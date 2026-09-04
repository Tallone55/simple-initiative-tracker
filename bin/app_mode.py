"""The app's two display/data modes. Persisted as a plain int (see
MODE_TO_INT) in the CSV, alongside the round number."""

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
INT_TO_MODE = {value: mode for mode, value in MODE_TO_INT.items()}


def mode_from_int(value):
    return INT_TO_MODE.get(value, Mode.SIMPLE)
