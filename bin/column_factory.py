"""Builds the Gtk.ColumnView columns for creature entries.

Gtk.ColumnView (rather than a hand-built Gtk.ListView row) gives us
resizable columns whose header and body cells stay aligned automatically
-- that behavior is built into the widget, not something maintained by
hand here.

The current-turn highlight is driven by native row selection (a
Gtk.SingleSelection on the ColumnView, configured in AppWindow) rather
than a per-cell CSS class, since native selection highlights the whole
row correctly with no extra work required here.

Turn activation (double-click) is handled via Gtk.ColumnView's own
"activate" signal in AppWindow, not in this module. Each field's click
handling here deliberately leaves its Gtk.GestureClick unclaimed, so the
same click also reaches the row's native selection handling underneath.

Gtk.ColumnViewColumn has no min-width property, and auto-grows to fit
its content's natural size unless given an explicit starting
fixed-width. Each column here is given both: a starting fixed-width (so
unusually long content has a real budget to ellipsize against, instead
of just growing the column) and a floor enforced against further drags
via _enforce_min_width (see its docstring for why that needs watching a
signal rather than just being a fixed property).
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
        """
        on_edit_requested(creature_obj, field_name, display_name) -- called
            on a click on the Creature / Armor Class / Initiative Roll cell.
        on_hitpoints_edit_requested(creature_obj) -- called on a click on
            the Hitpoints cell (routed separately since it opens a
            dedicated current/max HP dialog rather than the generic
            text-field editor).
        on_remove_requested(creature_obj) -- called when a row's remove
            button is clicked.

        Turn activation (double-click) is handled separately, at the
        Gtk.ColumnView level in AppWindow -- not here. See the module
        docstring for why.
        """
        self.on_edit_requested = on_edit_requested
        self.on_hitpoints_edit_requested = on_hitpoints_edit_requested
        self.on_remove_requested = on_remove_requested

        self.columns = [
            self._build_field_column(
                title="Creature",
                getter=lambda c: c.name,
                notify_props=["name"],
                on_click=lambda c: self.on_edit_requested(c, "name", "Creature"),
                expand=True,
                min_width=140,
            ),
            self._build_field_column(
                title="Hitpoints",
                getter=self._format_hitpoints,
                notify_props=["hitpoints", "max-hitpoints"],
                on_click=lambda c: self.on_hitpoints_edit_requested(c),
                min_width=90,
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
            self._build_remove_column(min_width=48),
        ]

    @staticmethod
    def _format_hitpoints(creature_obj):
        """Display text for the Hitpoints cell: "current/max"."""
        return f"{creature_obj.hitpoints}/{creature_obj.max_hitpoints}"

    # -- generic text-cell column ------------------------------------------------

    def _build_field_column(self, title, getter, notify_props, on_click, expand=False, min_width=80):
        """Builds one resizable, ellipsizing text column.

        getter(creature_obj) -> str produces the cell's display text.
        notify_props is the list of GObject property names (dash-case)
        whose "notify::" signal should re-run getter and refresh the
        label -- i.e. which CreatureObject properties this column's text
        depends on. on_click(creature_obj) is called when the cell is
        clicked. expand controls whether this column soaks up extra
        Gtk.ColumnView width beyond the sum of all columns' widths.
        """
        factory = Gtk.SignalListItemFactory()

        def on_setup(factory, list_item):
            label = Gtk.Label(label="", xalign=0, hexpand=True)
            label.add_css_class("editable-cell")
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_overflow(Gtk.Overflow.HIDDEN)
            label.set_cursor_from_name("pointer")
            # Gtk.ColumnViewColumn has no min-width property of its own --
            # a resizable column's floor is derived from its cells' actual
            # size requests, so this is what stops the column from being
            # dragged down to (or below) zero and overlapping its neighbors.
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
            refresh()

            list_item.notify_handler_ids = [
                creature_obj.connect(f"notify::{prop}", refresh) for prop in notify_props
            ]

            def handle_click(gesture, n_press, x, y):
                # Every click opens the edit dialog; turn activation
                # (double-click) is handled separately, by the
                # ColumnView's own "activate" signal in AppWindow.
                on_click(creature_obj)
                # Left unclaimed so the click also reaches the row's
                # native selection handling -- causes the same
                # transient visual selection here that clicking row
                # background does, corrected by AppWindow._sync_selection()
                # after any real state change.

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
        # Without an explicit starting fixed-width, the column auto-grows
        # to fit its content's natural size -- so an unusually long value
        # would just widen the column rather than ever get ellipsized.
        # Giving it a real starting width (rather than leaving it at -1
        # / auto) means long content actually has a fixed budget to
        # overflow against.
        column.set_fixed_width(min_width)
        self._enforce_min_width(column, min_width)
        return column

    @staticmethod
    def _enforce_min_width(column, min_width):
        """Gtk.ColumnViewColumn has no min-width property -- resizable
        columns just have their fixed-width set directly to the drag
        position, with no clamping against content size. So instead we
        watch fixed-width itself and snap it back up if a drag pushes it
        below our floor. -1 means "unset / natural sizing", which we
        leave alone.
        """
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
            button.set_size_request(min_width, -1)
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
