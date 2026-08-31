from gi.repository import Gio, Gtk

from window import AppWindow
from styling import install_css
from keybinds import KEYBINDS
from app_menus import build_menubar
from theme_sync import sync_theme, reapply as reapply_theme
import adwaita

# Adw.Application when libadwaita is available -- this is what
# actually triggers libadwaita's own native theme integration
# (including Linux Mint's patched build reading real system theme
# colors directly, see theme_sync.py's module docstring), rather than
# theme_sync.py's own approximated fallback CSS, which is used only
# when libadwaita genuinely isn't installed. Every other widget in
# this app (Gtk.HeaderBar, Gtk.ColumnView, etc.) stays exactly as-is
# either way -- libadwaita's stylesheet applies through shared GTK CSS
# node names, not by requiring Adw-specific widget classes.
_ApplicationBase = adwaita.Adw.Application if adwaita.AVAILABLE else Gtk.Application


class Application(_ApplicationBase):
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

        # Traditional "File" menu bar, for platforms where a headerbar
        # hamburger menu (see window.py) isn't the native convention.
        # References the same win.* actions the headerbar menu does --
        # both are built from app_menus.py so there's one definition,
        # not two that could drift apart.
        self.set_menubar(build_menubar())

        # See theme_sync.py -- detects and applies the desktop's
        # dark/light preference across DEs, including a fallback dark
        # palette for cases where the system's own theme has nothing
        # GTK4 can actually load.
        self._theme_settings = sync_theme()

        install_css()

    # Run on process activation (executable invoked through any means)
    def do_activate(self):
        if not self.window:
            # Construct the main window.
            self.window = AppWindow(application=self, title="Simple Initiative Tracker")
        self.window.present()

        # Re-asserts the already-known dark/light preference now that
        # the window (and its headerbar's window-control buttons)
        # actually exist -- see theme_sync.reapply()'s docstring for
        # why this second application is needed at all.
        reapply_theme()

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
