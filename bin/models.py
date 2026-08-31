"""Data layer: the plain Creature record, its GObject wrapper for use in
Gtk list models, and the InitiativeDatabase that owns the sorted,
current-turn-aware collection of creatures.

This module has no widgets in it on purpose -- everything here should be
testable without a display.
"""

import csv
from dataclasses import dataclass

from gi.repository import Gio, Gtk, GObject

# The CSV column order used by both export and import -- kept here
# rather than in a shared constants module since this is the only
# consumer.
CSV_HEADERS = ["Creature", "Hitpoints", "Max Hitpoints", "Armor Class", "Initiative Roll"]


@dataclass
class Creature:
    """Plain composite data class. This is the source of truth for a
    single creature's stats; CreatureObject below just exposes it to GTK."""
    name: str
    hitpoints: int
    max_hitpoints: int
    armor_class: int
    initiative_roll: int


class CreatureObject(GObject.Object):
    """GObject wrapper around a Creature dataclass instance.

    Gio.ListStore (and therefore Gtk.SortListModel / Gtk.ColumnView) can
    only hold GObject-derived items, so this adapts the plain dataclass
    into something GTK's model/view machinery can bind to and be notified
    about.
    """

    __gtype_name__ = "CreatureObject"

    def __init__(self, creature: Creature):
        super().__init__()
        self._creature = creature

    @GObject.Property(type=str)
    def name(self):
        return self._creature.name

    @name.setter
    def name(self, value):
        self._creature.name = value

    @GObject.Property(type=int)
    def hitpoints(self):
        return self._creature.hitpoints

    @hitpoints.setter
    def hitpoints(self, value):
        self._creature.hitpoints = value

    @GObject.Property(type=int)
    def max_hitpoints(self):
        return self._creature.max_hitpoints

    @max_hitpoints.setter
    def max_hitpoints(self, value):
        self._creature.max_hitpoints = value

    @GObject.Property(type=int)
    def armor_class(self):
        return self._creature.armor_class

    @armor_class.setter
    def armor_class(self, value):
        self._creature.armor_class = value

    @GObject.Property(type=int)
    def initiative_roll(self):
        return self._creature.initiative_roll

    @initiative_roll.setter
    def initiative_roll(self, value):
        self._creature.initiative_roll = value


class InitiativeDatabase:
    """Composite in-memory database of creatures, auto-sorted by
    initiative_roll (descending) via a Gtk.SortListModel, with the
    current turn tracked by reference."""

    def __init__(self):
        self.store = Gio.ListStore(item_type=CreatureObject)
        self.sorter = Gtk.CustomSorter.new(self._compare)
        self.sorted_model = Gtk.SortListModel(model=self.store, sorter=self.sorter)
        self.current_creature = None  # CreatureObject reference, or None
        self.round_number = 1

    @staticmethod
    def _compare(a, b, user_data=None):
        """Gtk.CustomSorter comparison: descending by initiative_roll."""
        if a.initiative_roll > b.initiative_roll:
            return -1
        if a.initiative_roll < b.initiative_roll:
            return 1
        return 0

    def _sorted_list(self):
        """Returns the current turn order as a plain Python list."""
        n = self.sorted_model.get_n_items()
        return [self.sorted_model.get_item(i) for i in range(n)]

    def _current_index(self):
        """Position of current_creature within the sorted turn order,
        or None if there's no current creature or it's not in the list."""
        items = self._sorted_list()
        if self.current_creature in items:
            return items.index(self.current_creature)
        return None

    def resort(self):
        """Call after a mutation that could change turn order
        (i.e. any edit to initiative_roll, or an add)."""
        self.sorter.changed(Gtk.SorterChange.DIFFERENT)

    def add_creature(self, creature: Creature) -> CreatureObject:
        """Adds a new creature to the database.

        A new arrival's higher roll only gets to jump the queue if
        whoever currently has the turn was already at the very top of
        the order -- i.e. combat hasn't meaningfully started yet, or
        it's genuinely the top roller's turn right now. Mid-round,
        adding creatures shouldn't disrupt whoever's turn it already
        is, even if the new arrival rolled higher.
        """
        current_was_top = self.current_creature is not None and self._current_index() == 0

        obj = CreatureObject(creature)
        self.store.append(obj)

        if self.current_creature is None:
            self.current_creature = obj
        elif current_was_top and obj.initiative_roll > self.current_creature.initiative_roll:
            self.current_creature = obj

        return obj

    def set_current_creature(self, creature_obj: CreatureObject):
        """Manually override whose turn it is -- distinct from
        next_turn(), which advances turn order rather than jumping to a
        specific creature."""
        self.current_creature = creature_obj

    def remove_creature(self, creature_obj: CreatureObject):
        """Removes a creature. If it was the current turn, current
        becomes the new top of the turn order (or None if now empty)."""
        found, position = self.store.find(creature_obj)
        if found:
            self.store.remove(position)
        if self.current_creature is creature_obj:
            items = self._sorted_list()
            self.current_creature = items[0] if items else None

    def next_turn(self):
        """Advances current_creature to the next creature in turn
        order, wrapping back to the top and incrementing round_number
        when a full cycle completes."""
        items = self._sorted_list()
        if not items:
            self.current_creature = None
            return
        idx = self._current_index()
        if idx is None:
            self.current_creature = items[0]
        else:
            new_idx = (idx + 1) % len(items)
            if new_idx == 0:
                # Wrapped back to the top of the turn order -- a full
                # round has elapsed.
                self.round_number += 1
            self.current_creature = items[new_idx]

    def export_csv(self, path):
        """Writes the full creature list to path as CSV, current
        creature first followed by the rest in turn order (wrapping
        around), with the round number appended to the header row."""
        items = self._sorted_list()
        idx = self._current_index()
        if idx is None:
            idx = 0
        # Current creature first, then the rest in the order their
        # turns would come up, wrapping back around.
        ordered = items[idx:] + items[:idx] if items else []

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # The round number is tacked onto the header row as a trailing
            # cell, since that row is otherwise write-only from our own
            # perspective -- import always skips row 0 entirely rather
            # than reading its cell values, so there's no established
            # column meaning there to collide with.
            writer.writerow(CSV_HEADERS + [str(self.round_number)])
            for obj in ordered:
                writer.writerow([
                    obj.name,
                    obj.hitpoints,
                    obj.max_hitpoints,
                    obj.armor_class,
                    obj.initiative_roll,
                ])

    def import_csv(self, path):
        """Replaces the entire creature list with the contents of path.
        The header row is skipped for creature data but its trailing
        cell (if present) is read back as the round number. Malformed
        data rows (fewer than 5 columns) are silently skipped."""
        with open(path, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        header_row = rows[0] if rows else []
        data_rows = rows[1:]

        new_objects = []
        for row in data_rows:
            if len(row) < 5:
                continue
            creature = Creature(
                name=row[0],
                hitpoints=int(row[1]),
                max_hitpoints=int(row[2]),
                armor_class=int(row[3]),
                initiative_roll=int(row[4]),
            )
            new_objects.append(CreatureObject(creature))

        self.store.remove_all()
        for obj in new_objects:
            self.store.append(obj)

        # First row in the file is, by our export convention, whoever's
        # turn it currently is.
        self.current_creature = new_objects[0] if new_objects else None

        # Round number, if present, is a trailing cell on the header row.
        # Files exported before this feature existed won't have it --
        # default back to round 1 rather than failing the import.
        round_number = 1
        if len(header_row) > len(CSV_HEADERS):
            try:
                round_number = int(header_row[len(CSV_HEADERS)])
            except ValueError:
                round_number = 1
        self.round_number = round_number
