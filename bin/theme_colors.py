"""Reads the color palette a GTK theme provides for libadwaita apps
(window_bg_color, view_bg_color, headerbar_bg_color, popover_bg_color,
and their _fg_color counterparts) directly from that theme's own files
on disk, rather than hardcoding any specific theme's values -- for
BOTH light and dark, symmetrically.

Why this exists: stock libadwaita ignores the system GTK theme by
design (see theme_sync.py's module docstring) -- but some distros,
confirmed concretely for Linux Mint, ship a patched libadwaita that
DOES read theme-provided colors, via libadwaita-1.X/defaults-{dark,
light}.css files inside the theme's own folder. This is a mechanism
separate from (and not to be confused with) the theme's plain
gtk-4.0/ folder -- Mint-L-Dark-Aqua, for example, has no gtk-4.0/
folder at all, but does have libadwaita-1.5/defaults-dark.css.

Reading this directly, rather than hand-copying values observed once
on one particular system, means the resolved palette automatically
follows whatever theme (and theme variant, and light/dark mode) is
actually active on whatever system this runs on, without special-
casing any specific theme by name -- and degrades gracefully (see
resolve_colors) on a system that doesn't provide this at all.
"""

import re
from pathlib import Path

_DEFINE_COLOR_RE = re.compile(r"@define-color\s+([\w-]+)\s+([^;]+);")
_REFERENCE_RE = re.compile(r"@([\w-]+)")

# Standard GTK theme search locations, in priority order (user-local
# overrides system-wide, matching how GTK itself resolves theme names).
_THEME_SEARCH_ROOTS = [
    Path.home() / ".themes",
    Path.home() / ".local" / "share" / "themes",
    Path("/usr/share/themes"),
]

# libadwaita's own published defaults for each mode -- used only for
# names a theme's own file doesn't define, or when no theme-provided
# file could be found/parsed at all. Not a guess: taken directly from
# libadwaita's official CSS variables documentation.
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
    "window_fg_color": "rgb(0 0 6 / 80%)",
    "view_bg_color": "#ffffff",
    "view_fg_color": "rgb(0 0 6 / 80%)",
    "headerbar_bg_color": "#ffffff",
    "headerbar_fg_color": "rgb(0 0 6 / 80%)",
    "popover_bg_color": "#ffffff",
    "popover_fg_color": "rgb(0 0 6 / 80%)",
}


def resolve_colors(theme_name, dark):
    """Returns a dict covering exactly the named colors this app
    needs, for whichever mode `dark` selects -- preferring values read
    from theme_name's own libadwaita-1.X/defaults-{dark,light}.css
    where available, and falling back to libadwaita's stock published
    defaults (for that same mode) for any name that file doesn't
    define -- or for every name, if theme_name is None or no such file
    could be found/parsed at all. Never fails; always returns a
    complete dict."""
    stock = _STOCK_DARK_DEFAULTS if dark else _STOCK_LIGHT_DEFAULTS
    discovered = find_theme_colors(theme_name, dark) if theme_name else None
    discovered = discovered or {}
    return {name: discovered.get(name, value) for name, value in stock.items()}


def find_theme_colors(theme_name, dark):
    """Returns a dict of libadwaita named-color -> CSS value pairs
    read directly from theme_name's own dark- or light-variant file,
    or None if this theme doesn't provide one (no libadwaita-1.X/
    folder found, or nothing parseable inside it)."""
    theme_dir = _find_theme_dir(theme_name)
    if theme_dir is None:
        return None

    css_path = _find_defaults_css(theme_dir, dark)
    if css_path is None:
        return None

    try:
        css_text = css_path.read_text(encoding="utf-8")
    except OSError:
        return None

    return _parse_define_colors(css_text) or None


def _find_theme_dir(theme_name):
    for root in _THEME_SEARCH_ROOTS:
        candidate = root / theme_name
        if candidate.is_dir():
            return candidate
    return None


def _find_defaults_css(theme_dir, dark):
    """Picks the newest libadwaita-1.X/ variant the theme ships, if
    more than one is present (Mint themes ship both 1.5 and 1.7, for
    instance, regardless of which is actually installed). A plain
    string sort is good enough here -- libadwaita minor versions are
    nowhere near reaching double digits, where lexicographic sorting
    of version strings would start giving the wrong answer."""
    filename = "defaults-dark.css" if dark else "defaults-light.css"
    candidates = sorted(theme_dir.glob(f"libadwaita-*/{filename}"))
    return candidates[-1] if candidates else None


def _parse_define_colors(css_text):
    """Extracts @define-color name -> value pairs, substituting any
    @other_name reference already parsed earlier in the same file --
    whether the ENTIRE value is a bare reference (@define-color
    headerbar_bg_color @window_bg_color;) or a reference embedded in a
    larger expression (@define-color x alpha(@window_bg_color, 0.9);),
    since theme files use both forms. A reference to a name not yet
    parsed is left as the literal "@name" text; that specific
    declaration then simply fails to resolve at the GTK level (since
    we never define "@name" ourselves), which resolve_colors's
    per-name .get() fallback doesn't catch on its own -- worth knowing
    if a specific color still looks wrong after this: it likely means
    the theme file defines it via something more complex than either
    of these two forms.
    """
    colors = {}
    for match in _DEFINE_COLOR_RE.finditer(css_text):
        name, value = match.group(1), match.group(2).strip()
        colors[name] = _REFERENCE_RE.sub(lambda m: colors.get(m.group(1), m.group(0)), value)
    return colors
