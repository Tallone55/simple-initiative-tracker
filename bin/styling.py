from gi.repository import Gdk, Gtk

CSS = b"""
.action-add {
    background-color: #a8e6a3;
}
.action-next-turn {
    background-color: #a3c9e6;
}
.editable-cell {
    padding: 8px 12px;
    background-color: rgba(0, 0, 0, 0.03);
}
.editable-cell:hover {
    background-color: rgba(0, 0, 0, 0.08);
}
.round-counter {
    font-weight: bold;
    font-size: 1.15em;
}
/* Recolors Gtk.ColumnView's native selected-row state (used for the
   current-turn highlight) to the app's yellow, rather than the theme's
   default accent color. */
columnview row:selected,
columnview row:selected:hover {
    background-color: #fff3b0;
    color: black;
}
"""


def install_css():
    """Registers CSS above as a global style provider, applied to
    every widget in the app. Called once from Application.do_startup."""
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
