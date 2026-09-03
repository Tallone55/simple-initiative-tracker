"""Functions that perform a creature mutation (add/remove/edit) and
register its undo/redo Command with the UndoManager in one place, so
callers (AppWindow) don't need to know the shape of each mutation's
undo/redo pair. No GTK dependency: these closures only mutate
InitiativeDatabase / CreatureObject state -- refreshing the UI is the
caller's job, via AppWindow.after_database_mutation."""

from undo_manager import Command


def add_creatures(database, undo_manager, creatures) -> bool:
    """Adds one or more new creatures as a single undoable action.
    Returns whether a resort is needed."""
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

    undo_manager.push(Command(undo=undo, redo=redo))
    return True


def remove_creature(database, undo_manager, creature_obj) -> bool:
    """Removes a creature and registers an undo that restores it and
    the exact current-turn state at removal time. Returns whether a
    resort is needed."""
    previous_current = database.current_creature
    database.remove_creature(creature_obj)
    resulting_current = database.current_creature

    def undo():
        # Re-append the same instance directly, bypassing
        # add_creature's auto-select-highest-roller logic, for an
        # exact reversal.
        database.store.append(creature_obj)
        database.current_creature = previous_current

    def redo():
        database.remove_creature(creature_obj)
        database.current_creature = resulting_current

    undo_manager.push(Command(undo=undo, redo=redo))
    return False


def edit_field(undo_manager, creature_obj, field_name, display_name, old_value, new_value):
    """Registers an undo/redo command for a single-field edit. The
    field has already been set on creature_obj by the time this runs."""
    def undo():
        setattr(creature_obj, field_name, old_value)

    def redo():
        setattr(creature_obj, field_name, new_value)

    undo_manager.push(Command(undo=undo, redo=redo))


def edit_hitpoints(undo_manager, creature_obj, old_hitpoints, old_max, old_temp, new_hitpoints, new_max, new_temp):
    """Registers a single undo/redo command covering current, max, and
    temporary HP together, since they're edited as one logical action."""
    def undo():
        creature_obj.max_hitpoints = old_max
        creature_obj.hitpoints = old_hitpoints
        creature_obj.temp_hitpoints = old_temp

    def redo():
        creature_obj.max_hitpoints = new_max
        creature_obj.hitpoints = new_hitpoints
        creature_obj.temp_hitpoints = new_temp

    undo_manager.push(Command(undo=undo, redo=redo))


# The full set of fields creature_stats_dialog.py's stats dict covers
# -- kept in one place so edit_stats below and window.py's read side
# (building the dict to hand the dialog) can't drift apart on which
# keys are actually part of "the stat block."
STATS_FIELDS = [
    "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma",
    "proficiency_bonus", "save_skill_pattern", "to_hit_bonus",
]


def edit_stats(undo_manager, creature_obj, old_stats, new_stats):
    """Registers a single undo/redo command covering the whole 5e
    stat block (six ability scores, proficiency bonus, and the
    encoded saving-throw/skill pattern) as one logical action, same
    reasoning as edit_hitpoints above. old_stats/new_stats are dicts
    keyed by STATS_FIELDS -- see creature_stats_dialog.py's own
    docstring for the exact shape."""
    def undo():
        for field in STATS_FIELDS:
            setattr(creature_obj, field, old_stats[field])

    def redo():
        for field in STATS_FIELDS:
            setattr(creature_obj, field, new_stats[field])

    undo_manager.push(Command(undo=undo, redo=redo))
