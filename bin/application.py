from gi.repository import Gio, Gtk

from window import AppWindow
from styling import install_css


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

        install_css()

    # Run on process activation (executable invoked through any means)
    def do_activate(self):
        if not self.window:
            # This line invokes the actual application.
            self.window = AppWindow(application=self, title="Simple Initiative Tracker")
        self.window.present()

    def on_quit(self, action, param):
        self.quit()
