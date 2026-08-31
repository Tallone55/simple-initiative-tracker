"""Detects the desktop's dark/light theme preference and applies it,
bridging gaps a plain (non-libadwaita) Gtk.Application doesn't handle
on its own.

Preferred mechanism: the XDG Desktop Portal
(org.freedesktop.portal.Settings), the SAME cross-desktop-environment
mechanism libadwaita's AdwStyleManager uses -- this is how a reference
app like gnome-calculator gets its dark styling correctly on Linux
Mint, despite not being a Mint-specific XApp itself. Using the same
mechanism means picking up whatever signal Mint has already ensured is
correct for libadwaita apps, rather than us re-deriving
desktop-specific heuristics.

The portal isn't guaranteed to be running or to implement Settings --
a documented, common gap on some compositors (e.g. xdg-desktop-portal-wlr
doesn't implement it at all). When it's unavailable, this falls back to
reading each desktop's own settings directly:
- GNOME: a boolean toggle (org.gnome.desktop.interface / color-scheme)
  applied over ONE shared theme (Adwaita) that responds to it.
- Cinnamon: a totally separate, named GTK theme selection
  (org.cinnamon.desktop.interface / gtk-theme) -- no boolean toggle at
  all; "dark mode" is just a different theme name being active.
Cinnamon's gtk-theme-name is always applied regardless of which
detection mechanism ends up authoritative, since it's independently
correct to do (the actual theme NAME Cinnamon has selected) even when
something else decides the light/dark CSS-fallback question.

Confirmed directly on a real system (not assumed): Cinnamon's own dark
theme variants (e.g. "Mint-L-Dark-Aqua") can ship NO gtk-4.0/ CSS
directory at all. Setting gtk-theme-name correctly in that case still
leaves nothing for GTK4 to load -- it falls back to GTK's own bundled
light default regardless of the system's actual preference. Since
there's no theme CSS to inherit from, this module also supplies its
own minimal dark-mode CSS fallback whenever dark mode is detected as
desired, applied via the same CssProvider mechanism as styling.py.
"""

import os

from gi.repository import Gio, GLib, Gtk, Gdk

# background-image is reset to "none" alongside background-color
# throughout, since a headerbar/columnview's focused-state background
# is commonly painted via a gradient image that sits visually on top
# of (and isn't cleared by) background-color alone. columnview >
# header is targeted explicitly and separately from columnview >
# listview, since the header portion is a distinct CSS node, not
# covered by styling the body rows alone.
#
# Row background rules explicitly exclude :selected (via :not()) so
# they never compete with styling.py's dedicated amber current-turn
# rule for the same rows -- both are our own CSS at the same provider
# priority, so rather than depend on getting specificity exactly right
# a second time, this avoids the conflict outright by construction.
_DARK_FALLBACK_CSS = b"""
window, headerbar, columnview, columnview > listview, columnview > header {
    background-color: #242424;
    background-image: none;
    color: #e9e9e9;
}
columnview > listview > row:not(:selected) {
    background-color: #242424;
    color: #e9e9e9;
}
columnview > listview > row:nth-child(even):not(:selected) {
    background-color: #2a2a2a;
}
columnview > header > *,
columnview > header button {
    background-color: #242424;
    background-image: none;
    color: #e9e9e9;
}
"""

_dark_fallback_provider = None
# Once the portal has successfully established itself as the dark-mode
# source of truth, DE-specific fallback heuristics (which are less
# accurate) shouldn't be allowed to override its signal.
_portal_is_authoritative = False
# Tracks the last-applied preference so reapply() (see below) can
# re-assert it without re-reading GSettings/the portal again.
_current_prefers_dark = False
_current_gtk_settings = None


def sync_theme(gtk_settings=None):
    """Call once from Application.do_startup. Returns the live
    Gio.DBusProxy / Gio.Settings objects created -- callers must keep
    a reference so their signal connections aren't garbage collected.
    """
    global _current_gtk_settings
    gtk_settings = gtk_settings or Gtk.Settings.get_default()
    _current_gtk_settings = gtk_settings
    live_objects = []

    portal = _sync_portal(gtk_settings)
    if portal is not None:
        live_objects.append(portal)

    for strategy in _ordered_de_strategies():
        settings = strategy(gtk_settings)
        if settings is not None:
            live_objects.append(settings)

    return live_objects


def reapply():
    """Re-asserts the currently-known dark/light preference without
    re-reading GSettings/the portal. Call this once, after the main
    window has actually been constructed and presented.

    gtk-application-prefer-dark-theme (and our own fallback CSS)
    reliably affects plain CSS properties even when set before any
    window exists, but doesn't reliably reach icon-level styling (the
    headerbar's window-control button glyphs, the hamburger menu's
    popover) for widgets that don't exist yet at the moment it's set.
    Re-running the same apply logic once real widgets exist fixes it --
    this just does that deliberately, rather than requiring the system
    setting to be toggled again after every launch.
    """
    if _current_gtk_settings is not None:
        _current_gtk_settings.set_property(
            "gtk-application-prefer-dark-theme", _current_prefers_dark
        )
    _set_dark_fallback_active(_current_prefers_dark)


def _ordered_de_strategies():
    hint = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    strategies = [_sync_gnome, _sync_cinnamon]
    if "cinnamon" in hint:
        strategies.reverse()
    return strategies


# -- XDG Desktop Portal (preferred) ------------------------------------------------

_PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
_PORTAL_OBJECT_PATH = "/org/freedesktop/portal/desktop"
_PORTAL_INTERFACE = "org.freedesktop.portal.Settings"
_PORTAL_NAMESPACE = "org.freedesktop.appearance"
_PORTAL_KEY = "color-scheme"


def _sync_portal(gtk_settings):
    """Reads org.freedesktop.appearance/color-scheme from the XDG
    portal. Enum values per the portal's own spec: 0 = no preference,
    1 = prefer dark, 2 = prefer light; unknown values treated as 0.

    Unlike Gio.Settings' missing-schema case (which hard-aborts the
    process), a missing/failing D-Bus call raises a normal, catchable
    GLib.Error -- so a plain try/except is the correct, safe pattern
    here, confirmed against real bug reports of this exact call
    failing on portal setups that don't implement Settings.
    """
    try:
        proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE,
            None,
            _PORTAL_BUS_NAME,
            _PORTAL_OBJECT_PATH,
            _PORTAL_INTERFACE,
            None,
        )
        result = proxy.call_sync(
            "Read",
            GLib.Variant("(ss)", (_PORTAL_NAMESPACE, _PORTAL_KEY)),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
    except GLib.Error:
        return None

    scheme_value = _unwrap_portal_value(result)
    if scheme_value is None:
        return None

    def apply(value):
        global _portal_is_authoritative, _current_prefers_dark
        _portal_is_authoritative = True
        prefers_dark = value == 1
        _current_prefers_dark = prefers_dark
        gtk_settings.set_property("gtk-application-prefer-dark-theme", prefers_dark)
        _set_dark_fallback_active(prefers_dark)

    apply(scheme_value)

    def on_signal(_proxy, _sender, signal_name, params):
        if signal_name != "SettingChanged":
            return
        namespace, key, new_value = params.unpack()
        if namespace == _PORTAL_NAMESPACE and key == _PORTAL_KEY:
            apply(_coerce_portal_int(new_value))

    proxy.connect("g-signal", on_signal)
    return proxy


def _unwrap_portal_value(result_variant):
    """Read() double-wraps the reply -- a Variant containing another
    Variant containing the actual uint32 (the public
    org.freedesktop.portal.Settings.Read differs from the internal
    org.freedesktop.impl.portal.Settings.Read in this way). The loop in
    _coerce_portal_int handles arbitrary nesting depth."""
    try:
        value = result_variant.unpack()[0]
        return _coerce_portal_int(value)
    except (IndexError, TypeError, ValueError):
        return None


def _coerce_portal_int(value):
    while isinstance(value, GLib.Variant):
        value = value.unpack()
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# -- Desktop-specific fallbacks ------------------------------------------------

def _try_open_schema(schema_id):
    """Gio.Settings.new() on a schema that isn't installed doesn't
    raise a catchable Python exception -- it hard-aborts the process
    (a GLib-level assertion failure). Checking existence via
    SettingsSchemaSource first avoids that entirely; returns None
    (rather than crashing) when the schema isn't present."""
    schema_source = Gio.SettingsSchemaSource.get_default()
    if schema_source is None or schema_source.lookup(schema_id, True) is None:
        return None
    return Gio.Settings.new(schema_id)


def _sync_gnome(gtk_settings):
    """GNOME's dark/light toggle: org.gnome.desktop.interface /
    color-scheme -> Gtk.Settings::gtk-application-prefer-dark-theme.
    Only drives the dark-fallback CSS if the portal hasn't already
    established itself as authoritative."""
    settings = _try_open_schema("org.gnome.desktop.interface")
    if settings is None:
        return None

    def apply(*_args):
        global _current_prefers_dark
        prefers_dark = settings.get_string("color-scheme") == "prefer-dark"
        gtk_settings.set_property("gtk-application-prefer-dark-theme", prefers_dark)
        if not _portal_is_authoritative:
            _current_prefers_dark = prefers_dark
            _set_dark_fallback_active(prefers_dark)

    apply()
    settings.connect("changed::color-scheme", apply)
    return settings


def _sync_cinnamon(gtk_settings):
    """Cinnamon's named-theme selection: org.cinnamon.desktop.interface
    / gtk-theme -> Gtk.Settings::gtk-theme-name. The theme name is
    always applied regardless of the portal, since that part is
    correct independent of which mechanism decides the dark-fallback
    question. The "dark" substring check on the theme name (matching
    the near-universal Linux theme naming convention -- Mint-Y-Dark,
    Adwaita-dark, Yaru-dark, etc.) only drives the fallback CSS if the
    portal hasn't already established itself as authoritative."""
    settings = _try_open_schema("org.cinnamon.desktop.interface")
    if settings is None:
        return None

    def apply(*_args):
        global _current_prefers_dark
        theme_name = settings.get_string("gtk-theme")
        if theme_name:
            gtk_settings.set_property("gtk-theme-name", theme_name)
        if not _portal_is_authoritative:
            prefers_dark = "dark" in theme_name.lower()
            _current_prefers_dark = prefers_dark
            _set_dark_fallback_active(prefers_dark)

    apply()
    settings.connect("changed::gtk-theme", apply)
    return settings


# -- Fallback CSS ------------------------------------------------

def _set_dark_fallback_active(active):
    """Toggles the minimal dark-mode CSS supplement on or off.

    Applied unconditionally whenever dark mode is detected as desired,
    rather than trying to probe the filesystem for whether the active
    theme happens to provide real GTK4 assets (fragile, and
    theme-packaging-layout-dependent). If the real system theme DOES
    provide correct GTK4 dark styling on its own, this is simply
    redundant with it, not conflicting.

    Toggles the SAME provider object's CONTENT (via load_from_data)
    rather than removing and re-adding the provider itself. That
    distinction matters: application.py adds this provider before
    styling.py's own (sync_theme() runs before install_css() in
    do_startup), so at equal specificity styling.py's rules -- added
    later -- win any tiebreak, which is what keeps the amber
    current-turn highlight (styling.py) from being overridden by this
    module's broader row-background rules. Removing and re-adding this
    provider on every toggle would move it to the END of the provider
    list each time, making IT the more-recently-added one instead --
    silently flipping which provider wins ties, without styling.py
    ever changing at all. Keeping one persistent provider object,
    added once, keeps that relationship constant regardless of how
    many times dark mode gets toggled.
    """
    provider = _get_dark_fallback_provider()
    if provider is None:
        return
    provider.load_from_data(_DARK_FALLBACK_CSS if active else b"")


def _get_dark_fallback_provider():
    """Creates and registers the fallback CSS provider exactly once;
    returns the same object on every subsequent call. See
    _set_dark_fallback_active's docstring for why this provider is
    never removed once added."""
    global _dark_fallback_provider
    if _dark_fallback_provider is not None:
        return _dark_fallback_provider

    display = Gdk.Display.get_default()
    if display is None:
        return None

    _dark_fallback_provider = Gtk.CssProvider()
    Gtk.StyleContext.add_provider_for_display(
        display, _dark_fallback_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    return _dark_fallback_provider
