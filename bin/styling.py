from gi.repository import Gdk, Gtk

CSS = b"""
.initiative-row {
    padding: 1px 0;
}
.action-add {
    background-color: #a8e6a3;
}
.action-next-turn {
    background-color: #a3c9e6;
}
.editable-cell {
    padding: 2px 4px;
    background-color: rgba(0, 0, 0, 0.03);
}
.editable-cell:hover {
    background-color: rgba(0, 0, 0, 0.08);
}
.round-counter {
    font-weight: bold;
    font-size: 1.15em;
}
/* Best-effort attempt to recolor GtkColumnView's native selected-row
   state to match the app's yellow, rather than the theme's default
   accent color. Not verified against a live GTK session -- the exact
   CSS node path for a selected row inside ColumnView's internal
   listview wasn't something documentation confirmed precisely, so this
   selector is an educated guess based on GTK's documented widget/CSS
   node naming conventions. If the highlight color doesn't change, GTK
   Inspector (Ctrl+Shift+D while running) would show the real node names
   to target here. */
columnview row:selected,
columnview row:selected:hover {
    background-color: #fff3b0;
    color: black;
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
