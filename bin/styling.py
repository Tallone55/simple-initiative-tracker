from gi.repository import Gdk, Gtk

# .action-add / .action-next-turn use explicit hardcoded colors (rather
# than GTK4's paired @success_bg_color/@success_fg_color-style tokens,
# which aren't guaranteed to resolve to a mutually-compatible pair) and
# are scoped as "headerbar button.action-add" for the specificity
# needed to win over the theme's own headerbar-button styling.
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
/* Hitpoints cell at 0 HP -- a fixed, theme-independent pale red
   (rather than a theme-derived color) so it reads consistently as a
   status/alert indicator regardless of the active theme's palette. */
.editable-cell.zero-hp,
.editable-cell.zero-hp:hover {
    background-color: #f5c6cb;
    color: #6b1f27;
}
/* The round counter is a real button (clicking it opens the Set
   Round dialog), styled flat here so it still reads as plain,
   centered text at rest -- background-image: none and border/
   box-shadow: none defeat the active theme's own default button
   chrome (gradients, borders) the same way headerbar buttons
   elsewhere in this file need to; the two states below give it
   subtle, theme-relative (not hardcoded) feedback instead. */
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
/* Recolors the ColumnView's native selected-row state (used for the
   current-turn highlight) to the current GTK theme's own selection/
   highlight color, via GTK's standard named colors -- desktop-
   agnostic (works under any GTK theme, not just Cinnamon's) and
   already falls back to GTK's own built-in defaults when nothing
   else defines these. This is the baseline: on a system where
   cinnamon_theme.py manages to resolve the active theme's actual
   accent color itself (which GTK's own named-color lookup can miss
   -- see _find_highlight_colors there), its provider is installed
   after this one and its more specific value wins instead. */
columnview row:selected,
columnview row:selected:hover {
    background-color: @theme_selected_bg_color;
    color: @theme_selected_fg_color;
}
/* Titlebar (window-control) buttons otherwise inherit the theme's
   default animated transition between hover/backdrop/active states;
   these should switch instantly instead. */
windowcontrols button,
windowcontrols button image {
    transition: none;
}
/* Remove and Edit Stats (crossed-swords) column buttons: a visible
   background at rest, not just on hover, so both read as clickable
   controls sitting in the table rather than plain glyphs -- matches
   .editable-cell's own alpha(currentColor, ...) approach (theme-
   relative, not a hardcoded color) but a bit stronger, appropriate
   for a small icon-only button rather than a full text cell.
   background-image: none defeats the active theme's own default
   button chrome, same reasoning as headerbar buttons elsewhere in
   this file. */
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
/* The crossed-swords glyph itself, 50% larger than the button's
   surrounding (inherited) text size. */
.stats-button {
    font-size: 1.5em;
}
/* Each ability's row in the stat-block editor window
   (creature_stats_dialog.py) -- a visibly bordered, rounded-corner
   "card" so the six rows read as distinct groups rather than one
   continuous block; alpha(currentColor, ...) again for a
   theme-relative border rather than a hardcoded color. */
.stat-row {
    border: 1px solid alpha(currentColor, 0.2);
    border-radius: 10px;
    background-color: alpha(currentColor, 0.03);
}
"""


def install_css():
    """Registers the CSS above as a global style provider. Called once
    from Application.do_startup."""
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
