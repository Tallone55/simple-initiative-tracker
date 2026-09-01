"""Imports Mint Cinnamon's actual active theme -- its selected theme
name, that theme's real color palette, and its window-control images
-- directly into this plain GTK4 app, rather than relying on
libadwaita to apply theming for us (libadwaita ignores the system
theme by design unless an app links against it, and even
gnome-calculator -- initially assumed to be proof libadwaita theming
works on Mint -- turned out via GTK Inspector to be running as GTK3
itself).

Deliberately scoped to Mint Cinnamon specifically, not a general
cross-desktop abstraction: Mint's own native apps (the xapps -- xed,
xreader, etc.) are kept on GTK3, where Cinnamon's theming applies
natively without any of this; GTK4 apps don't get that for free. Kept
in its own module so a second desktop's equivalent could be added
alongside it later, not because that generalization exists yet.

Colors: read from the active theme's own gtk-4.0/gtk[-dark].css file
where the theme provides one, falling back to the theme's
libadwaita-1.X/defaults-{dark,light}.css file (a file Mint's theme
packages ship to give GTK4/libadwaita apps accurate colors, present
even for themes with no gtk-4.0/ folder at all) via @define-color
parsing, with libadwaita's own stock published defaults as the final
per-color fallback. Both files are read purely as color DATA SOURCES
-- nothing here uses libadwaita as a library or renders anything
through it.
"""

import re
from pathlib import Path

from gi.repository import Gio, Gtk, Gdk

_DEFINE_COLOR_RE = re.compile(r"@define-color\s+([\w-]+)\s+([^;]+);")
_REFERENCE_RE = re.compile(r"@([\w-]+)")

_THEME_SEARCH_ROOTS = [
    Path.home() / ".themes",
    Path.home() / ".local" / "share" / "themes",
    Path("/usr/share/themes"),
]

# libadwaita's own published defaults for each mode -- used only for
# names a theme's own file doesn't define, or when no theme-provided
# file could be found/parsed at all. Taken directly from libadwaita's
# official CSS variables documentation.
_STOCK_DARK_DEFAULTS = {
    "window_bg_color": "#222226",
    "window_fg_color": "#ffffff",
    "view_bg_color": "#1d1d20",
    "view_fg_color": "#ffffff",
    "headerbar_bg_color": "#2e2e32",
    "headerbar_fg_color": "#ffffff",
    "popover_bg_color": "#36363a",
    "popover_fg_color": "#ffffff",
}
_STOCK_LIGHT_DEFAULTS = {
    "window_bg_color": "#fafafb",
    "window_fg_color": "#333338",
    "view_bg_color": "#ffffff",
    "view_fg_color": "#333338",
    "headerbar_bg_color": "#ffffff",
    "headerbar_fg_color": "#333338",
    "popover_bg_color": "#ffffff",
    "popover_fg_color": "#333338",
}

_current_prefers_dark = False
_current_theme_name = None
_current_gtk_settings = None
_fallback_provider = None


def sync_theme(gtk_settings=None):
    """Call once from Application.do_startup. Returns the live
    Gio.Settings object created -- callers must keep a reference so its
    "changed" signal connection isn't garbage collected. Returns None
    if Cinnamon's schema isn't present on this system at all (this
    module makes no attempt to fall back to any other mechanism)."""
    global _current_gtk_settings
    gtk_settings = gtk_settings or Gtk.Settings.get_default()
    _current_gtk_settings = gtk_settings

    settings = _try_open_schema("org.cinnamon.desktop.interface")
    if settings is None:
        return None

    def apply(*_args):
        global _current_prefers_dark, _current_theme_name
        theme_name = settings.get_string("gtk-theme")
        if theme_name:
            gtk_settings.set_property("gtk-theme-name", theme_name)
            _current_theme_name = theme_name
            _current_prefers_dark = "dark" in theme_name.lower()
            _apply_theme()

    def apply_icon_theme(*_args):
        icon_theme_name = settings.get_string("icon-theme")
        if icon_theme_name:
            gtk_settings.set_property("gtk-icon-theme-name", icon_theme_name)

    apply()
    apply_icon_theme()
    settings.connect("changed::gtk-theme", apply)
    settings.connect("changed::icon-theme", apply_icon_theme)
    return settings


def reapply():
    """Re-asserts the currently-known theme state without re-reading
    GSettings. Call this once, after the main window has actually been
    constructed and presented -- applying theme CSS before any window
    exists reliably affects plain CSS properties but doesn't reliably
    reach icon-level styling (the headerbar's window-control button
    glyphs) for widgets that don't exist yet at the moment it's set.
    """
    _apply_theme()


def _try_open_schema(schema_id):
    """Gio.Settings.new() on a schema that isn't installed doesn't
    raise a catchable Python exception -- it hard-aborts the process
    (a GLib-level assertion failure). Checking existence via
    SettingsSchemaSource first avoids that entirely."""
    schema_source = Gio.SettingsSchemaSource.get_default()
    if schema_source is None or schema_source.lookup(schema_id, True) is None:
        return None
    return Gio.Settings.new(schema_id)


# -- Colors ------------------------------------------------

# Mint's own name for a shade slightly lighter than its main content
# color -- present, and holding that same lighter-than-content
# relationship, in both the dark and light theme files. Used for the
# window canvas specifically, so it reads as a distinct surface from
# the table content below it, since Mint's own theme deliberately uses
# the same value for window_bg_color and view_bg_color and never
# provides that distinction itself.
_WINDOW_BG_HOVER_NAME = "mint_button_hover"


def _resolve_colors(dark):
    stock = _STOCK_DARK_DEFAULTS if dark else _STOCK_LIGHT_DEFAULTS
    discovered = _find_theme_colors(_current_theme_name, dark) if _current_theme_name else None
    discovered = discovered or {}
    resolved = {name: discovered.get(name, value) for name, value in stock.items()}

    if _WINDOW_BG_HOVER_NAME in discovered:
        resolved["window_bg_color"] = discovered[_WINDOW_BG_HOVER_NAME]
    else:
        # This theme doesn't define that name at all (a third-party or
        # differently-authored theme, for instance) -- fall back to
        # computing a lightened variant instead of leaving
        # window_bg_color identical to view_bg_color.
        resolved["window_bg_color"] = _lighten_hex(resolved["window_bg_color"])

    return resolved


def _find_theme_colors(theme_name, dark):
    """Tries stock GTK4's own theme file first (gtk-4.0/gtk[-dark].css)
    -- what a GTK4 app would actually load natively if the theme had
    full GTK4 support. Several Mint theme families never ship this
    (every "Mint-L-*" family, including Mint-L-Dark-Aqua, has no
    gtk-4.0/ folder at all -- only "Mint-X-*"/"Mint-Y-*" families do),
    so this falls back to the theme's libadwaita-1.X/ file when that
    doesn't exist.
    """
    theme_dir = _find_theme_dir(theme_name)
    if theme_dir is None:
        return None

    return (
        _read_css_colors(theme_dir / "gtk-4.0" / ("gtk-dark.css" if dark else "gtk.css"))
        or _read_libadwaita_colors(theme_dir, dark)
    )


def _read_css_colors(css_path):
    if not css_path.is_file():
        return None
    try:
        css_text = css_path.read_text(encoding="utf-8")
    except OSError:
        return None
    return _parse_define_colors(css_text) or None


def _read_libadwaita_colors(theme_dir, dark):
    filename = "defaults-dark.css" if dark else "defaults-light.css"
    candidates = sorted(theme_dir.glob(f"libadwaita-*/{filename}"))
    if not candidates:
        return None
    # Oldest libadwaita-1.X/ variant the theme ships, not newest --
    # matches the actually-installed libadwaita-1-0 version on the
    # target system (1.5.0), and a newer-numbered file a theme ships
    # isn't necessarily more complete than an older one.
    return _read_css_colors(candidates[0])


def _find_theme_dir(theme_name):
    for root in _THEME_SEARCH_ROOTS:
        candidate = root / theme_name
        if candidate.is_dir():
            return candidate
    return None


_TITLEBUTTON_ICON_RE = re.compile(
    r'button\.titlebutton\.(close|minimize|maximize)(:backdrop|:hover|:active)?\s*(?:,[^{]*)?\{\s*'
    r'background-image:\s*-gtk-scaled\(url\("([^"]+)"\),\s*url\("([^"]+)"\)\)'
)


def _resolve_titlebutton_images(theme_name, dark):
    """Returns a dict of (button, state) -> (1x file:// URL, 2x file://
    URL) for the close/minimize/maximize titlebar button images.

    Read from the theme's own gtk-3.0/gtk[-dark].css file specifically
    -- confirmed directly (not assumed): no GTK4 theme file provides an
    equivalent declaration for these at all, so gtk-3.0's is the only
    real source, even for this GTK4 app. GTK3's own CSS class for these
    buttons ("titlebutton") doesn't exist in GTK4's actual widget tree
    at all (confirmed via GTK Inspector: GTK4's windowcontrols buttons
    carry bare "close"/"minimize"/"maximize" classes, no "titlebutton").
    This reads only the asset PATHS out of GTK3's file; the CSS built
    around them targets GTK4's real selectors.

    Both the 1x and 2x URL are kept (an earlier version discarded the
    2x one entirely, which meant a HiDPI display always got the
    upscaled, blurrier 1x asset) so the generated CSS can hand both to
    GTK's own -gtk-scaled() -- the same mechanism the theme's own file
    uses -- rather than us trying to detect the display's scale factor
    ourselves.
    """
    if theme_name is None:
        return {}
    theme_dir = _find_theme_dir(theme_name)
    if theme_dir is None:
        return {}

    assets_dir = theme_dir / "gtk-3.0"
    css_path = assets_dir / ("gtk-dark.css" if dark else "gtk.css")
    if not css_path.is_file():
        return {}
    try:
        css_text = css_path.read_text(encoding="utf-8")
    except OSError:
        return {}

    images = {}
    for button, state, rel_path_1x, rel_path_2x in _TITLEBUTTON_ICON_RE.findall(css_text):
        image_path_1x = assets_dir / rel_path_1x
        image_path_2x = assets_dir / rel_path_2x
        if image_path_1x.is_file() and image_path_2x.is_file():
            images[(button, state)] = (image_path_1x.as_uri(), image_path_2x.as_uri())
    return images


_RGB_ALPHA_RE = re.compile(
    r"rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)\s*(?:[,/]\s*([\d.]+)(%)?\s*)?\)", re.IGNORECASE
)


def _normalize_color_value(value):
    """Converts any rgb()/rgba() color with an alpha channel --
    comma-separated or modern space/slash syntax, either case -- into a
    flat 8-digit hex color (#rrggbbaa), a format GDK's own color parser
    explicitly documents as supported ("#rgba", "#rrggbbaa",
    "#rrrrggggbbbbaaaa"). A flat hex literal has nothing to nest,
    unlike a function-call form (rgba(...), or a color wrapped in
    alpha(...)), which matters here specifically -- GTK's CSS parser on
    the target system rejects both 4-argument rgba() and rgb() nested
    inside alpha(). rgb()/rgba() with no alpha channel just gets
    comma-normalized, not converted to hex. Values that aren't
    rgb()/rgba() at all (hex, alpha(), color keywords) pass through
    unchanged.
    """
    def replace(match):
        r, g, b, alpha, is_percent = match.groups()
        r, g, b = int(r), int(g), int(b)
        if alpha is None:
            return f"rgb({r}, {g}, {b})"
        alpha_value = float(alpha) / 100 if is_percent else float(alpha)
        alpha_hex = format(round(alpha_value * 255), "02x")
        return f"#{r:02x}{g:02x}{b:02x}{alpha_hex}"

    return _RGB_ALPHA_RE.sub(replace, value)


def _parse_define_colors(css_text):
    """Extracts @define-color name -> value pairs, substituting any
    @other_name reference already parsed earlier in the same file --
    whether the entire value is a bare reference or one embedded in a
    larger expression (e.g. alpha(@window_bg_color, 0.9)) -- and
    normalizing modern CSS4 color syntax GTK's parser can't read (see
    _normalize_color_value) before storing the final value."""
    colors = {}
    for match in _DEFINE_COLOR_RE.finditer(css_text):
        name, value = match.group(1), match.group(2).strip()
        resolved = _REFERENCE_RE.sub(lambda m: colors.get(m.group(1), m.group(0)), value)
        colors[name] = _normalize_color_value(resolved)
    return colors


# -- Window-control images ------------------------------------------------

def _build_titlebutton_css(images):
    """Builds background-image rules for the window-control buttons
    from a resolved images dict (see _resolve_titlebutton_images) --
    empty if the theme doesn't provide any, which just means those
    buttons render with whatever GTK's own default is, not a crash or
    a broken reference.

    background-image uses -gtk-scaled(url(1x), url(2x)) -- the same
    mechanism the theme's own CSS uses -- rather than a plain url() to
    the 1x asset alone, so GTK picks the right resolution for the
    display's actual scale factor itself instead of always showing the
    1x asset upscaled (blurry on HiDPI).

    background-repeat/background-position are set explicitly since
    CSS's own default (repeat, tiling to fill the box) isn't what we
    want for a single centered icon -- confirmed directly: without
    these, the close button rendered as four tiled copies of the same
    image. background-size is deliberately NOT set at all -- confirmed
    directly against the theme's own gtk-3.0/gtk-dark.css, which never
    sets it either; the image is meant to show at its own natural
    pixel size, with the surrounding box sized to just barely exceed
    it (equal 3px padding on every side below, rather than the theme's
    own asymmetric padding, which was for a differently-shaped GTK3
    button box) -- not scaled to fill whatever box GTK4's own default
    button size happens to give it.

    background-color is explicitly cleared to transparent everywhere
    here (both the per-state rules and the base sizing rule) --
    without this, GTK's own default button background-color (a dark
    circular hover/press highlight) still shows behind these images,
    which is redundant: the theme's own per-state assets (separate
    normal/hover/active/backdrop images) already provide that same
    visual feedback baked into the image itself.

    For each button with at least one resolved image, its own GtkImage
    child (the default symbolic icon glyph, e.g. window-close-symbolic)
    is separately made transparent -- a background-image paints on the
    button itself, a distinct layer from the image child's own
    rendered content, so without this the default GTK glyph and our
    replacement render simultaneously, one on top of the other. The
    broader "windowcontrols button image" color rule (recoloring the
    default glyph when no replacement image exists at all) is left
    alone elsewhere -- this only overrides it, via higher selector
    specificity, for buttons that actually have one.
    """
    if not images:
        return ""
    rules = []
    buttons_with_images = set()
    for (button, state), (url_1x, url_2x) in images.items():
        buttons_with_images.add(button)
        rules.append(
            f'windowcontrols button.{button}{state} {{\n'
            f'    background-image: -gtk-scaled(url("{url_1x}"), url("{url_2x}"));\n'
            f'    background-repeat: no-repeat;\n'
            f'    background-position: center;\n'
            f'    background-color: transparent;\n'
            f"}}"
        )
    for button in buttons_with_images:
        rules.append(
            f'windowcontrols button.{button} {{\n'
            f'    min-width: 0;\n'
            f'    min-height: 0;\n'
            f'    padding: 4px;\n'
            f'    margin: 0;\n'
            f'    background-color: transparent;\n'
            f"}}"
        )
        rules.append(
            f'windowcontrols button.{button} image {{\n'
            f'    color: transparent;\n'
            f"}}"
        )
    return "\n" + "\n".join(rules)


# -- CSS application ------------------------------------------------

def _lighten_hex(value, amount=0.08):
    """Blends a plain #rrggbb hex color toward white by `amount`
    (0-1). Used for the window canvas's background when the theme
    doesn't define _WINDOW_BG_HOVER_NAME, to give it a bit more
    contrast against the table content below it. Values that aren't a
    plain 6-digit hex (an 8-digit #rrggbbaa from _normalize_color_value,
    a bare color keyword, an unresolved @reference) are returned
    unchanged rather than guessed at.
    """
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value
    r, g, b = (int(value[i:i + 2], 16) for i in (1, 3, 5))
    r = round(r + (255 - r) * amount)
    g = round(g + (255 - g) * amount)
    b = round(b + (255 - b) * amount)
    return f"#{r:02x}{g:02x}{b:02x}"


def _build_css(colors, images):
    return f"""
window {{
    background-color: {colors['window_bg_color']};
    background-image: none;
    color: {colors['window_fg_color']};
}}
headerbar,
columnview header,
columnview header *,
columnview header button {{
    background-color: {colors['headerbar_bg_color']};
    background-image: none;
    color: {colors['headerbar_fg_color']};
}}
windowcontrols button,
windowcontrols button image {{
    color: {colors['headerbar_fg_color']};
}}
columnview,
columnview > listview {{
    background-color: {colors['view_bg_color']};
    background-image: none;
    color: {colors['view_fg_color']};
}}
columnview > listview > row:not(:selected) {{
    background-color: {colors['view_bg_color']};
    color: {colors['view_fg_color']};
}}
columnview > listview > row:nth-child(even):not(:selected) {{
    background-color: alpha(currentColor, 0.05);
}}
popover {{
    background-color: transparent;
    background-image: none;
    color: {colors['popover_fg_color']};
}}
{_build_titlebutton_css(images)}
""".encode()


def _apply_theme():
    """Rebuilds and applies the CSS for the currently-known theme
    state, including the window-control button images. Runs on every
    call rather than caching, so it always reflects whatever theme is
    currently known, not a value captured once at startup.

    Toggles the SAME provider object's CONTENT (via load_from_data)
    rather than removing and re-adding the provider itself.
    Application.py adds this provider before styling.py's own
    (sync_theme() runs before install_css() in do_startup), so at
    equal specificity styling.py's rules -- added later -- win any
    tiebreak, which is what keeps the amber current-turn highlight
    (styling.py) from being overridden by this module's broader
    row-background rules. Removing and re-adding this provider on
    every theme change would move it to the end of the provider list
    each time, making it the more-recently-added one instead --
    silently flipping which provider wins ties, without styling.py
    ever changing at all. Keeping one persistent provider object,
    added once, keeps that relationship constant regardless of how
    many times the theme changes.
    """
    provider = _get_provider()
    if provider is None:
        return
    colors = _resolve_colors(_current_prefers_dark)
    images = _resolve_titlebutton_images(_current_theme_name, _current_prefers_dark)
    provider.load_from_data(_build_css(colors, images))
    if _current_gtk_settings is not None:
        _current_gtk_settings.set_property(
            "gtk-application-prefer-dark-theme", _current_prefers_dark
        )


def _get_provider():
    global _fallback_provider
    if _fallback_provider is not None:
        return _fallback_provider

    display = Gdk.Display.get_default()
    if display is None:
        return None

    _fallback_provider = Gtk.CssProvider()
    Gtk.StyleContext.add_provider_for_display(
        display, _fallback_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    return _fallback_provider