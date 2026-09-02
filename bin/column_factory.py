"""Builds the Gtk.ColumnView columns for creature entries.

The current-turn highlight is driven by native row selection (a
Gtk.SingleSelection on the ColumnView, configured in AppWindow) rather
than a per-cell CSS class. Turn activation (double-click) is handled
via Gtk.ColumnView's own "activate" signal in AppWindow, not here --
each field's click handling below deliberately leaves its
Gtk.GestureClick unclaimed, so the same click also reaches the row's
native selection handling underneath.

Gtk.ColumnViewColumn has no min-width property and auto-grows to fit
its content unless given an explicit fixed-width, so each column here
gets both a starting fixed-width and a floor enforced against further
drags (see _enforce_min_width).
"""

from gi.repository import Gtk, Pango


class CreatureColumnFactory:
    """Builds the list of Gtk.ColumnViewColumn objects for the creature
    table: one column per displayed field, plus a remove-icon column.
    Construct once per AppWindow and pass self.columns to a
    Gtk.ColumnView.
    """

    def __init__(
        self,
        on_edit_requested,
        on_hitpoints_edit_requested,
        on_remove_requested,
    ):
        """on_edit_requested(creature_obj, field_name, display_name) is
        called on a click on the Creature/Armor Class/Initiative
        Roll/Status cell. on_hitpoints_edit_requested(creature_obj) is
        called on the Hitpoints cell (routed separately since it opens
        a dedicated current/max/temp HP dialog). on_remove_requested(creature_obj)
        is called when a row's remove button is clicked."""
        self.on_edit_requested = on_edit_requested
        self.on_hitpoints_edit_requested = on_hitpoints_edit_requested
        self.on_remove_requested = on_remove_requested

        self.columns = [
            self._build_field_column(
                title="Creature",
                getter=lambda c: c.name,
                notify_props=["name"],
                on_click=lambda c: self.on_edit_requested(c, "name", "Creature"),
                min_width=140,
            ),
            self._build_field_column(
                title="Hitpoints",
                getter=self._format_hitpoints,
                notify_props=["hitpoints", "max-hitpoints", "temp-hitpoints"],
                on_click=lambda c: self.on_hitpoints_edit_requested(c),
                min_width=140,
                zero_hp_highlight=True,
            ),
            self._build_field_column(
                title="Armor Class",
                getter=lambda c: str(c.armor_class),
                notify_props=["armor-class"],
                on_click=lambda c: self.on_edit_requested(c, "armor_class", "Armor Class"),
                min_width=110,
            ),
            self._build_field_column(
                title="Initiative Roll",
                getter=lambda c: str(c.initiative_roll),
                notify_props=["initiative-roll"],
                on_click=lambda c: self.on_edit_requested(c, "initiative_roll", "Initiative Roll"),
                min_width=120,
            ),
            self._build_field_column(
                title="Status",
                getter=lambda c: c.status,
                notify_props=["status"],
                on_click=lambda c: self.on_edit_requested(c, "status", "Status"),
                expand=True,
                min_width=100,
            ),
            self._build_remove_column(min_width=48),
        ]

    @staticmethod
    def _format_hitpoints(creature_obj):
        """Display text for the Hitpoints cell: "current/max", with a
        "+ N temp" suffix appended whenever there's any temporary HP
        (D&D-style temp HP, tracked separately rather than added into
        current/max)."""
        base = f"{creature_obj.hitpoints}/{creature_obj.max_hitpoints}"
        if creature_obj.temp_hitpoints > 0:
            return f"{base} + {creature_obj.temp_hitpoints} temp"
        return base

    # -- generic text-cell column ------------------------------------------------

    def _build_field_column(self, title, getter, notify_props, on_click, expand=False, min_width=80, zero_hp_highlight=False):
        """Builds one resizable, ellipsizing text column. getter(creature_obj)
        -> str produces the cell's display text; notify_props (dash-case
        GObject property names) is which CreatureObject properties
        should trigger a refresh via "notify::"; on_click(creature_obj)
        fires on a cell click; expand controls whether this column
        soaks up extra ColumnView width. zero_hp_highlight marks the
        cell with the "zero-hp" CSS class (styling.py) whenever the
        creature is at 0 hitpoints -- only meaningful for the
        Hitpoints column, which already includes "hitpoints" in
        notify_props."""
        factory = Gtk.SignalListItemFactory()

        def on_setup(factory, list_item):
            label = Gtk.Label(label="", xalign=0, hexpand=True)
            label.add_css_class("editable-cell")
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_overflow(Gtk.Overflow.HIDDEN)
            label.set_cursor_from_name("pointer")
            # Stops the column from being dragged down to (or below)
            # zero, since a resizable column's floor is derived from
            # its cells' actual size requests.
            label.set_size_request(min_width, -1)

            click_gesture = Gtk.GestureClick()
            click_gesture.set_button(1)  # left click only
            label.add_controller(click_gesture)

            list_item.set_child(label)
            list_item.notify_handler_ids = []
            list_item.click_gesture = click_gesture
            list_item.click_handler_id = None

        def on_bind(factory, list_item):
            creature_obj = list_item.get_item()
            label = list_item.get_child()

            def refresh(*_args):
                label.set_label(getter(creature_obj))
                if zero_hp_highlight:
                    if creature_obj.hitpoints == 0:
                        label.add_css_class("zero-hp")
                    else:
                        label.remove_css_class("zero-hp")
            refresh()

            list_item.notify_handler_ids = [
                creature_obj.connect(f"notify::{prop}", refresh) for prop in notify_props
            ]

            def handle_click(gesture, n_press, x, y):
                # Every click opens the edit dialog; turn activation
                # (double-click) is handled by the ColumnView's own
                # "activate" signal in AppWindow. Left unclaimed so the
                # click also reaches the row's native selection
                # handling, corrected by _sync_selection() afterward.
                on_click(creature_obj)

            list_item.click_handler_id = list_item.click_gesture.connect(
                "released", handle_click
            )

        def on_unbind(factory, list_item):
            creature_obj = list_item.get_item()
            for hid in list_item.notify_handler_ids:
                creature_obj.disconnect(hid)
            list_item.notify_handler_ids = []

            if list_item.click_handler_id is not None:
                list_item.click_gesture.disconnect(list_item.click_handler_id)
                list_item.click_handler_id = None

        factory.connect("setup", on_setup)
        factory.connect("bind", on_bind)
        factory.connect("unbind", on_unbind)

        column = Gtk.ColumnViewColumn(title=title, factory=factory)
        column.set_resizable(True)
        column.set_expand(expand)
        # A real starting width (rather than -1/auto) gives long
        # content a fixed budget to ellipsize against, instead of just
        # growing the column.
        column.set_fixed_width(min_width)
        self._enforce_min_width(column, min_width)
        return column

    @staticmethod
    def _enforce_min_width(column, min_width):
        """Gtk.ColumnViewColumn has no min-width property, so this
        watches fixed-width and snaps it back up if a drag pushes it
        below the floor. -1 ("unset / natural sizing") is left alone."""
        def on_notify_fixed_width(col, _pspec):
            width = col.get_fixed_width()
            if width != -1 and width < min_width:
                col.set_fixed_width(min_width)

        column.connect("notify::fixed-width", on_notify_fixed_width)

    # -- remove (trash-can icon) column ------------------------------------------------

    def _build_remove_column(self, min_width=48):
        """Builds the fixed-width, non-resizable icon column used to
        remove a creature from the list."""
        factory = Gtk.SignalListItemFactory()

        def on_setup(factory, list_item):
            button = Gtk.Button.new_from_icon_name("user-trash-symbolic")
            button.set_tooltip_text("Remove")
            button.add_css_class("flat")
            button.set_overflow(Gtk.Overflow.HIDDEN)
            # Centered rather than forced to fill the full column width
            # (which left it flush against one edge) -- the column's
            # own fixed_width already gives the cell its width, so the
            # button just needs to center within it.
            button.set_halign(Gtk.Align.CENTER)
            button.set_valign(Gtk.Align.CENTER)
            list_item.set_child(button)
            list_item.click_handler_id = None

        def on_bind(factory, list_item):
            creature_obj = list_item.get_item()
            button = list_item.get_child()
            list_item.click_handler_id = button.connect(
                "clicked", lambda b: self.on_remove_requested(creature_obj)
            )

        def on_unbind(factory, list_item):
            button = list_item.get_child()
            if list_item.click_handler_id is not None:
                button.disconnect(list_item.click_handler_id)
                list_item.click_handler_id = None

        factory.connect("setup", on_setup)
        factory.connect("bind", on_bind)
        factory.connect("unbind", on_unbind)

        column = Gtk.ColumnViewColumn(title="", factory=factory)
        column.set_resizable(False)
        column.set_fixed_width(min_width)
        return column
