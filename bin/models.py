"""Data layer: the plain Creature record, its GObject wrapper for use in
GTK list models, and the InitiativeDatabase that owns the sorted,
current-turn-aware collection of creatures. No widgets here."""

import csv
from dataclasses import dataclass

from gi.repository import Gio, Gtk, GObject

CSV_HEADERS = [
    "Creature", "Hitpoints", "Max Hitpoints", "Armor Class", "Initiative Roll",
    "Temp Hitpoints", "Status", "Strength", "Dexterity", "Constitution",
    "Intelligence", "Wisdom", "Charisma", "Proficiency Bonus", "Save/Skill Pattern",
    "To-Hit Bonus",
]

# -- 5e ability/skill reference data ------------------------------------------------

ABILITIES = ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]
ABILITY_ABBREVIATIONS = {
    "strength": "Str", "dexterity": "Dex", "constitution": "Con",
    "intelligence": "Int", "wisdom": "Wis", "charisma": "Cha",
}

# (skill name, governing ability), the standard 5e list of 18.
SKILLS = [
    ("Athletics", "strength"),
    ("Acrobatics", "dexterity"),
    ("Sleight of Hand", "dexterity"),
    ("Stealth", "dexterity"),
    ("Arcana", "intelligence"),
    ("History", "intelligence"),
    ("Investigation", "intelligence"),
    ("Nature", "intelligence"),
    ("Religion", "intelligence"),
    ("Animal Handling", "wisdom"),
    ("Insight", "wisdom"),
    ("Medicine", "wisdom"),
    ("Perception", "wisdom"),
    ("Survival", "wisdom"),
    ("Deception", "charisma"),
    ("Intimidation", "charisma"),
    ("Performance", "charisma"),
    ("Persuasion", "charisma"),
]
assert len(SKILLS) == 18
SKILL_NAMES = [name for name, _ in SKILLS]

# Skills grouped by governing ability, in SKILLS order.
SKILLS_BY_ABILITY = {ability: [] for ability in ABILITIES}
for _skill_name, _governing_ability in SKILLS:
    SKILLS_BY_ABILITY[_governing_ability].append(_skill_name)

# 24 positions: 6 saving throws (ABILITIES order), then 18 skills
# (SKILLS order).
_POSITIONS = list(ABILITIES) + SKILL_NAMES
NUM_POSITIONS = len(_POSITIONS)
assert NUM_POSITIONS == 24


def position_index(kind, name):
    """0-based position for a saving throw (kind="save", name in
    ABILITIES) or a skill (kind="skill", name in SKILL_NAMES)."""
    if kind == "save":
        return ABILITIES.index(name)
    return 6 + SKILL_NAMES.index(name)


def ability_modifier(score):
    """Standard 5e ability modifier: floor((score - 10) / 2)."""
    return (score - 10) // 2


# -- proficiency/advantage pattern encoding ------------------------------------------------
#
# One integer (Creature.save_skill_pattern) covers all 24 positions'
# proficiency level and advantage:
#   - Proficiency level per position is a base-3 trit (0/1/2 for
#     skills; saves only ever use 0/1), packed into a base-3 number.
#   - Advantage per position is one bit, packed into a 24-bit number.
#   - Combined as (advantage_bits * 3**24) + proficiency_trits.

_TRIT_BASE = 3 ** NUM_POSITIONS


def encode_pattern(proficiency_levels, advantages):
    """proficiency_levels: 24 ints (0/1/2). advantages: 24
    truthy/falsy values. Both in position order."""
    prof_code = 0
    for i, level in enumerate(proficiency_levels):
        prof_code += level * (3 ** i)
    adv_code = 0
    for i, advantage in enumerate(advantages):
        if advantage:
            adv_code |= (1 << i)
    return prof_code + adv_code * _TRIT_BASE


def decode_pattern(value):
    """Inverse of encode_pattern."""
    adv_code, prof_code = divmod(value, _TRIT_BASE)
    proficiency_levels = []
    remaining = prof_code
    for _ in range(NUM_POSITIONS):
        remaining, trit = divmod(remaining, 3)
        proficiency_levels.append(trit)
    advantages = [bool((adv_code >> i) & 1) for i in range(NUM_POSITIONS)]
    return proficiency_levels, advantages


@dataclass
class Creature:
    """Plain data class -- the source of truth for a single creature's
    stats. CreatureObject below exposes it to GTK.

    The six ability scores default to 0, meaning "not set". Dexterity
    is usable outside 5e Combat mode too (initiative tie-break); the
    rest are only editable via the stat-block window."""
    name: str
    hitpoints: int
    max_hitpoints: int
    armor_class: int
    initiative_roll: int
    temp_hitpoints: int = 0
    status: str = ""
    strength: int = 0
    dexterity: int = 0
    constitution: int = 0
    intelligence: int = 0
    wisdom: int = 0
    charisma: int = 0
    proficiency_bonus: int = 0
    save_skill_pattern: int = 0
    to_hit_bonus: int = 0


class CreatureObject(GObject.Object):
    """GObject wrapper around a Creature, since Gio.ListStore/
    Gtk.SortListModel/Gtk.ColumnView require GObject-derived items."""

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

    @GObject.Property(type=int)
    def temp_hitpoints(self):
        return self._creature.temp_hitpoints

    @temp_hitpoints.setter
    def temp_hitpoints(self, value):
        self._creature.temp_hitpoints = value

    @GObject.Property(type=str)
    def status(self):
        return self._creature.status

    @status.setter
    def status(self, value):
        self._creature.status = value

    @GObject.Property(type=int)
    def strength(self):
        return self._creature.strength

    @strength.setter
    def strength(self, value):
        self._creature.strength = value

    @GObject.Property(type=int)
    def dexterity(self):
        return self._creature.dexterity

    @dexterity.setter
    def dexterity(self, value):
        self._creature.dexterity = value

    @GObject.Property(type=int)
    def constitution(self):
        return self._creature.constitution

    @constitution.setter
    def constitution(self, value):
        self._creature.constitution = value

    @GObject.Property(type=int)
    def intelligence(self):
        return self._creature.intelligence

    @intelligence.setter
    def intelligence(self, value):
        self._creature.intelligence = value

    @GObject.Property(type=int)
    def wisdom(self):
        return self._creature.wisdom

    @wisdom.setter
    def wisdom(self, value):
        self._creature.wisdom = value

    @GObject.Property(type=int)
    def charisma(self):
        return self._creature.charisma

    @charisma.setter
    def charisma(self, value):
        self._creature.charisma = value

    @GObject.Property(type=int)
    def proficiency_bonus(self):
        return self._creature.proficiency_bonus

    @proficiency_bonus.setter
    def proficiency_bonus(self, value):
        self._creature.proficiency_bonus = value

    # int64: the encoded value can exceed 2**31.
    @GObject.Property(type=GObject.TYPE_INT64)
    def save_skill_pattern(self):
        return self._creature.save_skill_pattern

    @save_skill_pattern.setter
    def save_skill_pattern(self, value):
        self._creature.save_skill_pattern = value

    @GObject.Property(type=int)
    def to_hit_bonus(self):
        return self._creature.to_hit_bonus

    @to_hit_bonus.setter
    def to_hit_bonus(self, value):
        self._creature.to_hit_bonus = value


class InitiativeDatabase:
    """In-memory database of creatures, auto-sorted by initiative_roll
    (descending) via a Gtk.SortListModel, with the current turn tracked
    by reference."""

    def __init__(self):
        self.store = Gio.ListStore(item_type=CreatureObject)
        self.sorter = Gtk.CustomSorter.new(self._compare)
        self.sorted_model = Gtk.SortListModel(model=self.store, sorter=self.sorter)
        self.current_creature = None  # CreatureObject reference, or None
        self.round_number = 1
        self.mode = 0  # plain int; see app_mode.py

    @staticmethod
    def _compare(a, b, user_data=None):
        if a.initiative_roll != b.initiative_roll:
            return -1 if a.initiative_roll > b.initiative_roll else 1
        # 5e tie-break: higher Dexterity acts first.
        if a.dexterity != b.dexterity:
            return -1 if a.dexterity > b.dexterity else 1
        return 0

    def _sorted_list(self):
        n = self.sorted_model.get_n_items()
        return [self.sorted_model.get_item(i) for i in range(n)]

    def _current_index(self):
        """Position of current_creature in turn order, or None."""
        items = self._sorted_list()
        if self.current_creature in items:
            return items.index(self.current_creature)
        return None

    def resort(self):
        self.sorter.changed(Gtk.SorterChange.DIFFERENT)

    def add_creature(self, creature: Creature) -> CreatureObject:
        """A new arrival's higher roll only jumps the queue if whoever
        has the turn was already at the top of the order."""
        current_was_top = self.current_creature is not None and self._current_index() == 0

        obj = CreatureObject(creature)
        self.store.append(obj)

        if self.current_creature is None:
            self.current_creature = obj
        elif current_was_top and obj.initiative_roll > self.current_creature.initiative_roll:
            self.current_creature = obj

        return obj

    def set_current_creature(self, creature_obj: CreatureObject):
        self.current_creature = creature_obj

    def clear(self):
        self.store.remove_all()
        self.current_creature = None
        self.round_number = 1
        self.mode = 0

    def remove_creature(self, creature_obj: CreatureObject):
        """If the removed creature was the current turn, current
        becomes the new top of the turn order (or None if empty)."""
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
            new_idx = (idx + 1) % len(items)
            if new_idx == 0:
                self.round_number += 1
            self.current_creature = items[new_idx]

    def export_csv(self, path):
        """Writes the creature list as CSV, current creature first,
        with round number and display mode appended to the header."""
        items = self._sorted_list()
        idx = self._current_index()
        if idx is None:
            idx = 0
        ordered = items[idx:] + items[:idx] if items else []

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADERS + [str(self.round_number), str(self.mode)])
            for obj in ordered:
                writer.writerow([
                    obj.name,
                    obj.hitpoints,
                    obj.max_hitpoints,
                    obj.armor_class,
                    obj.initiative_roll,
                    obj.temp_hitpoints,
                    obj.status,
                    obj.strength,
                    obj.dexterity,
                    obj.constitution,
                    obj.intelligence,
                    obj.wisdom,
                    obj.charisma,
                    obj.proficiency_bonus,
                    obj.save_skill_pattern,
                    obj.to_hit_bonus,
                ])

    def import_csv(self, path):
        """Replaces the entire creature list with path's contents.
        Every column past Initiative Roll is optional, for
        compatibility with older exports -- missing defaults to 0 (or
        "" for Status)."""
        with open(path, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        header_row = rows[0] if rows else []
        data_rows = rows[1:]

        def _int_col(row, index):
            return int(row[index]) if len(row) > index and row[index] else 0

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
                temp_hitpoints=_int_col(row, 5),
                status=row[6] if len(row) > 6 else "",
                strength=_int_col(row, 7),
                dexterity=_int_col(row, 8),
                constitution=_int_col(row, 9),
                intelligence=_int_col(row, 10),
                wisdom=_int_col(row, 11),
                charisma=_int_col(row, 12),
                proficiency_bonus=_int_col(row, 13),
                save_skill_pattern=_int_col(row, 14),
                to_hit_bonus=_int_col(row, 15),
            )
            new_objects.append(CreatureObject(creature))

        self.store.remove_all()
        for obj in new_objects:
            self.store.append(obj)

        self.current_creature = new_objects[0] if new_objects else None

        # Round number and mode are the header row's trailing cells.
        # A file with only one trailing cell predates the mode field;
        # disambiguated by header length against CSV_HEADERS.
        round_number = 1
        mode = 0
        if len(header_row) >= len(CSV_HEADERS) + 2:
            try:
                round_number = int(header_row[-2])
            except ValueError:
                round_number = 1
            try:
                mode = int(header_row[-1])
            except ValueError:
                mode = 0
        elif len(header_row) > 5:
            try:
                round_number = int(header_row[-1])
            except ValueError:
                round_number = 1
        self.round_number = round_number
        self.mode = mode
