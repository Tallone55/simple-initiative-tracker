"""Builds the Gtk.ColumnView columns for creature entries."""

from gi.repository import Gtk, Pango


class CreatureColumnFactory:
    """Builds the list of Gtk.ColumnViewColumn objects for the creature
    table. Construct once per AppWindow and pass self.columns to a
    Gtk.ColumnView."""

    def __init__(
        self,
        on_edit_requested,
        on_hitpoints_edit_requested,
        on_remove_requested,
        on_stats_requested,
    ):
        """on_edit_requested(creature_obj, field_name, display_name),
        on_hitpoints_edit_requested(creature_obj),
        on_stats_requested(creature_obj), on_remove_requested(
        creature_obj) fire on the corresponding cell/button click."""
        self.on_edit_requested = on_edit_requested
        self.on_hitpoints_edit_requested = on_hitpoints_edit_requested
        self.on_remove_requested = on_remove_requested
        self.on_stats_requested = on_stats_requested

        self._combat_only_columns = [self._build_stats_column(min_width=48)]
        for column in self._combat_only_columns:
            column.set_visible(False)

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
            *self._combat_only_columns,
            self._build_remove_column(min_width=48),
        ]

    def set_combat_columns_visible(self, visible):
        for column in self._combat_only_columns:
            column.set_visible(visible)

    def _build_stats_column(self, min_width=48):
        """The 5e Combat-mode-only column: a crossed-swords button that
        opens the full stat-block editor."""
        factory = Gtk.SignalListItemFactory()

        def on_setup(factory, list_item):
            button = Gtk.Button(label="\u2694")  # crossed swords
            button.set_tooltip_text("Edit Stats")
            button.add_css_class("flat")
            button.add_css_class("icon-cell-button")
            button.add_css_class("stats-button")
            button.set_overflow(Gtk.Overflow.HIDDEN)
            button.set_halign(Gtk.Align.CENTER)
            button.set_valign(Gtk.Align.CENTER)
            list_item.set_child(button)
            list_item.click_handler_id = None

        def on_bind(factory, list_item):
            creature_obj = list_item.get_item()
            button = list_item.get_child()
            list_item.click_handler_id = button.connect(
                "clicked", lambda b: self.on_stats_requested(creature_obj)
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

    @staticmethod
    def _format_hitpoints(creature_obj):
        base = f"{creature_obj.hitpoints}/{creature_obj.max_hitpoints}"
        if creature_obj.temp_hitpoints > 0:
            return f"{base} + {creature_obj.temp_hitpoints} temp"
        return base

    # -- generic text-cell column ------------------------------------------------

    def _build_field_column(self, title, getter, notify_props, on_click, expand=False, min_width=80, zero_hp_highlight=False):
        """getter(creature_obj) -> str produces the cell text;
        notify_props (dash-case) triggers a refresh; on_click fires on
        a cell click; zero_hp_highlight marks 0-HP cells."""
        factory = Gtk.SignalListItemFactory()

        def on_setup(factory, list_item):
            label = Gtk.Label(label="", xalign=0, hexpand=True)
            label.add_css_class("editable-cell")
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_overflow(Gtk.Overflow.HIDDEN)
            label.set_cursor_from_name("pointer")
            label.set_size_request(min_width, -1)

            click_gesture = Gtk.GestureClick()
            click_gesture.set_button(1)
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
        column.set_fixed_width(min_width)
        self._enforce_min_width(column, min_width)
        return column

    @staticmethod
    def _enforce_min_width(column, min_width):
        """Gtk.ColumnViewColumn has no min-width property, so this
        snaps fixed-width back up if a drag pushes it below the floor."""
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
            button.add_css_class("icon-cell-button")
            button.set_overflow(Gtk.Overflow.HIDDEN)
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
