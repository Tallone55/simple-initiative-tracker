"""Builds the Gtk.ColumnView columns for creature entries.

Gtk.ColumnView (rather than a hand-built Gtk.ListView row) is what gives
us resizable columns whose header and body cells stay aligned for free --
that alignment/resize behavior is built into the widget, not something we
maintain by hand.

Each field gets its own Gtk.ColumnViewColumn with its own tiny factory.
Since there's no single "row" widget spanning a whole row (each column
renders its own cells independently), the current-turn highlight is
applied per-cell across every column for that creature -- tracked here
via cell_registry.
"""

from gi.repository import Gtk


class CreatureColumnFactory:
    def __init__(
        self,
        on_edit_requested,
        on_hitpoints_edit_requested,
        on_remove_requested,
        is_current_fn,
    ):
        """
        on_edit_requested(creature_obj, field_name, display_name) -- called
            when the Creature / Armor Class / Initiative Roll cell is
            clicked.
        on_hitpoints_edit_requested(creature_obj) -- called when the
            Hitpoints cell is clicked (routed separately since it opens a
            dedicated current/max HP dialog rather than the generic
            text-field editor).
        on_remove_requested(creature_obj) -- called when a row's remove
            button is clicked.
        is_current_fn(creature_obj) -> bool -- used to decide whether a
            creature's cells should show the current-turn highlight.
        """
        self.on_edit_requested = on_edit_requested
        self.on_hitpoints_edit_requested = on_hitpoints_edit_requested
        self.on_remove_requested = on_remove_requested
        self.is_current_fn = is_current_fn

        # id(CreatureObject) -> list[(widget, creature_obj)]
        self.cell_registry = {}

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
        return f"{creature_obj.hitpoints}/{creature_obj.max_hitpoints}"

    # -- generic text-cell column ------------------------------------------------

    def _build_field_column(self, title, getter, notify_props, on_click, expand=False, min_width=80):
        factory = Gtk.SignalListItemFactory()

        def on_setup(factory, list_item):
            # label="" up front guarantees the button already has an
            # internal Label child, so get_child() below is never None.
            button = Gtk.Button(label="", hexpand=True)
            button.add_css_class("flat")
            button.get_child().set_xalign(0)
            # Gtk.ColumnViewColumn has no min-width property of its own --
            # a resizable column's floor is derived from its cells' actual
            # size requests, so this is what stops the column from being
            # dragged down to (or below) zero and overlapping its neighbors.
            button.set_size_request(min_width, -1)
            list_item.set_child(button)
            list_item.notify_handler_ids = []
            list_item.click_handler_id = None

        def on_bind(factory, list_item):
            creature_obj = list_item.get_item()
            button = list_item.get_child()

            def refresh(*_args):
                button.set_label(getter(creature_obj))
            refresh()

            list_item.notify_handler_ids = [
                creature_obj.connect(f"notify::{prop}", refresh) for prop in notify_props
            ]
            list_item.click_handler_id = button.connect(
                "clicked", lambda b: on_click(creature_obj)
            )

            self._register_cell(creature_obj, button)

        def on_unbind(factory, list_item):
            creature_obj = list_item.get_item()
            for hid in list_item.notify_handler_ids:
                creature_obj.disconnect(hid)
            list_item.notify_handler_ids = []

            if list_item.click_handler_id is not None:
                list_item.get_child().disconnect(list_item.click_handler_id)
                list_item.click_handler_id = None

            self._unregister_cell(creature_obj, list_item.get_child())

        factory.connect("setup", on_setup)
        factory.connect("bind", on_bind)
        factory.connect("unbind", on_unbind)

        column = Gtk.ColumnViewColumn(title=title, factory=factory)
        column.set_resizable(True)
        column.set_expand(expand)
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
        factory = Gtk.SignalListItemFactory()

        def on_setup(factory, list_item):
            button = Gtk.Button.new_from_icon_name("user-trash-symbolic")
            button.set_tooltip_text("Remove")
            button.add_css_class("flat")
            button.set_size_request(min_width, -1)
            list_item.set_child(button)
            list_item.click_handler_id = None

        def on_bind(factory, list_item):
            creature_obj = list_item.get_item()
            button = list_item.get_child()
            list_item.click_handler_id = button.connect(
                "clicked", lambda b: self.on_remove_requested(creature_obj)
            )
            self._register_cell(creature_obj, button)

        def on_unbind(factory, list_item):
            creature_obj = list_item.get_item()
            button = list_item.get_child()
            if list_item.click_handler_id is not None:
                button.disconnect(list_item.click_handler_id)
                list_item.click_handler_id = None
            self._unregister_cell(creature_obj, button)

        factory.connect("setup", on_setup)
        factory.connect("bind", on_bind)
        factory.connect("unbind", on_unbind)

        column = Gtk.ColumnViewColumn(title="", factory=factory)
        column.set_resizable(False)
        return column

    # -- current-turn highlight tracking ------------------------------------------------

    def _register_cell(self, creature_obj, widget):
        self.cell_registry.setdefault(id(creature_obj), []).append((widget, creature_obj))
        self._apply_highlight(widget, creature_obj)

    def _unregister_cell(self, creature_obj, widget):
        key = id(creature_obj)
        cells = self.cell_registry.get(key)
        if not cells:
            return
        remaining = [(w, c) for w, c in cells if w is not widget]
        if remaining:
            self.cell_registry[key] = remaining
        else:
            del self.cell_registry[key]

    def _apply_highlight(self, widget, creature_obj):
        if self.is_current_fn(creature_obj):
            widget.add_css_class("current-turn")
        else:
            widget.remove_css_class("current-turn")

    def refresh_highlights(self):
        """Call after anything that could change which creature is
        current (next turn, add, remove, import)."""
        for cells in list(self.cell_registry.values()):
            for widget, creature_obj in cells:
                self._apply_highlight(widget, creature_obj)
