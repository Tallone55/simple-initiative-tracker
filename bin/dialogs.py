"""Modal dialogs, built from their .ui files. These are plain functions
rather than methods on AppWindow -- each takes the parent window and a
callback to invoke on success, so they don't need to know anything about
AppWindow's internals.
"""

import random

from gi.repository import Gtk

from constants import EDIT_FIELD_UI_PATH, EDIT_HITPOINTS_UI_PATH, ADD_CREATURE_UI_PATH
from models import Creature
from expressions import evaluate_int_expression, ExpressionError


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
                value = evaluate_int_expression(raw)
            except ExpressionError:
                entry.add_css_class("error")
                return
            setattr(creature_obj, field_name, value)

        resort = field_name == "initiative_roll"
        window.destroy()
        on_committed(resort=resort)

    def on_cancel(_button):
        window.destroy()

    update_button.connect("clicked", on_update)
    cancel_button.connect("clicked", on_cancel)
    window.present()


def open_edit_hitpoints_dialog(parent, creature_obj, on_committed):
    """Dedicated hitpoints editor: current and max HP as plain text
    entries, each pre-filled with its current value and evaluated as an
    arithmetic expression on Update (e.g. edit "23" to "23+5" to heal 5).
    """
    builder = Gtk.Builder()
    builder.add_from_file(EDIT_HITPOINTS_UI_PATH)

    window = builder.get_object("edit_hitpoints_window")
    current_entry = builder.get_object("current_hp_entry")
    max_entry = builder.get_object("max_hp_entry")
    update_button = builder.get_object("update_button")
    cancel_button = builder.get_object("cancel_button")

    window.set_transient_for(parent)

    current_entry.set_text(str(creature_obj.hitpoints))
    max_entry.set_text(str(creature_obj.max_hitpoints))

    def on_update(_button):
        current_entry.remove_css_class("error")
        max_entry.remove_css_class("error")

        try:
            new_max = evaluate_int_expression(max_entry.get_text())
        except ExpressionError:
            max_entry.add_css_class("error")
            return

        try:
            new_current = evaluate_int_expression(current_entry.get_text())
        except ExpressionError:
            current_entry.add_css_class("error")
            return

        new_max = max(new_max, 1)
        new_current = max(0, min(new_current, new_max))

        creature_obj.max_hitpoints = new_max
        creature_obj.hitpoints = new_current
        window.destroy()
        on_committed(resort=False)

    def on_cancel(_button):
        window.destroy()

    update_button.connect("clicked", on_update)
    cancel_button.connect("clicked", on_cancel)
    window.present()


def open_add_creature_dialog(parent, on_added):
    """on_added(creatures: list[Creature]) is called after a successful
    add, once the dialog has already been destroyed. A list is used even
    for the common single-creature case so callers have one code path.
    """
    builder = Gtk.Builder()
    builder.add_from_file(ADD_CREATURE_UI_PATH)

    window = builder.get_object("add_window")
    name_entry = builder.get_object("name_entry")
    hp_entry = builder.get_object("hp_entry")
    ac_entry = builder.get_object("ac_entry")
    init_entry = builder.get_object("init_entry")
    count_spin = builder.get_object("count_spin")
    error_label = builder.get_object("error_label")
    add_button = builder.get_object("add_button")
    cancel_button = builder.get_object("cancel_button")

    window.set_transient_for(parent)

    def show_error(message):
        error_label.set_text(message)
        error_label.set_visible(True)

    def on_add(_button):
        try:
            hitpoints = evaluate_int_expression(hp_entry.get_text())
            armor_class = evaluate_int_expression(ac_entry.get_text())
        except ExpressionError:
            show_error("Hitpoints and Armor Class must be whole numbers or expressions.")
            return

        raw_init = init_entry.get_text().strip()
        if raw_init:
            try:
                fixed_initiative = evaluate_int_expression(raw_init)
            except ExpressionError:
                show_error(
                    "Initiative Roll must be a whole number or expression, "
                    "or left blank to roll randomly (1-20)."
                )
                return
        else:
            fixed_initiative = None  # roll per-creature below

        base_name = name_entry.get_text().strip() or "Unnamed"
        count = int(count_spin.get_value())

        creatures = []
        for i in range(count):
            # Only number duplicates when there's more than one -- a
            # single add keeps the name exactly as typed.
            display_name = f"{base_name} {i + 1}" if count > 1 else base_name
            initiative_roll = (
                fixed_initiative if fixed_initiative is not None
                else random.randint(1, 20)
            )
            creatures.append(Creature(
                name=display_name,
                hitpoints=hitpoints,
                max_hitpoints=hitpoints,
                armor_class=armor_class,
                initiative_roll=initiative_roll,
            ))

        window.destroy()
        on_added(creatures)

    def on_cancel(_button):
        window.destroy()

    add_button.connect("clicked", on_add)
    cancel_button.connect("clicked", on_cancel)
    window.present()
