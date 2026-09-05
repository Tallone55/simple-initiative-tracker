"""Locations of the app's .ui files and icon. Resolved relative to
this file's own directory for normal/installed execution, or relative
to the frozen executable's data directory (sys._MEIPASS or
sys.executable) when bundled via e.g. PyInstaller."""

import sys
from pathlib import Path


def _resolve_ui_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", None) or Path(sys.executable).resolve().parent)
        return base / "ui"
    return Path(__file__).resolve().parent.parent / "ui"


UI_DIR = _resolve_ui_dir()

FILE_PICKER_UI_PATH = str(UI_DIR / "file-picker.ui")
EDIT_FIELD_UI_PATH = str(UI_DIR / "edit-field.ui")
EDIT_HITPOINTS_UI_PATH = str(UI_DIR / "edit-hitpoints.ui")
ADD_CREATURE_UI_PATH = str(UI_DIR / "add-creature.ui")
UNSAVED_CHANGES_UI_PATH = str(UI_DIR / "unsaved-changes.ui")
EDIT_ROUND_UI_PATH = str(UI_DIR / "edit-round.ui")
APP_ICON_PATH = str(UI_DIR / "net.mystive.sit.svg")
