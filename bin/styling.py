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
.round-counter {
    font-weight: bold;
    font-size: 1.15em;
}
/* Recolors the ColumnView's native selected-row state (used for the
   current-turn highlight) to a fixed amber. */
columnview row:selected,
columnview row:selected:hover {
    background-color: #f5c451;
    color: #3d2b00;
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
