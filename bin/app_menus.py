"""Builds the Gio.Menu models shared between the headerbar's hamburger
popover and the traditional File menu bar, so the four New/Import/
Export/Export As items are defined in exactly one place."""

from gi.repository import Gio


def _file_actions_menu():
    menu = Gio.Menu()
    menu.append("New", "win.new")
    menu.append("Import", "win.import")
    menu.append("Export", "win.export")
    menu.append("Export As\u2026", "win.export-as")
    return menu


def _about_menu():
    menu = Gio.Menu()
    menu.append("About", "win.about")
    return menu


def build_hamburger_menu():
    menu = Gio.Menu()
    menu.append_section(None, _file_actions_menu())
    menu.append_section(None, _about_menu())
    return menu


def build_menubar():
    menu = Gio.Menu()
    menu.append_submenu("File", _file_actions_menu())
    menu.append_submenu("Help", _about_menu())
    return menu
