"""Central keybind configuration: maps "app.<name>"/"win.<name>" action
names to GTK accelerator strings. Application.py iterates this dict and
calls set_accels_for_action for each entry, so shortcuts are changed
here only."""

KEYBINDS = {
    "app.quit": ["<Control>q"],
    "app.undo": ["<Control>z"],
    "app.redo": ["<Control>y", "<Control><Shift>z"],  # Windows + GNOME conventions
    "win.new": ["<Control>n"],
}
