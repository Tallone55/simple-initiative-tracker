"""Owns the app's relationship to a CSV file on disk: which file (if
any) is synced with in-memory state, unexported-changes tracking, and
the unsaved-changes/import/export/close flows built around that."""

import csv
from pathlib import Path

from gi.repository import Gio, Gtk, GLib

from ui_paths import FILE_PICKER_UI_PATH
from session_dialogs import open_unsaved_changes_dialog
from session_cache import read_last_file_path, write_last_file_path


class SessionManager:
    def __init__(self, window, initiative_database, undo_manager, on_state_changed):
        """on_state_changed(resort: bool) is called after a successful
        import (file-picker-driven or startup auto-load)."""
        self.window = window
        self.initiative_database = initiative_database
        self.undo_manager = undo_manager
        self.on_state_changed = on_state_changed

        self.last_file_path = None
        self.dirty = False
        self.base_title = window.get_title() or "Simple Initiative Tracker"
        self._after_export_callback = None

        self.file_dialog = self._load_file_dialog()

    # -- construction ------------------------------------------------

    def _load_file_dialog(self):
        builder = Gtk.Builder()
        builder.add_from_file(FILE_PICKER_UI_PATH)
        file_dialog = builder.get_object("file_chooser")

        csv_filter = Gtk.FileFilter()
        csv_filter.set_name("CSV files")
        csv_filter.add_suffix("csv")
        filters = Gio.ListStore(item_type=Gtk.FileFilter)
        filters.append(csv_filter)
        file_dialog.set_filters(filters)

        return file_dialog

    # -- dirty tracking ------------------------------------------------

    def mark_dirty(self):
        self._set_dirty(True)

    def _set_dirty(self, value):
        self.dirty = value
        self.window.set_title(f"*{self.base_title}" if value else self.base_title)

    # -- startup ------------------------------------------------

    def load_cached_file_on_startup(self):
        cached_path = read_last_file_path()
        if not cached_path:
            return
        if not Path(cached_path).is_file():
            self.window.show_status(f"Last file not found, skipping auto-load: {cached_path}")
            return
        self._import_from_path(cached_path)

    # -- new ------------------------------------------------

    def try_new(self):
        self._after_export_callback = None
        if self.dirty:
            open_unsaved_changes_dialog(
                self.window,
                on_export=self._export_then_new,
                on_discard=self._begin_new,
                message=(
                    "You have unexported changes. Starting a new "
                    "initiative order will discard the current list. "
                    "Export first?"
                ),
            )
        else:
            self._begin_new()

    def _export_then_new(self):
        self._after_export_callback = self._begin_new
        if self.last_file_path:
            self._export_to_path(self.last_file_path)
        else:
            self._open_export_dialog()

    def _begin_new(self):
        self.initiative_database.clear()
        self.undo_manager.clear()
        self.last_file_path = None
        self._set_dirty(False)
        self.on_state_changed(resort=False)
        self.window.show_status("Started a new initiative order.")

    # -- import ------------------------------------------------

    def try_import(self):
        self._after_export_callback = None
        if self.dirty:
            open_unsaved_changes_dialog(
                self.window,
                on_export=self._export_then_import,
                on_discard=self._begin_import,
                message=(
                    "You have unexported changes. Importing will replace "
                    "the current list. Export first?"
                ),
            )
        else:
            self._begin_import()

    def _export_then_import(self):
        self._after_export_callback = self._begin_import
        if self.last_file_path:
            self._export_to_path(self.last_file_path)
        else:
            self._open_export_dialog()

    def _begin_import(self):
        self.file_dialog.set_title("Import Initiative Tracker (CSV)")
        self.file_dialog.open(self.window, None, self._on_import_dialog_open)

    def _on_import_dialog_open(self, dialog, result):
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error as e:
            if e.matches(Gtk.DialogError.quark(), Gtk.DialogError.DISMISSED):
                return
            self.window.show_status(f"Error opening file dialog: {e.message}")
            return

        if gfile is None:
            return

        self._import_from_path(gfile.get_path())

    def _import_from_path(self, path):
        try:
            self.initiative_database.import_csv(path)
        except (OSError, csv.Error, ValueError) as e:
            self.window.show_status(f"Import failed: {e}")
            return

        self.last_file_path = path
        write_last_file_path(path)
        self.undo_manager.clear()
        self._set_dirty(False)
        self.on_state_changed(resort=True)
        self.window.show_status(f"Imported {path}")

    # -- export ------------------------------------------------

    def try_export(self):
        self._after_export_callback = None
        if self.last_file_path:
            self._export_to_path(self.last_file_path)
        else:
            self._open_export_dialog()

    def try_export_as(self):
        self._after_export_callback = None
        self._open_export_dialog()

    def _open_export_dialog(self):
        self.file_dialog.set_title("Export Initiative Tracker (CSV)")
        self.file_dialog.set_initial_name("initiative.csv")
        self.file_dialog.save(self.window, None, self._on_export_dialog_save)

    def _on_export_dialog_save(self, dialog, result):
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error as e:
            if e.matches(Gtk.DialogError.quark(), Gtk.DialogError.DISMISSED):
                return
            self.window.show_status(f"Error opening file dialog: {e.message}")
            return

        if gfile is None:
            return

        self._export_to_path(gfile.get_path())

    def _export_to_path(self, path):
        try:
            self.initiative_database.export_csv(path)
        except OSError as e:
            self.window.show_status(f"Export failed: {e}")
            return

        self.last_file_path = path
        write_last_file_path(path)
        self._set_dirty(False)
        self.window.show_status(f"Exported to {path}")

        if self._after_export_callback is not None:
            callback = self._after_export_callback
            self._after_export_callback = None
            callback()

    # -- close ------------------------------------------------

    def try_close(self) -> bool:
        """Returns True if the close should be blocked (handled here,
        possibly asynchronously), False if it should proceed."""
        if not self.dirty:
            return False

        open_unsaved_changes_dialog(
            self.window,
            on_export=self._export_then_close,
            on_discard=self.window.destroy,
            message="You have unexported changes. Export before closing?",
        )
        return True

    def _export_then_close(self):
        self._after_export_callback = self.window.destroy
        if self.last_file_path:
            self._export_to_path(self.last_file_path)
        else:
            self._open_export_dialog()
