from pathlib import Path

UI_DIR = Path(__file__).resolve().parent.parent / "ui"

# Gtk.Builder.add_from_file() expects a plain string, not a Path object,
# so these are converted once here rather than at every call site.
FILE_PICKER_UI_PATH = str(UI_DIR / "file-picker.ui")
EDIT_FIELD_UI_PATH = str(UI_DIR / "edit-field.ui")
EDIT_HITPOINTS_UI_PATH = str(UI_DIR / "edit-hitpoints.ui")
ADD_CREATURE_UI_PATH = str(UI_DIR / "add-creature.ui")

CSV_HEADERS = ["Creature", "Hitpoints", "Max Hitpoints", "Armor Class", "Initiative Roll"]
