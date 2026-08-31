"""Central keybind configuration.

Maps action names (in "app.<name>" or "win.<name>" form, matching how
Gtk.Application.set_accels_for_action expects them -- both prefixes
work the same way, "win." for actions registered on the window rather
than the application) to a list of GTK accelerator strings. Edit this
file to change or add a keyboard shortcut without touching application
logic elsewhere -- application.py just iterates this dict and calls
set_accels_for_action for each entry.

Accelerator syntax: "<Control>z", "<Control><Shift>z", "<Alt>F4", etc.
Each action can have more than one accelerator; all of them will work.
"""

KEYBINDS = {
    "app.quit": ["<Control>q"],
    "app.undo": ["<Control>z"],
    # Ctrl+Y is the Windows convention for redo; Ctrl+Shift+Z is the more
    # common GNOME/Linux one. Both are bound rather than picking one.
    "app.redo": ["<Control>y", "<Control><Shift>z"],
    "win.new": ["<Control>n"],
}
