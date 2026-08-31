"""Locations of the app's .ui files -- the single source of truth for
where each dialog's XML definition lives on disk.

Resolved two different ways depending on how the app is running:
- Normal (unfrozen) execution, or installed via the .deb package: the
  ui/ directory is a sibling of the directory this file itself lives
  in, so it's resolved relative to __file__.
- Frozen/bundled execution (e.g. via PyInstaller): __file__-relative
  resolution doesn't hold, since a frozen build's runtime file layout
  is entirely different from the source tree's -- a onefile build
  extracts bundled data to a temp directory (sys._MEIPASS), while a
  onedir build places it alongside the executable itself.
"""

import sys
from pathlib import Path


def _resolve_ui_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", None) or Path(sys.executable).resolve().parent)
        return base / "ui"
    return Path(__file__).resolve().parent.parent / "ui"


UI_DIR = _resolve_ui_dir()

# Gtk.Builder.add_from_file() expects a plain string, not a Path object,
# so these are converted once here rather than at every call site.
FILE_PICKER_UI_PATH = str(UI_DIR / "file-picker.ui")
EDIT_FIELD_UI_PATH = str(UI_DIR / "edit-field.ui")
EDIT_HITPOINTS_UI_PATH = str(UI_DIR / "edit-hitpoints.ui")
ADD_CREATURE_UI_PATH = str(UI_DIR / "add-creature.ui")
UNSAVED_CHANGES_UI_PATH = str(UI_DIR / "unsaved-changes.ui")
