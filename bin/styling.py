from gi.repository import Gdk, Gtk

CSS = b"""
.current-turn {
    background-color: #fff3b0;
}
.initiative-row {
    padding: 2px 0;
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
