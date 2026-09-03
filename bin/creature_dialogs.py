"""Modal dialogs for creating and editing creatures, built from their
.ui files. Plain functions rather than methods on AppWindow -- each
takes the parent window and a callback to invoke on success, so they
don't need to know anything about AppWindow's internals.
"""

from gi.repository import Gtk

from ui_paths import EDIT_FIELD_UI_PATH, EDIT_HITPOINTS_UI_PATH, ADD_CREATURE_UI_PATH
from models import Creature
from expressions import evaluate_int_expression, ExpressionError
from app_mode import Mode
from creature_stats_dialog import open_creature_stats_dialog
from creature_commands import STATS_FIELDS

# Fields edited as free-form text rather than an arithmetic/dice
# expression via open_edit_dialog. "name" falls back to "Unnamed" when
# left blank; "status" allows an empty string (no status).
_STRING_FIELDS = {"name", "status"}


def open_edit_dialog(parent, creature_obj, field_name, display_name, on_committed):
    """on_committed(old_value, new_value, resort: bool) is called after a
    successful update, once the dialog has already been destroyed --
    both values are passed (rather than just applying the change here
    and reporting success) so the caller can build an undo/redo command
    from them."""
    builder = Gtk.Builder()
    builder.add_from_file(EDIT_FIELD_UI_PATH)

    window = builder.get_object("edit_window")
    entry = builder.get_object("edit_entry")
    update_button = builder.get_object("update_button")
    cancel_button = builder.get_object("cancel_button")

    window.set_title(f"Edit {display_name}")
    window.set_transient_for(parent)

    old_value = getattr(creature_obj, field_name)
    entry.set_text(str(old_value))

    def on_update(_button):
        raw = entry.get_text().strip()
        entry.remove_css_class("error")

        if field_name == "name":
            new_value = raw or "Unnamed"
        elif field_name in _STRING_FIELDS:
            new_value = raw
        else:
            try:
                new_value = evaluate_int_expression(raw)
            except ExpressionError:
                entry.add_css_class("error")
                return

        setattr(creature_obj, field_name, new_value)
        resort = field_name == "initiative_roll"
        window.destroy()
        on_committed(old_value, new_value, resort)

    def on_cancel(_button):
        window.destroy()

    update_button.connect("clicked", on_update)
    cancel_button.connect("clicked", on_cancel)
    window.present()


def open_edit_hitpoints_dialog(parent, creature_obj, on_committed):
    """Dedicated hitpoints editor: current, max, and temporary HP as
    plain text entries, each evaluated as an arithmetic expression on
    Update (e.g. edit "23" to "23+5" to heal 5). A Temp HP expression
    that evaluates negative is applied to hitpoints instead (damage
    exceeding remaining temp HP), rather than clamped to a negative
    temp HP value. on_committed(old_hitpoints, old_max, old_temp,
    new_hitpoints, new_max, new_temp) is called after a successful
    update, once the dialog has already been destroyed."""
    builder = Gtk.Builder()
    builder.add_from_file(EDIT_HITPOINTS_UI_PATH)

    window = builder.get_object("edit_hitpoints_window")
    current_entry = builder.get_object("current_hp_entry")
    max_entry = builder.get_object("max_hp_entry")
    temp_entry = builder.get_object("temp_hp_entry")
    update_button = builder.get_object("update_button")
    cancel_button = builder.get_object("cancel_button")

    window.set_transient_for(parent)

    old_hitpoints = creature_obj.hitpoints
    old_max = creature_obj.max_hitpoints
    old_temp = creature_obj.temp_hitpoints
    current_entry.set_text(str(old_hitpoints))
    max_entry.set_text(str(old_max))
    temp_entry.set_text(str(old_temp))

    def on_update(_button):
        current_entry.remove_css_class("error")
        max_entry.remove_css_class("error")
        temp_entry.remove_css_class("error")

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

        try:
            new_temp = evaluate_int_expression(temp_entry.get_text())
        except ExpressionError:
            temp_entry.add_css_class("error")
            return

        if new_temp < 0:
            # A negative Temp HP entry represents damage overflowing
            # past whatever temporary HP was available -- applied
            # directly to hitpoints instead of clamping to a
            # nonsensical negative temp HP value.
            new_current += new_temp
            new_temp = 0

        new_max = max(new_max, 1)
        new_current = max(0, min(new_current, new_max))
        new_temp = max(0, new_temp)

        creature_obj.max_hitpoints = new_max
        creature_obj.hitpoints = new_current
        creature_obj.temp_hitpoints = new_temp
        window.destroy()
        on_committed(old_hitpoints, old_max, old_temp, new_current, new_max, new_temp)

    def on_cancel(_button):
        window.destroy()

    update_button.connect("clicked", on_update)
    cancel_button.connect("clicked", on_cancel)
    window.present()


def open_add_creature_dialog(parent, mode, on_added):
    """on_added(creatures: list[Creature]) is called after a successful
    add, once the dialog has already been destroyed. A list is used even
    for the common single-creature case so callers have one code path.

    mode controls how the 5e stat block is entered: Simple mode
    exposes just a plain Dexterity field (for breaking initiative
    ties); 5e Combat mode replaces it with an "Edit Stats..." button
    that opens the same full stat-block editor the crossed-swords
    table column uses (creature_stats_dialog.py) -- since Add Creature
    can create several creatures at once, whatever's set there is
    identical ("propagated") across every creature in that batch,
    rather than asked for once per creature.
    """
    builder = Gtk.Builder()
    builder.add_from_file(ADD_CREATURE_UI_PATH)

    window = builder.get_object("add_window")
    name_entry = builder.get_object("name_entry")
    hp_entry = builder.get_object("hp_entry")
    ac_entry = builder.get_object("ac_entry")
    init_entry = builder.get_object("init_entry")
    status_entry = builder.get_object("status_entry")
    dex_entry = builder.get_object("dex_entry")
    stats_button = builder.get_object("stats_button")
    count_spin = builder.get_object("count_spin")
    error_label = builder.get_object("error_label")
    add_button = builder.get_object("add_button")
    cancel_button = builder.get_object("cancel_button")

    window.set_transient_for(parent)

    is_combat_mode = mode is Mode.COMBAT_5E
    dex_entry.set_visible(not is_combat_mode)
    stats_button.set_visible(is_combat_mode)

    # The batch's shared stat block -- untouched (all zeros) unless
    # the user actually opens Edit Stats, in which case every field
    # here (including dexterity, no longer entered via dex_entry in
    # this mode) gets applied identically to every creature created
    # below.
    staged_stats = {field: 0 for field in STATS_FIELDS}

    def on_stats_button_clicked(_button):
        def on_stats_committed(new_stats):
            staged_stats.update(new_stats)
        open_creature_stats_dialog(window, staged_stats, on_stats_committed)

    stats_button.connect("clicked", on_stats_button_clicked)

    def show_error(message):
        error_label.set_text(message)
        error_label.set_visible(True)

    def on_add(_button):
        base_name = name_entry.get_text().strip() or "Unnamed"
        count = int(count_spin.get_value())
        status = status_entry.get_text().strip()
        # A blank Initiative Roll rolls its own 1d20, same as any
        # other die notation typed directly -- evaluated per creature
        # in the loop below, not once here, so each creature in a
        # multi-add batch gets its own independent roll.
        raw_init = init_entry.get_text().strip() or "1d20"

        creatures = []
        for i in range(count):
            # Hitpoints, Armor Class, and Initiative Roll are each
            # re-evaluated per creature rather than once outside the
            # loop, so dice notation in any of them gives every
            # creature in the batch its own independent roll. The
            # rest of the stat block (staged_stats, or a plain
            # Dexterity in Simple mode) is deliberately NOT
            # re-evaluated per creature -- it's already resolved to
            # plain integers, the same for every creature in the
            # batch, by design (see the docstring above).
            try:
                hitpoints = evaluate_int_expression(hp_entry.get_text())
                armor_class = evaluate_int_expression(ac_entry.get_text())
                initiative_roll = evaluate_int_expression(raw_init)
                dexterity = staged_stats["dexterity"] if is_combat_mode else evaluate_int_expression(dex_entry.get_text())
            except ExpressionError:
                show_error(
                    "Hitpoints, Armor Class, Initiative Roll, and Dexterity "
                    "must be whole numbers or expressions."
                )
                return

            # Only number duplicates when there's more than one -- a
            # single add keeps the name exactly as typed.
            display_name = f"{base_name} {i + 1}" if count > 1 else base_name
            creature_kwargs = dict(
                name=display_name,
                hitpoints=hitpoints,
                max_hitpoints=hitpoints,
                armor_class=armor_class,
                initiative_roll=initiative_roll,
                status=status,
                dexterity=dexterity,
            )
            if is_combat_mode:
                creature_kwargs.update({f: v for f, v in staged_stats.items() if f != "dexterity"})
            creatures.append(Creature(**creature_kwargs))

        window.destroy()
        on_added(creatures)

    def on_cancel(_button):
        window.destroy()

    add_button.connect("clicked", on_add)
    cancel_button.connect("clicked", on_cancel)
    window.present()
