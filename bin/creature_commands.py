"""Creature mutations (add/remove/edit) that also register the
matching undo/redo Command. No GTK dependency."""

from undo_manager import Command


def add_creatures(database, undo_manager, creatures) -> bool:
    """Returns whether a resort is needed."""
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
    """Returns whether a resort is needed."""
    previous_current = database.current_creature
    database.remove_creature(creature_obj)
    resulting_current = database.current_creature

    def undo():
        database.store.append(creature_obj)
        database.current_creature = previous_current

    def redo():
        database.remove_creature(creature_obj)
        database.current_creature = resulting_current

    undo_manager.push(Command(undo=undo, redo=redo))
    return False


def edit_field(undo_manager, creature_obj, field_name, display_name, old_value, new_value):
    def undo():
        setattr(creature_obj, field_name, old_value)

    def redo():
        setattr(creature_obj, field_name, new_value)

    undo_manager.push(Command(undo=undo, redo=redo))


def edit_hitpoints(undo_manager, creature_obj, old_hitpoints, old_max, old_temp, new_hitpoints, new_max, new_temp):
    def undo():
        creature_obj.max_hitpoints = old_max
        creature_obj.hitpoints = old_hitpoints
        creature_obj.temp_hitpoints = old_temp

    def redo():
        creature_obj.max_hitpoints = new_max
        creature_obj.hitpoints = new_hitpoints
        creature_obj.temp_hitpoints = new_temp

    undo_manager.push(Command(undo=undo, redo=redo))


STATS_FIELDS = [
    "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma",
    "proficiency_bonus", "save_skill_pattern", "to_hit_bonus",
]


def edit_stats(undo_manager, creature_obj, old_stats, new_stats):
    """old_stats/new_stats are dicts keyed by STATS_FIELDS."""
    def undo():
        for field in STATS_FIELDS:
            setattr(creature_obj, field, old_stats[field])

    def redo():
        for field in STATS_FIELDS:
            setattr(creature_obj, field, new_stats[field])

    undo_manager.push(Command(undo=undo, redo=redo))
