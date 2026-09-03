"""Data layer: the plain Creature record, its GObject wrapper for use in
GTK list models, and the InitiativeDatabase that owns the sorted,
current-turn-aware collection of creatures. No widgets here, so this is
testable without a display."""

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

# (skill name, governing ability) -- the standard 5e list, 18 entries,
# grouped by ability to match how creature_stats_dialog.py displays
# them (Constitution governs no skills, same as the real rules).
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

# Skills grouped by governing ability, in SKILLS' own order, for
# creature_stats_dialog.py's per-ability row layout (e.g.
# SKILLS_BY_ABILITY["intelligence"] == ["Arcana", "History",
# "Investigation", "Nature", "Religion"]). Every ability is present as
# a key even if its list is empty (Constitution has no skills in 5e).
SKILLS_BY_ABILITY = {ability: [] for ability in ABILITIES}
for _skill_name, _governing_ability in SKILLS:
    SKILLS_BY_ABILITY[_governing_ability].append(_skill_name)

# The 24 "positions" referenced throughout this module and
# creature_stats_dialog.py: the 6 saving throws (one per ability, in
# ABILITIES order) come first, then the 18 skills (in SKILLS order).
_POSITIONS = list(ABILITIES) + SKILL_NAMES
NUM_POSITIONS = len(_POSITIONS)
assert NUM_POSITIONS == 24


def position_index(kind, name):
    """0-based position within the 24-entry proficiency/advantage
    pattern for a saving throw (kind="save", name=one of ABILITIES) or
    a skill (kind="skill", name=one of SKILL_NAMES)."""
    if kind == "save":
        return ABILITIES.index(name)
    return 6 + SKILL_NAMES.index(name)


def ability_modifier(score):
    """Standard 5e ability modifier: floor((score - 10) / 2) -- e.g.
    16 -> +3, 7 -> -2. Python's // already floors toward negative
    infinity (not just truncates toward zero), which is exactly the
    rounding 5e's own rule uses, so no special-casing is needed for
    the negative/odd-difference case."""
    return (score - 10) // 2


# -- proficiency/advantage pattern encoding ------------------------------------------------
#
# Stored as a single integer (Creature.save_skill_pattern / CSV column
# "Save/Skill Pattern") covering all 24 positions' proficiency level
# AND advantage together, so a creature's entire saving-throw/skill
# configuration round-trips through one CSV cell:
#
#   - Proficiency level per position is one base-3 "trit" (0 = none,
#     1 = proficient, 2 = expertise) -- skills genuinely use all three
#     values; saving throws only ever use 0 or 1 (5e has no saving
#     throw expertise), but still get a full trit each for a uniform
#     24-trit encoding rather than a mix of different bases. All 24
#     trits packed into one base-3 number gives "24 positions worth of
#     trinary data," i.e. a value from 0 to 3**24 - 1.
#   - Advantage per position is a single bit (0/1), independent of
#     proficiency level, packed into a 24-bit number.
#   - The two are combined into one integer as
#     (advantage_bits * 3**24) + proficiency_trits: 3**24 is larger
#     than any possible value of the trit part, so the two halves
#     never collide and can be split back apart with plain // and %.

_TRIT_BASE = 3 ** NUM_POSITIONS  # one past the max value the trit half can take


def encode_pattern(proficiency_levels, advantages):
    """proficiency_levels: 24 ints, each 0/1/2 (position order -- see
    _POSITIONS). advantages: 24 truthy/falsy values, same order.
    Returns the single combined integer described above."""
    prof_code = 0
    for i, level in enumerate(proficiency_levels):
        prof_code += level * (3 ** i)
    adv_code = 0
    for i, advantage in enumerate(advantages):
        if advantage:
            adv_code |= (1 << i)
    return prof_code + adv_code * _TRIT_BASE


def decode_pattern(value):
    """Inverse of encode_pattern -- returns (proficiency_levels,
    advantages), each a 24-entry list in position order."""
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
    stats. CreatureObject below just exposes it to GTK.

    The six ability scores default to 0, meaning "not set" (blank in
    every UI that displays them) rather than a real ability score --
    matching every other optional numeric field in this module
    (temp_hitpoints). Dexterity is the only one usable outside 5e
    Combat mode (Simple mode's Add Creature dialog exposes just that
    one field, for breaking initiative ties -- see
    InitiativeDatabase._compare below); the other five, along with
    proficiency_bonus and save_skill_pattern, are only editable via
    the full stat-block window (creature_stats_dialog.py), opened from
    the crossed-swords column (5e Combat mode only)."""
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
    """GObject wrapper around a Creature dataclass instance, since
    Gio.ListStore/Gtk.SortListModel/Gtk.ColumnView only accept
    GObject-derived items."""

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

    # int64, not the default 32-bit int: the encoded value can exceed
    # 2**31 (see encode_pattern's own docstring for the exact range --
    # up to roughly 4.7e18, safely within int64 but not int32).
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
        # A plain int, not app_mode.Mode -- see app_mode.py's own
        # docstring for why the enum<->int conversion happens in
        # window.py instead of here. 0 (Mode.SIMPLE) by default.
        self.mode = 0

    @staticmethod
    def _compare(a, b, user_data=None):
        if a.initiative_roll != b.initiative_roll:
            return -1 if a.initiative_roll > b.initiative_roll else 1
        # Standard 5e tie-break: higher Dexterity acts first. Only
        # actually distinguishes two creatures when both have a
        # nonzero (i.e. actually entered) Dexterity -- 0 means "not
        # set" here, same as everywhere else this module treats an
        # optional stat, so two untouched creatures with equal
        # initiative still just fall through to the arbitrary (but
        # stable) order below, same as before Dexterity existed.
        if a.dexterity != b.dexterity:
            return -1 if a.dexterity > b.dexterity else 1
        return 0

    def _sorted_list(self):
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
        """Call after a mutation that could change turn order (any
        edit to initiative_roll, or an add)."""
        self.sorter.changed(Gtk.SorterChange.DIFFERENT)

    def add_creature(self, creature: Creature) -> CreatureObject:
        """Adds a new creature. A new arrival's higher roll only jumps
        the queue if whoever currently has the turn was already at the
        top of the order -- mid-round, adding creatures shouldn't
        disrupt whoever's turn it already is."""
        current_was_top = self.current_creature is not None and self._current_index() == 0

        obj = CreatureObject(creature)
        self.store.append(obj)

        if self.current_creature is None:
            self.current_creature = obj
        elif current_was_top and obj.initiative_roll > self.current_creature.initiative_roll:
            self.current_creature = obj

        return obj

    def set_current_creature(self, creature_obj: CreatureObject):
        """Manually overrides whose turn it is (distinct from
        next_turn(), which advances turn order)."""
        self.current_creature = creature_obj

    def clear(self):
        """Resets to a fresh, empty initiative order -- used by "New"."""
        self.store.remove_all()
        self.current_creature = None
        self.round_number = 1
        self.mode = 0

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
        """Advances to the next creature in turn order, wrapping to the
        top and incrementing round_number when a full cycle completes."""
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
        """Writes the full creature list to path as CSV, current
        creature first followed by the rest in turn order (wrapping
        around), with the round number and display mode appended to
        the header row (in that order)."""
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
        """Replaces the entire creature list with the contents of
        path. The header row is skipped for creature data but its
        trailing cell (if present) is read back as the round number.
        Malformed data rows (fewer than 5 columns) are skipped.
        Temp Hitpoints (column 6), Status (column 7), the six ability
        scores (columns 8-13), Proficiency Bonus (column 14), the
        Save/Skill Pattern (column 15), and To-Hit Bonus (column 16)
        are all optional, for compatibility with files exported before
        those fields existed -- missing entirely defaults to 0 (or ""
        for Status)."""
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

        # First row is, by our export convention, whoever's turn it is.
        self.current_creature = new_objects[0] if new_objects else None

        # Round number and display mode, if present, are the header
        # row's trailing cells, in that order -- files from before
        # each feature existed won't have them. A file with only ONE
        # trailing cell (everything exported before display mode
        # existed) has just the round number; disambiguated from a
        # genuine two-cell (round, mode) pair by whether the header
        # row is at least 2 cells longer than the current CSV_HEADERS
        # -- robust to CSV_HEADERS itself having grown since a given
        # file was exported, the same reasoning the single-cell
        # version of this check already relied on.
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
