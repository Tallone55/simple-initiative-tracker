"""Data layer: the plain Creature record, its GObject wrapper for use in
Gtk list models, and the InitiativeDatabase that owns the sorted,
current-turn-aware collection of creatures.

This module has no widgets in it on purpose -- everything here should be
testable without a display.
"""

import csv
from dataclasses import dataclass

from gi.repository import Gio, Gtk, GObject

from constants import CSV_HEADERS


@dataclass
class Creature:
    """Plain composite data class. This is the source of truth for a
    single creature's stats; CreatureObject below just exposes it to GTK."""
    name: str
    hitpoints: int
    armor_class: int
    initiative_roll: int


class CreatureObject(GObject.Object):
    """GObject wrapper around a Creature dataclass instance.

    Gio.ListStore (and therefore Gtk.SortListModel / Gtk.ListView) can only
    hold GObject-derived items, so this adapts the plain dataclass into
    something GTK's model/view machinery can bind to and be notified about.
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

    @staticmethod
    def _compare(a, b, user_data=None):
        if a.initiative_roll > b.initiative_roll:
            return -1
        if a.initiative_roll < b.initiative_roll:
            return 1
        return 0

    def _sorted_list(self):
        n = self.sorted_model.get_n_items()
        return [self.sorted_model.get_item(i) for i in range(n)]

    def _current_index(self):
        items = self._sorted_list()
        if self.current_creature in items:
            return items.index(self.current_creature)
        return None

    def resort(self):
        """Call after a mutation that could change turn order
        (i.e. any edit to initiative_roll, or an add)."""
        self.sorter.changed(Gtk.SorterChange.DIFFERENT)

    def add_creature(self, creature: Creature) -> CreatureObject:
        obj = CreatureObject(creature)
        self.store.append(obj)
        if self.current_creature is None:
            self.current_creature = obj
        return obj

    def remove_creature(self, creature_obj: CreatureObject):
        found, position = self.store.find(creature_obj)
        if found:
            self.store.remove(position)
        if self.current_creature is creature_obj:
            items = self._sorted_list()
            self.current_creature = items[0] if items else None

    def next_turn(self):
        items = self._sorted_list()
        if not items:
            self.current_creature = None
            return
        idx = self._current_index()
        if idx is None:
            self.current_creature = items[0]
        else:
            self.current_creature = items[(idx + 1) % len(items)]

    def export_csv(self, path):
        items = self._sorted_list()
        idx = self._current_index()
        if idx is None:
            idx = 0
        # Current creature first, then the rest in the order their
        # turns would come up, wrapping back around.
        ordered = items[idx:] + items[:idx] if items else []

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADERS)
            for obj in ordered:
                writer.writerow([
                    obj.name,
                    obj.hitpoints,
                    obj.armor_class,
                    obj.initiative_roll,
                ])

    def import_csv(self, path):
        with open(path, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        data_rows = rows[1:]  # header is always ignored on import

        new_objects = []
        for row in data_rows:
            if len(row) < 4:
                continue
            creature = Creature(
                name=row[0],
                hitpoints=int(row[1]),
                armor_class=int(row[2]),
                initiative_roll=int(row[3]),
            )
            new_objects.append(CreatureObject(creature))

        self.store.remove_all()
        for obj in new_objects:
            self.store.append(obj)

        # First row in the file is, by our export convention, whoever's
        # turn it currently is.
        self.current_creature = new_objects[0] if new_objects else None
