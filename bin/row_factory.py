"""Builds and manages the Gtk.ListView rows for creature entries: creating
the row widgets, binding them to a CreatureObject's live properties (so
edits made elsewhere auto-refresh the label), and tracking which row (if
any) is the current turn so it can be highlighted.
"""

from gi.repository import Gtk


class CreatureRowFactory:
    # (attribute name on CreatureObject, display label for the edit dialog)
    FIELDS = (
        ("name", "Creature"),
        ("hitpoints", "Hitpoints"),
        ("armor_class", "Armor Class"),
        ("initiative_roll", "Initiative Roll"),
    )

    def __init__(self, on_edit_requested, on_remove_requested, is_current_fn):
        """
        on_edit_requested(creature_obj, field_name, display_name) -- called
            when a field button is clicked.
        on_remove_requested(creature_obj) -- called when a row's Remove
            button is clicked.
        is_current_fn(creature_obj) -> bool -- used to decide whether a
            row should show the current-turn highlight.
        """
        self.on_edit_requested = on_edit_requested
        self.on_remove_requested = on_remove_requested
        self.is_current_fn = is_current_fn

        # id(CreatureObject) -> (row_widget, creature_obj)
        self.row_boxes = {}

        self.factory = Gtk.SignalListItemFactory()
        self.factory.connect("setup", self._on_setup)
        self.factory.connect("bind", self._on_bind)
        self.factory.connect("unbind", self._on_unbind)

    # -- Gtk.SignalListItemFactory callbacks ---------------------------------

    def _on_setup(self, factory, list_item):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.add_css_class("initiative-row")

        field_buttons = {}
        for field_name, _display_name in self.FIELDS:
            # label="" up front guarantees the button already has an
            # internal Label child, so get_child() below is never None.
            button = Gtk.Button(label="", hexpand=True)
            button.add_css_class("flat")
            button.get_child().set_xalign(0)
            row.append(button)
            field_buttons[field_name] = button

        remove_button = Gtk.Button(label="Remove")
        row.append(remove_button)

        list_item.row = row
        list_item.field_buttons = field_buttons
        list_item.remove_button = remove_button
        list_item.notify_handler_ids = []
        list_item.click_handler_ids = []

        list_item.set_child(row)

    def _on_bind(self, factory, list_item):
        creature_obj = list_item.get_item()
        row = list_item.row

        for field_name, display_name in self.FIELDS:
            button = list_item.field_buttons[field_name]
            refresh = self._make_refresh(creature_obj, field_name, button)
            refresh()

            gobject_prop = field_name.replace("_", "-")
            list_item.notify_handler_ids.append(
                creature_obj.connect(f"notify::{gobject_prop}", refresh)
            )
            list_item.click_handler_ids.append((
                button,
                button.connect(
                    "clicked",
                    lambda b, fn=field_name, dn=display_name: (
                        self.on_edit_requested(creature_obj, fn, dn)
                    ),
                ),
            ))

        list_item.click_handler_ids.append((
            list_item.remove_button,
            list_item.remove_button.connect(
                "clicked", lambda b: self.on_remove_requested(creature_obj)
            ),
        ))

        self.row_boxes[id(creature_obj)] = (row, creature_obj)
        self.update_row_highlight(row, creature_obj)

    def _on_unbind(self, factory, list_item):
        creature_obj = list_item.get_item()

        for hid in list_item.notify_handler_ids:
            creature_obj.disconnect(hid)
        list_item.notify_handler_ids = []

        for widget, hid in list_item.click_handler_ids:
            widget.disconnect(hid)
        list_item.click_handler_ids = []

        self.row_boxes.pop(id(creature_obj), None)

    @staticmethod
    def _make_refresh(creature_obj, field_name, button):
        def refresh(*_args):
            button.set_label(str(getattr(creature_obj, field_name)))
        return refresh

    # -- highlighting ------------------------------------------------

    def update_row_highlight(self, row, creature_obj):
        if self.is_current_fn(creature_obj):
            row.add_css_class("current-turn")
        else:
            row.remove_css_class("current-turn")

    def refresh_highlights(self):
        """Call after anything that could change which creature is
        current (next turn, add, remove, import)."""
        for row, creature_obj in list(self.row_boxes.values()):
            self.update_row_highlight(row, creature_obj)
