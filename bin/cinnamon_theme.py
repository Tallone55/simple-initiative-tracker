"""Imports Mint Cinnamon's active theme (name, color palette, and
window-control button images) directly into this GTK4 app, rather than
relying on libadwaita (which ignores the system theme unless an app
links against it, and doesn't reach GTK4 apps under Cinnamon natively).

Colors are read from the active theme's gtk-4.0/gtk[-dark].css file
where present, falling back to its libadwaita-1.X/defaults-*.css file,
and finally to libadwaita's own stock defaults."""

import re
from pathlib import Path

from gi.repository import Gio, GLib, Gtk, Gdk

_DEFINE_COLOR_RE = re.compile(r"@define-color\s+([\w-]+)\s+([^;]+);")
_REFERENCE_RE = re.compile(r"@([\w-]+)")

# GNOME/libadwaita's standard named-color palette, used as a fallback
# when a theme references e.g. "@red_4" without defining it locally.
_LIBADWAITA_NAMED_COLORS = {
    "blue_1": "#99c1f1", "blue_2": "#62a0ea", "blue_3": "#3584e4", "blue_4": "#1c71d8", "blue_5": "#1a5fb4",
    "green_1": "#8ff0a4", "green_2": "#57e389", "green_3": "#33d17a", "green_4": "#2ec27e", "green_5": "#26a269",
    "yellow_1": "#f9f06b", "yellow_2": "#f8e45c", "yellow_3": "#f6d32d", "yellow_4": "#f5c211", "yellow_5": "#e5a50a",
    "orange_1": "#ffbe6f", "orange_2": "#ffa348", "orange_3": "#ff7800", "orange_4": "#e66100", "orange_5": "#c64600",
    "red_1": "#f66151", "red_2": "#ed333b", "red_3": "#e01b24", "red_4": "#c01c28", "red_5": "#a51d2d",
    "purple_1": "#dc8add", "purple_2": "#c061cb", "purple_3": "#9141ac", "purple_4": "#813d9c", "purple_5": "#613583",
    "brown_1": "#cdab8f", "brown_2": "#b5835a", "brown_3": "#986a44", "brown_4": "#865e3c", "brown_5": "#63452c",
    "light_1": "#ffffff", "light_2": "#f6f5f4", "light_3": "#deddda", "light_4": "#c0bfbc", "light_5": "#9a9996",
    "dark_1": "#77767b", "dark_2": "#5e5c64", "dark_3": "#3d3846", "dark_4": "#241f31", "dark_5": "#000000",
}


def _theme_search_roots():
    """Directories GTK searches for installed themes."""
    roots = [Path.home() / ".themes"]
    for data_dir in [GLib.get_user_data_dir(), *GLib.get_system_data_dirs()]:
        candidate = Path(data_dir) / "themes"
        if candidate not in roots:
            roots.append(candidate)
    return roots


_THEME_SEARCH_ROOTS = _theme_search_roots()

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
    Gio.Settings object (callers must keep a reference alive), or None
    if Cinnamon's GSettings schema isn't present."""
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
            _current_prefers_dark = _detect_prefers_dark(theme_name)
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
    """Re-asserts the currently-known theme state. Call after the main
    window has been constructed and presented."""
    _apply_theme()


def _try_open_schema(schema_id):
    """Gio.Settings.new() on a missing schema hard-aborts the process,
    so existence is checked first."""
    schema_source = Gio.SettingsSchemaSource.get_default()
    if schema_source is None or schema_source.lookup(schema_id, True) is None:
        return None
    return Gio.Settings.new(schema_id)


def _detect_prefers_dark(theme_name):
    """Whether the theme should be treated as dark. Tries, in order:
    the XDG portal's color-scheme setting, the theme's own background
    luminance, then a name-substring guess."""
    portal_preference = _read_portal_color_scheme()
    if portal_preference is not None:
        return portal_preference

    name_guess = "dark" in theme_name.lower()
    discovered = _find_theme_colors(theme_name, name_guess)
    if discovered:
        bg = discovered.get("window_bg_color") or discovered.get("theme_bg_color")
        if bg:
            luminance = _color_luminance(bg)
            if luminance is not None:
                return luminance < 0.5
    return name_guess


def _read_portal_color_scheme():
    """Reads org.freedesktop.appearance's color-scheme via the XDG
    Desktop Portal over D-Bus. Returns True/False/None (no
    preference, or the portal couldn't be reached)."""
    try:
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        result = connection.call_sync(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Settings",
            "Read",
            GLib.Variant("(ss)", ("org.freedesktop.appearance", "color-scheme")),
            GLib.VariantType("(v)"),
            Gio.DBusCallFlags.NONE,
            200,
            None,
        )
    except GLib.Error:
        return None

    value = result.unpack()[0]
    if value == 1:
        return True
    if value == 2:
        return False
    return None


# -- Colors ------------------------------------------------

# Mint's own name for a shade lighter than its main content color,
# used for view_bg_color so the table surface reads distinct from the
# window canvas.
_VIEW_BG_ACCENT_NAME = "mint_button_hover"

# Legacy GTK3-era color names, tried when a theme doesn't define the
# modern role under its GTK4 name.
_LEGACY_COLOR_ALIASES = {
    "window_bg_color": ("theme_bg_color",),
    "window_fg_color": ("theme_fg_color",),
    "view_bg_color": ("theme_base_color",),
    "view_fg_color": ("theme_text_color",),
    "headerbar_bg_color": ("wm_bg_a", "wm_bg"),
    "headerbar_fg_color": ("theme_fg_color",),
    "popover_bg_color": ("insensitive_base_color",),
    "popover_fg_color": ("theme_fg_color",),
}


def _resolve_colors(dark):
    stock = _STOCK_DARK_DEFAULTS if dark else _STOCK_LIGHT_DEFAULTS
    discovered = _find_theme_colors(_current_theme_name, dark) if _current_theme_name else None
    discovered = discovered or {}

    resolved = {}
    for name, stock_value in stock.items():
        if name in discovered:
            resolved[name] = discovered[name]
            continue
        resolved[name] = stock_value
        for legacy_name in _LEGACY_COLOR_ALIASES.get(name, ()):
            if legacy_name in discovered:
                resolved[name] = discovered[legacy_name]
                break

    view_legacy_names = _LEGACY_COLOR_ALIASES["view_bg_color"]
    has_real_view_bg = "view_bg_color" in discovered or any(
        n in discovered for n in view_legacy_names
    )

    if _VIEW_BG_ACCENT_NAME in discovered:
        resolved["view_bg_color"] = discovered[_VIEW_BG_ACCENT_NAME]
    elif not has_real_view_bg:
        resolved["view_bg_color"] = _lighten_hex(resolved["window_bg_color"])

    return resolved


def _find_theme_colors(theme_name, dark):
    """Tries the theme's gtk-4.0/ file, then libadwaita-1.X/, then
    gtk-3.0/ -- some theme families ship only a subset."""
    theme_dir = _find_theme_dir(theme_name)
    if theme_dir is None:
        return None

    return (
        _read_css_colors(_variant_css_path(theme_dir / "gtk-4.0", dark))
        or _read_libadwaita_colors(theme_dir, dark)
        or _read_css_colors(_variant_css_path(theme_dir / "gtk-3.0", dark))
    )


def _variant_css_path(folder, dark):
    """The gtk[-dark].css to use from `folder`, preferring the file
    matching `dark` but falling back to the other if only one exists."""
    primary = folder / ("gtk-dark.css" if dark else "gtk.css")
    if primary.is_file():
        return primary
    fallback = folder / ("gtk.css" if dark else "gtk-dark.css")
    return fallback if fallback.is_file() else None


def _find_highlight_colors(theme_name, dark):
    """Locates the theme's selection/highlight color. Returns (bg, fg)
    or None. Tries gtk-4.0/, then libadwaita accent tokens, then
    gtk-3.0/ (modern or legacy name)."""
    if theme_name is None:
        return None
    theme_dir = _find_theme_dir(theme_name)
    if theme_dir is None:
        return None

    gtk4_colors = _read_css_colors(_variant_css_path(theme_dir / "gtk-4.0", dark))
    if gtk4_colors and "theme_selected_bg_color" in gtk4_colors:
        return (
            gtk4_colors["theme_selected_bg_color"],
            gtk4_colors.get("theme_selected_fg_color", "#ffffff"),
        )

    adwaita_colors = _read_libadwaita_colors(theme_dir, dark)
    if adwaita_colors and "accent_bg_color" in adwaita_colors:
        return (
            adwaita_colors["accent_bg_color"],
            adwaita_colors.get("accent_fg_color", "#ffffff"),
        )

    gtk3_colors = _read_css_colors(_variant_css_path(theme_dir / "gtk-3.0", dark))
    if gtk3_colors:
        bg = gtk3_colors.get("theme_selected_bg_color") or gtk3_colors.get("selected_bg_color")
        fg = gtk3_colors.get("theme_selected_fg_color") or gtk3_colors.get("selected_fg_color")
        if bg:
            return bg, fg or "#ffffff"

    return None


def _find_destructive_colors(theme_name, dark):
    """Locates the theme's destructive/error accent color. Returns
    (bg, fg) or None. Same tiered lookup as _find_highlight_colors."""
    if theme_name is None:
        return None
    theme_dir = _find_theme_dir(theme_name)
    if theme_dir is None:
        return None

    gtk4_colors = _read_css_colors(_variant_css_path(theme_dir / "gtk-4.0", dark))
    if gtk4_colors:
        bg = gtk4_colors.get("destructive_bg_color") or gtk4_colors.get("error_color")
        if bg:
            return bg, gtk4_colors.get("destructive_fg_color", "#ffffff")

    adwaita_colors = _read_libadwaita_colors(theme_dir, dark)
    if adwaita_colors:
        bg = adwaita_colors.get("destructive_bg_color") or adwaita_colors.get("error_color")
        if bg:
            return bg, adwaita_colors.get("destructive_fg_color", "#ffffff")

    gtk3_colors = _read_css_colors(_variant_css_path(theme_dir / "gtk-3.0", dark))
    if gtk3_colors:
        bg = gtk3_colors.get("destructive_bg_color") or gtk3_colors.get("error_color")
        if bg:
            return bg, gtk3_colors.get("destructive_fg_color", "#ffffff")

    return None


def _read_css_colors(css_path):
    if css_path is None or not css_path.is_file():
        return None
    try:
        css_text = css_path.read_text(encoding="utf-8")
    except OSError:
        return None
    return _parse_define_colors(css_text) or None


def _read_libadwaita_colors(theme_dir, dark):
    """Prefers defaults-dark.css/defaults-light.css matching `dark`,
    falling back to whichever variant a theme actually ships."""
    filenames = (
        ("defaults-dark.css", "defaults-light.css")
        if dark
        else ("defaults-light.css", "defaults-dark.css")
    )
    for filename in filenames:
        candidates = sorted(theme_dir.glob(f"libadwaita-*/{filename}"))
        if candidates:
            return _read_css_colors(candidates[0])
    return None


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
    """Returns {(button, state): (1x file:// URL, 2x file:// URL)} for
    the close/minimize/maximize images, read from the theme's
    gtk-3.0/gtk[-dark].css (GTK4's windowcontrols buttons don't carry
    GTK3's "titlebutton" class, so only the asset paths are reused)."""
    if theme_name is None:
        return {}
    theme_dir = _find_theme_dir(theme_name)
    if theme_dir is None:
        return {}

    assets_dir = theme_dir / "gtk-3.0"
    css_path = _variant_css_path(assets_dir, dark)
    if css_path is None:
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
    r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)\s*(?:[,/]\s*([\d.]+)(%)?\s*)?\)", re.IGNORECASE
)


def _normalize_color_value(value):
    """Converts rgb()/rgba() with an alpha channel into #rrggbbaa
    (GTK's CSS parser rejects rgba() nested inside alpha()). Values
    with no alpha are just comma/rounding-normalized."""
    def replace(match):
        r, g, b, alpha, is_percent = match.groups()
        r, g, b = round(float(r)), round(float(g)), round(float(b))
        if alpha is None:
            return f"rgb({r}, {g}, {b})"
        alpha_value = float(alpha) / 100 if is_percent else float(alpha)
        alpha_hex = format(round(alpha_value * 255), "02x")
        return f"#{r:02x}{g:02x}{b:02x}{alpha_hex}"

    return _RGB_ALPHA_RE.sub(replace, value)


def _parse_define_colors(css_text):
    """Extracts @define-color name -> value pairs, substituting any
    @other_name reference, falling back to
    _LIBADWAITA_NAMED_COLORS for names the file doesn't define."""
    colors = {}

    def substitute(match):
        name = match.group(1)
        return colors.get(name) or _LIBADWAITA_NAMED_COLORS.get(name, match.group(0))

    for match in _DEFINE_COLOR_RE.finditer(css_text):
        name, value = match.group(1), match.group(2).strip()
        resolved = _REFERENCE_RE.sub(substitute, value)
        colors[name] = _normalize_color_value(resolved)
    return colors


# -- Window-control images ------------------------------------------------

def _build_titlebutton_css(images):
    """Builds background-image rules for the window-control buttons
    from a resolved images dict; empty if the theme provides none."""
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

def _color_luminance(value):
    """Perceived brightness (0=black, 1=white) of a "#rrggbb[aa]" or
    "rgb(r, g, b)" string. Returns None for anything else."""
    hex_match = re.fullmatch(r"#([0-9a-fA-F]{6})(?:[0-9a-fA-F]{2})?", value)
    if hex_match:
        hex6 = hex_match.group(1)
        r, g, b = (int(hex6[i:i + 2], 16) for i in (0, 2, 4))
    else:
        rgb_match = re.fullmatch(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", value)
        if not rgb_match:
            return None
        r, g, b = (int(component) for component in rgb_match.groups())
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def _lighten_hex(value, amount=0.08):
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value
    r, g, b = (int(value[i:i + 2], 16) for i in (1, 3, 5))
    r = round(r + (255 - r) * amount)
    g = round(g + (255 - g) * amount)
    b = round(b + (255 - b) * amount)
    return f"#{r:02x}{g:02x}{b:02x}"


def _darken_hex(value, amount=0.12):
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value
    r, g, b = (int(value[i:i + 2], 16) for i in (1, 3, 5))
    r = round(r * (1 - amount))
    g = round(g * (1 - amount))
    b = round(b * (1 - amount))
    return f"#{r:02x}{g:02x}{b:02x}"


def _build_css(colors, images, highlight=None, destructive=None):
    highlight_css = ""
    if highlight is not None:
        highlight_bg, highlight_fg = highlight
        highlight_css = f"""
columnview row:selected,
columnview row:selected:hover {{
    background-color: {highlight_bg};
    color: {highlight_fg};
}}
selection,
*:selected {{
    background-color: {highlight_bg};
    color: {highlight_fg};
    background-image: none;
}}
/* :focus, not :focus-visible: FOCUS_VISIBLE propagates to every
   ancestor widget, which would outline whole containers at once.
   ":not(text)" excludes GtkEntry's internal text node (handled by
   entry:focus-within below instead). */
*:focus:not(text) {{
    outline-color: {highlight_bg};
    outline-style: solid;
    outline-width: 2px;
    outline-offset: -2px;
}}
entry:focus-within {{
    outline-color: {highlight_bg};
    outline-style: solid;
    outline-width: 2px;
    outline-offset: -2px;
}}
button.suggested-action {{
    background-color: {highlight_bg};
    background-image: none;
    color: {highlight_fg};
}}
button.suggested-action:hover {{
    background-color: {_lighten_hex(highlight_bg, 0.12)};
    background-image: none;
    color: {highlight_fg};
}}
button.suggested-action:active {{
    background-color: {_darken_hex(highlight_bg, 0.12)};
    background-image: none;
    color: {highlight_fg};
}}
"""
    destructive_css = ""
    if destructive is not None:
        destructive_bg, destructive_fg = destructive
        destructive_css = f"""
button.destructive-action {{
    background-color: {destructive_bg};
    background-image: none;
    color: {destructive_fg};
}}
button.destructive-action:hover {{
    background-color: {_lighten_hex(destructive_bg, 0.12)};
    background-image: none;
    color: {destructive_fg};
}}
button.destructive-action:active {{
    background-color: {_darken_hex(destructive_bg, 0.12)};
    background-image: none;
    color: {destructive_fg};
}}
"""
    return f"""
window {{
    background-color: {colors['window_bg_color']};
    background-image: none;
    color: {colors['window_fg_color']};
}}
headerbar {{
    background-color: {colors['headerbar_bg_color']};
    background-image: none;
    color: {colors['headerbar_fg_color']};
}}
windowcontrols button,
windowcontrols button image {{
    color: {colors['headerbar_fg_color']};
}}
/* Excludes .action-add/.action-next-turn (own styling in
   styling.py) and .close/.minimize/.maximize (would blank their
   theme icon images otherwise). */
headerbar button:not(.action-add):not(.action-next-turn):not(.close):not(.minimize):not(.maximize) {{
    background-color: transparent;
    background-image: none;
}}
headerbar button:not(.action-add):not(.action-next-turn):not(.close):not(.minimize):not(.maximize):hover,
headerbar button:not(.action-add):not(.action-next-turn):not(.close):not(.minimize):not(.maximize):checked {{
    background-color: alpha(currentColor, 0.12);
    background-image: none;
}}
separator {{
    background-color: alpha(currentColor, 0.15);
}}
columnview,
columnview > listview {{
    background-color: {colors['view_bg_color']};
    background-image: none;
    color: {colors['view_fg_color']};
}}
columnview header,
columnview header *,
columnview header button {{
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
entry {{
    background-color: {colors['view_bg_color']};
    background-image: none;
    color: {colors['view_fg_color']};
}}
popover {{
    background-color: transparent;
    background-image: none;
    color: {colors['popover_fg_color']};
}}
/* popover's actual surface is split across two child nodes
   (contents, arrow) per GTK4's own CSS node structure. */
popover > contents {{
    background-color: {colors['popover_bg_color']};
    background-image: none;
    color: {colors['popover_fg_color']};
}}
popover > arrow {{
    background-color: {colors['popover_bg_color']};
    background-image: none;
}}
popover modelbutton:hover,
popover modelbutton:active {{
    background-color: alpha(currentColor, 0.1);
    background-image: none;
}}
{highlight_css}
{destructive_css}
{_build_titlebutton_css(images)}
""".encode()


def _apply_theme():
    """Rebuilds and applies the CSS for the current theme state."""
    provider = _get_provider()
    if provider is None:
        return
    colors = _resolve_colors(_current_prefers_dark)
    images = _resolve_titlebutton_images(_current_theme_name, _current_prefers_dark)
    highlight = _find_highlight_colors(_current_theme_name, _current_prefers_dark)
    destructive = _find_destructive_colors(_current_theme_name, _current_prefers_dark)
    provider.load_from_data(_build_css(colors, images, highlight, destructive))
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
