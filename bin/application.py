from gi.repository import Gio, Gtk

from window import AppWindow
from styling import install_css
from keybinds import KEYBINDS


class Application(Gtk.Application):
    def __init__(self, *args, **kwargs):
        # SIT: Simple Initiative Tracker
        super().__init__(*args, application_id="net.mystive.sit", **kwargs)
        self.window = None

    # Run on process registration, once
    def do_startup(self):
        Gtk.Application.do_startup(self)

        quit_action = Gio.SimpleAction(name="quit")
        quit_action.connect("activate", self.on_quit)
        self.add_action(quit_action)

        undo_action = Gio.SimpleAction(name="undo")
        undo_action.connect("activate", self.on_undo)
        self.add_action(undo_action)

        redo_action = Gio.SimpleAction(name="redo")
        redo_action.connect("activate", self.on_redo)
        self.add_action(redo_action)

        # Accelerators are driven entirely by keybinds.py rather than
        # hardcoded here -- change a shortcut by editing that file only.
        for action_name, accels in KEYBINDS.items():
            self.set_accels_for_action(action_name, accels)

        install_css()

    # Run on process activation (executable invoked through any means)
    def do_activate(self):
        if not self.window:
            # Construct the main window.
            self.window = AppWindow(application=self, title="Simple Initiative Tracker")
        self.window.present()

    def on_quit(self, action, param):
        """app.quit action handler (Ctrl+Q or any Quit menu item)."""
        if self.window:
            # Route through the window's own close sequence rather than
            # quitting directly, so the unsaved-changes check (hooked
            # into "close-request") gets a chance to run.
            self.window.close()
        else:
            self.quit()

    def on_undo(self, action, param):
        """app.undo action handler (Ctrl+Z)."""
        if self.window:
            self.window.perform_undo()

    def on_redo(self, action, param):
        """app.redo action handler (Ctrl+Y / Ctrl+Shift+Z)."""
        if self.window:
            self.window.perform_redo()
