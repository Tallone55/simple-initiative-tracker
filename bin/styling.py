from gi.repository import Gdk, Gtk

import os

# No font is bundled with this app -- these are each platform's own
# native UI font, present by default on every target this ships for,
# rather than something that needs installing. Segoe UI ships with
# every Windows release since Vista; Helvetica Neue with every macOS
# release; Cantarell is GNOME's (and, by extension, Cinnamon/Mint's)
# own default, with DejaVu Sans and Noto Sans as further, extremely
# commonly-preinstalled Linux fallbacks before the final generic
# sans-serif. Applied on the root `window` selector specifically so
# it's inherited everywhere as CSS's own normal default, rather than
# needing to be repeated on every individual widget selector below.
#
# Loaded at Gtk.STYLE_PROVIDER_PRIORITY_THEME (200) -- deliberately
# its own, separate, lower-priority provider from the rest of this
# file's CSS (which stays at PRIORITY_APPLICATION, 600, for the real
# app-specific style overrides below). THEME sits below
# PRIORITY_SETTINGS (400), the level a desktop's own global font
# choice (gtk-font-name, the thing GTK Inspector's own font override
# changes) applies at -- so a real, deliberately-configured system
# font now wins over this rule, the reverse of how this worked when
# it loaded at APPLICATION alongside everything else (confirmed
# directly: at APPLICATION, changing the font via Inspector had no
# visible effect at all, precisely because 600 outranks 400 regardless
# of what Inspector sets). This was always meant to be a fallback for
# platforms where fontconfig has nothing sensible configured, not a
# forced override of a real configured choice -- THEME priority is
# what actually makes it behave that way. Set
# SIT_DISABLE_FONT_OVERRIDE=1 to skip loading this rule entirely (the
# rest of this file's CSS still loads normally), for isolating this
# specific rule from everything else while diagnosing a rendering
# issue, independent of the priority question above.
_FONT_OVERRIDE_CSS = b"""
window {
    font-family: "Segoe UI", "Cantarell", "Helvetica Neue", "DejaVu Sans", "Noto Sans", sans-serif;
}
"""

CSS = b"""
headerbar button.action-add {
    background-color: #7cc47f;
    background-image: none;
    color: #0d3d0f;
    font-weight: bold;
}
headerbar button.action-add:hover {
    background-color: #6dac70;
}
headerbar button.action-add:active {
    background-color: #619963;
}
headerbar button.action-next-turn {
    background-color: #5b9bd5;
    background-image: none;
    color: #0a2d4d;
    font-weight: bold;
}
headerbar button.action-next-turn:hover {
    background-color: #5088bb;
}
headerbar button.action-next-turn:active {
    background-color: #4779a6;
}
.editable-cell {
    padding: 8px 12px;
    background-color: alpha(currentColor, 0.05);
}
.editable-cell:hover {
    background-color: alpha(currentColor, 0.1);
}
/* Hitpoints cell at 0 HP -- fixed, theme-independent alert color. */
.editable-cell.zero-hp,
.editable-cell.zero-hp:hover {
    background-color: #f5c6cb;
    color: #6b1f27;
}
/* Edit Stats window: the calculated save/skill total next to each
   one's own proficiency controls (e.g. "+0", "+5") -- distinct from
   the raw ability score and Prof./To-Hit Bonus entries next to it,
   which are typed in directly rather than derived from them. */
.stat-total {
    font-weight: bold;
}
.round-counter {
    font-weight: bold;
    font-size: 1.15em;
    background-color: transparent;
    background-image: none;
    border: none;
    box-shadow: none;
    padding: 2px 10px;
}
.round-counter:hover {
    background-color: alpha(currentColor, 0.1);
    background-image: none;
}
.round-counter:active {
    background-color: alpha(currentColor, 0.18);
    background-image: none;
}
/* Current-turn row highlight; cinnamon_theme.py's provider, installed
   after this one, overrides with the resolved theme accent when
   available. */
columnview row:selected,
columnview row:selected:hover {
    background-color: @theme_selected_bg_color;
    color: @theme_selected_fg_color;
}
windowcontrols button,
windowcontrols button image {
    transition: none;
}
.icon-cell-button {
    background-color: alpha(currentColor, 0.1);
    background-image: none;
    border-radius: 6px;
}
.icon-cell-button:hover {
    background-color: alpha(currentColor, 0.18);
    background-image: none;
}
.icon-cell-button:active {
    background-color: alpha(currentColor, 0.26);
    background-image: none;
}
/* Sized to match the Remove column's icon button (36x34) exactly. */
.stats-button {
    font-size: 1.2em;
    padding: 4px 10px;
    min-width: 0;
}
.stat-row {
    border: 1px solid alpha(currentColor, 0.2);
    border-radius: 10px;
    background-color: alpha(currentColor, 0.03);
}
"""


def install_css():
    if os.environ.get("SIT_DISABLE_FONT_OVERRIDE") != "1":
        font_provider = Gtk.CssProvider()
        font_provider.load_from_data(_FONT_OVERRIDE_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            font_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_THEME,
        )

    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
