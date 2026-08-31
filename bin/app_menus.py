"""Builds the Gio.Menu models shared between the GNOME-style hamburger
popover (packed into the headerbar, see window.py) and the traditional
"File" menu bar (Gtk.Application.set_menubar(), see application.py) --
for platforms where a headerbar hamburger isn't the native convention.

Both reference the same win.* actions registered on AppWindow, so
there's exactly one place these four menu items are defined, rather
than two copies that could drift apart.

Whether the traditional menu bar actually renders as visible, in-window
content depends on the platform and the gtk-shell-shows-menubar
setting -- outside our control, and by design: it's meant to adapt
automatically rather than being something we decide ourselves.
"""

from gi.repository import Gio


def _file_actions_menu():
    menu = Gio.Menu()
    menu.append("New", "win.new")
    menu.append("Import", "win.import")
    menu.append("Export", "win.export")
    menu.append("Export As\u2026", "win.export-as")
    return menu


def build_hamburger_menu():
    """Flat menu for the headerbar's hamburger MenuButton -- no "File"
    submenu label needed, since the hamburger icon itself signals
    "menu"."""
    return _file_actions_menu()


def build_menubar():
    """Traditional menu bar with a single "File" top-level entry, for
    Gtk.Application.set_menubar()."""
    menu = Gio.Menu()
    menu.append_submenu("File", _file_actions_menu())
    return menu
