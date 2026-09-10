"""Central keybind config: maps action names to GTK accelerators."""

KEYBINDS = {
    "app.quit": ["<Control>q"],
    "app.undo": ["<Control>z"],
    "app.redo": ["<Control>y", "<Control><Shift>z"],
    "win.new": ["<Control>n"],
    "win.import": ["<Control>o"],
    "win.export": ["<Control>e"],
    "win.add-creature": ["<Shift>a"],
    "win.next-turn": ["<Shift>space"],
}
