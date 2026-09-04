from gi.repository import Gio, Gtk

from window import AppWindow
from styling import install_css
from keybinds import KEYBINDS
from app_menus import build_menubar
from cinnamon_theme import sync_theme, reapply as reapply_theme


class Application(Gtk.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, application_id="net.mystive.sit", **kwargs)
        self.window = None

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

        for action_name, accels in KEYBINDS.items():
            self.set_accels_for_action(action_name, accels)

        self.set_menubar(build_menubar())

        install_css()
        self._theme_settings = sync_theme()

    def do_activate(self):
        if not self.window:
            self.window = AppWindow(application=self, title="Simple Initiative Tracker")
        self.window.present()
        reapply_theme()

    def on_quit(self, action, param):
        if self.window:
            self.window.close()
        else:
            self.quit()

    def on_undo(self, action, param):
        if self.window:
            self.window.perform_undo()

    def on_redo(self, action, param):
        if self.window:
            self.window.perform_redo()
