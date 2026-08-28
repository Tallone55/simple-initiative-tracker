"""Modal dialogs, built from their .ui files. These are plain functions
rather than methods on AppWindow -- each takes the parent window and a
callback to invoke on success, so they don't need to know anything about
AppWindow's internals.
"""

from gi.repository import Gtk

from constants import EDIT_FIELD_UI_PATH, ADD_CREATURE_UI_PATH
from models import Creature


def open_edit_dialog(parent, creature_obj, field_name, display_name, on_committed):
    """on_committed(resort: bool) is called after a successful update,
    once the dialog has already been destroyed."""
    builder = Gtk.Builder()
    builder.add_from_file(EDIT_FIELD_UI_PATH)

    window = builder.get_object("edit_window")
    entry = builder.get_object("edit_entry")
    update_button = builder.get_object("update_button")
    cancel_button = builder.get_object("cancel_button")

    window.set_title(f"Edit {display_name}")
    window.set_transient_for(parent)

    current_value = getattr(creature_obj, field_name)
    entry.set_text(str(current_value))

    def on_update(_button):
        raw = entry.get_text().strip()
        entry.remove_css_class("error")

        if field_name == "name":
            setattr(creature_obj, field_name, raw or "Unnamed")
        else:
            try:
                setattr(creature_obj, field_name, int(raw))
            except ValueError:
                entry.add_css_class("error")
                return

        resort = field_name == "initiative_roll"
        window.destroy()
        on_committed(resort=resort)

    def on_cancel(_button):
        window.destroy()

    update_button.connect("clicked", on_update)
    cancel_button.connect("clicked", on_cancel)
    window.present()


def open_add_creature_dialog(parent, on_added):
    """on_added(creature: Creature) is called after a successful add,
    once the dialog has already been destroyed."""
    builder = Gtk.Builder()
    builder.add_from_file(ADD_CREATURE_UI_PATH)

    window = builder.get_object("add_window")
    name_entry = builder.get_object("name_entry")
    hp_entry = builder.get_object("hp_entry")
    ac_entry = builder.get_object("ac_entry")
    init_entry = builder.get_object("init_entry")
    error_label = builder.get_object("error_label")
    add_button = builder.get_object("add_button")
    cancel_button = builder.get_object("cancel_button")

    window.set_transient_for(parent)

    def on_add(_button):
        try:
            creature = Creature(
                name=name_entry.get_text().strip() or "Unnamed",
                hitpoints=int(hp_entry.get_text()),
                armor_class=int(ac_entry.get_text()),
                initiative_roll=int(init_entry.get_text()),
            )
        except ValueError:
            error_label.set_text(
                "Hitpoints, Armor Class, and Initiative Roll must be whole numbers."
            )
            error_label.set_visible(True)
            return

        window.destroy()
        on_added(creature)

    def on_cancel(_button):
        window.destroy()

    add_button.connect("clicked", on_add)
    cancel_button.connect("clicked", on_cancel)
    window.present()
