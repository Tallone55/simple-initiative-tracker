from gi.repository import Gdk, Gtk

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
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
