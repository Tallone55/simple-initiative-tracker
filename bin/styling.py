from gi.repository import Gdk, Gtk

# .action-add / .action-next-turn use explicit hardcoded colors
# (background + matching text color chosen together for guaranteed
# contrast) rather than GTK4's paired named theme colors
# (@success_bg_color + @success_fg_color, etc.) -- those are two
# independent named tokens rather than one guaranteed-to-resolve
# reference, so there's no guarantee they resolve to a *compatible*
# pair even when each individually resolves to something.
#
# The selectors are scoped as "headerbar button.action-add" rather
# than plain ".action-add", giving them higher specificity than a
# single-class selector alone -- needed for the background to actually
# render as a fill rather than being overridden by the theme's own,
# more specific headerbar-button styling. background-image is
# explicitly reset too, since a theme can paint a button's background
# via a gradient image that sits on top of (and isn't cleared by)
# background-color alone.
#
# .editable-cell's alpha(currentColor, ...) is a different, safer
# mechanism (a single reference that's always well-defined in context,
# not two independent tokens that could disagree) and needs none of
# this extra specificity.
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
/* Recolors Gtk.ColumnView's native selected-row state (used for the
   current-turn highlight) to a fixed amber, keeping the established
   "amber = current turn" visual language with guaranteed contrast. */
columnview row:selected,
columnview row:selected:hover {
    background-color: #f5c451;
    color: #3d2b00;
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
