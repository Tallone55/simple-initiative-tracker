"""The app's two display/data modes -- see window.py's mode-switcher
popover, column_factory.py's combat-only columns, and
creature_dialogs.py's mode-conditional ability-score fields.

Persisted via models.py's InitiativeDatabase.mode -- a plain int (see
MODE_TO_INT/INT_TO_MODE below), stored as CSV_HEADERS' second trailing
header-row cell, right beside the round number. Kept as a plain int at
the models.py layer rather than importing this Mode enum there, since
models.py is otherwise deliberately UI-agnostic ("no widgets here, so
this is testable without a display") -- window.py is what converts
between the two, at both ends (see AppWindow._set_mode and
_handle_state_changed)."""

from enum import Enum


class Mode(Enum):
    SIMPLE = "simple"
    COMBAT_5E = "5e_combat"


MODE_LABELS = {
    Mode.SIMPLE: "Simple",
    Mode.COMBAT_5E: "5e Combat",
}

MODE_TO_INT = {
    Mode.SIMPLE: 0,
    Mode.COMBAT_5E: 1,
}
# Reverse mapping, with a safe fallback to Simple mode for any
# unrecognized value (a hand-edited or corrupted CSV, or one written
# by some future version with more modes than this one knows about).
INT_TO_MODE = {value: mode for mode, value in MODE_TO_INT.items()}


def mode_from_int(value):
    return INT_TO_MODE.get(value, Mode.SIMPLE)
