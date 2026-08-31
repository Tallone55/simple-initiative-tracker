"""Functions that perform a creature mutation (add/remove/edit) and
register its undo/redo Command with the UndoManager in one place, so
callers (AppWindow) don't need to know the shape of each mutation's
undo/redo pair.

Deliberately has no GTK dependency and doesn't call anything on
AppWindow -- undo/redo closures here only mutate InitiativeDatabase /
CreatureObject state. Refreshing the UI afterward (selection, round
label, dirty flag) is the caller's responsibility: AppWindow calls
after_database_mutation() itself after each of these, and again,
unconditionally, after every undo/redo replay via perform_undo/
perform_redo -- so these closures don't need to trigger it themselves.
"""

from undo_manager import Command


def add_creatures(database, undo_manager, creatures) -> bool:
    """Adds one or more new creatures as a single undoable action (a
    bulk add is one undo step, not one per creature). Returns whether a
    resort is needed for the initial add."""
    previous_current = database.current_creature
    added_objects = [database.add_creature(c) for c in creatures]
    resulting_current = database.current_creature

    def undo():
        for obj in added_objects:
            database.remove_creature(obj)
        database.current_creature = previous_current

    def redo():
        for obj in added_objects:
            database.store.append(obj)
        database.current_creature = resulting_current

    undo_manager.push(Command(undo=undo, redo=redo, description="Add creature(s)"))
    return True


def remove_creature(database, undo_manager, creature_obj) -> bool:
    """Removes a creature and registers an undo that restores it --
    and the exact current-turn state at removal time -- rather than
    re-deriving that state via add_creature()'s own selection logic,
    which could disagree. Returns whether a resort is needed."""
    previous_current = database.current_creature
    database.remove_creature(creature_obj)
    resulting_current = database.current_creature

    def undo():
        # Re-append the same CreatureObject instance directly (bypassing
        # add_creature's auto-select-highest-roller logic) so this is an
        # exact, faithful reversal.
        database.store.append(creature_obj)
        database.current_creature = previous_current

    def redo():
        database.remove_creature(creature_obj)
        database.current_creature = resulting_current

    undo_manager.push(Command(undo=undo, redo=redo, description="Remove creature"))
    return False


def edit_field(undo_manager, creature_obj, field_name, display_name, old_value, new_value):
    """Registers an undo/redo command for a single-field edit (name,
    armor_class, or initiative_roll). Doesn't touch the database at all
    -- the field has already been set on creature_obj by the time this
    is called."""
    def undo():
        setattr(creature_obj, field_name, old_value)

    def redo():
        setattr(creature_obj, field_name, new_value)

    undo_manager.push(Command(undo=undo, redo=redo, description=f"Edit {display_name}"))


def edit_hitpoints(undo_manager, creature_obj, old_hitpoints, old_max, new_hitpoints, new_max):
    """Registers a single undo/redo command covering both current and
    max HP together, since they're edited as one logical action."""
    def undo():
        creature_obj.max_hitpoints = old_max
        creature_obj.hitpoints = old_hitpoints

    def redo():
        creature_obj.max_hitpoints = new_max
        creature_obj.hitpoints = new_hitpoints

    undo_manager.push(Command(undo=undo, redo=redo, description="Edit Hitpoints"))
