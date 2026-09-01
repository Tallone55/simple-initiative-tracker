"""Imports Mint Cinnamon's active theme (name, color palette, and
window-control button images) directly into this GTK4 app, rather than
relying on libadwaita -- which ignores the system theme unless an app
links against it, and Mint's Cinnamon theming doesn't reach GTK4 apps
natively the way it does GTK3 ones. Scoped deliberately to Cinnamon;
not a general cross-desktop abstraction.

Colors are read from the active theme's gtk-4.0/gtk[-dark].css file
where present, falling back to its libadwaita-1.X/defaults-*.css file
(themes without a gtk-4.0/ folder still ship this), and finally to
libadwaita's own stock defaults for any color a theme doesn't define.
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

# libadwaita's own published defaults, used for any color name a
# theme's own file doesn't define at all.
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
    if Cinnamon's GSettings schema isn't present on this system."""
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
    GSettings. Call once, after the main window has been constructed
    and presented -- theme CSS set before any window exists doesn't
    reliably reach icon-level styling on widgets that don't exist yet."""
    _apply_theme()


def _try_open_schema(schema_id):
    """Gio.Settings.new() on a schema that isn't installed hard-aborts
    the process rather than raising, so existence is checked first."""
    schema_source = Gio.SettingsSchemaSource.get_default()
    if schema_source is None or schema_source.lookup(schema_id, True) is None:
        return None
    return Gio.Settings.new(schema_id)


# -- Colors ------------------------------------------------

# Mint's own name for a shade slightly lighter than its main content
# color, used for the window canvas so it reads as a distinct surface
# from the table content below it (Mint's theme otherwise uses the
# same value for window_bg_color and view_bg_color).
_WINDOW_BG_HOVER_NAME = "mint_button_hover"


def _resolve_colors(dark):
    stock = _STOCK_DARK_DEFAULTS if dark else _STOCK_LIGHT_DEFAULTS
    discovered = _find_theme_colors(_current_theme_name, dark) if _current_theme_name else None
    discovered = discovered or {}
    resolved = {name: discovered.get(name, value) for name, value in stock.items()}

    if _WINDOW_BG_HOVER_NAME in discovered:
        resolved["window_bg_color"] = discovered[_WINDOW_BG_HOVER_NAME]
    else:
        # Theme doesn't define that name -- lighten view_bg_color
        # instead of leaving window_bg_color identical to it.
        resolved["window_bg_color"] = _lighten_hex(resolved["window_bg_color"])

    return resolved


def _find_theme_colors(theme_name, dark):
    """Tries the theme's stock GTK4 file first; several Mint theme
    families (e.g. Mint-L-*) ship no gtk-4.0/ folder at all, so this
    falls back to the theme's libadwaita-1.X/ file."""
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
    # Oldest libadwaita-1.X/ variant the theme ships, matching the
    # actually-installed libadwaita-1-0 version (1.5.0).
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
    """Returns {(button, state): (1x file:// URL, 2x file:// URL)} for
    the close/minimize/maximize titlebar button images, read from the
    theme's gtk-3.0/gtk[-dark].css file -- no GTK4 theme file provides
    an equivalent, and GTK4's real windowcontrols buttons don't carry
    GTK3's "titlebutton" class at all, so only the asset paths are
    reused here; the CSS built around them targets GTK4's own selectors."""
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
    """Converts an rgb()/rgba() color with an alpha channel into a flat
    #rrggbbaa hex color -- GTK's CSS parser on the target system
    rejects rgba()/rgb() nested inside alpha(). Values with no alpha
    channel are comma-normalized only; anything else passes through
    unchanged."""
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
    @other_name reference already parsed earlier in the file."""
    colors = {}
    for match in _DEFINE_COLOR_RE.finditer(css_text):
        name, value = match.group(1), match.group(2).strip()
        resolved = _REFERENCE_RE.sub(lambda m: colors.get(m.group(1), m.group(0)), value)
        colors[name] = _normalize_color_value(resolved)
    return colors


# -- Window-control images ------------------------------------------------

def _build_titlebutton_css(images):
    """Builds background-image rules for the window-control buttons
    from a resolved images dict; empty if the theme provides none, in
    which case those buttons just render with GTK's own default.

    Uses -gtk-scaled(url(1x), url(2x)) so GTK picks the right asset for
    the display's scale factor. background-color is cleared to
    transparent (the theme's per-state images already carry their own
    hover/press feedback), and each button's default GtkImage glyph is
    separately made transparent so it doesn't render underneath the
    background-image.
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
    (0-1). Non-6-digit-hex values are returned unchanged."""
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
    state. Reuses the same provider object across calls (rather than
    removing/re-adding it) so its position in the provider list -- and
    therefore its tiebreak priority against styling.py's provider,
    added after this one in do_startup -- stays constant."""
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
