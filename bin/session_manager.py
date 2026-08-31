"""Owns the app's relationship to a CSV file on disk: which file (if
any) the in-memory state is synced with, whether there are unexported
changes, and the flows built around that -- the unsaved-changes prompt
(shared by closing and importing), remembering the last file across
launches, and the "export first, then do X" sequencing used by both.

Deliberately separate from AppWindow: this is file-persistence policy,
not table/dialog UI construction. It still needs a reference to the
window (as transient_for for its dialogs, and to call show_status/
set_title/destroy), but doesn't build or own any of the window's main
widgets.
"""

import csv
from pathlib import Path

from gi.repository import Gio, Gtk, GLib

from ui_paths import FILE_PICKER_UI_PATH
from session_dialogs import open_unsaved_changes_dialog
from session_cache import read_last_file_path, write_last_file_path


class SessionManager:
    def __init__(self, window, initiative_database, undo_manager, on_state_changed):
        """
        window -- the AppWindow: used as transient_for for dialogs and
            for show_status()/set_title()/destroy().
        initiative_database -- the InitiativeDatabase to import/export.
        undo_manager -- cleared on import, since old commands would
            reference creature objects no longer in the store.
        on_state_changed(resort: bool) -- called after a successful
            import (file-picker-driven or startup auto-load) so the
            caller can refresh selection/round display/etc. Not called
            after export, since export doesn't change in-memory state.
        """
        self.window = window
        self.initiative_database = initiative_database
        self.undo_manager = undo_manager
        self.on_state_changed = on_state_changed

        self.last_file_path = None
        self.dirty = False
        # Captured once, right after the window's "title" property is
        # set, so the dirty-indicator ("*") logic below has a single
        # source of truth rather than duplicating the literal title
        # string here and in application.py.
        self.base_title = window.get_title() or "Simple Initiative Tracker"
        # Set to a no-argument callable when an export is happening as a
        # precursor to some other action (closing the window, starting
        # an import) rather than a plain toolbar export -- invoked once
        # by _export_to_path after a successful export, then cleared.
        self._after_export_callback = None

        self.file_dialog = self._load_file_dialog()

    # -- construction ------------------------------------------------

    def _load_file_dialog(self):
        """Builds the shared Gtk.FileDialog used for both import and
        export, pre-configured with a CSV file filter."""
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
        """Called by AppWindow after any creature mutation."""
        self._set_dirty(True)

    def _set_dirty(self, value):
        """Sets dirty state and reflects it in the window title (a
        leading "*") so it's visible at a glance, not just enforced
        when closing/importing."""
        self.dirty = value
        self.window.set_title(f"*{self.base_title}" if value else self.base_title)

    # -- startup ------------------------------------------------

    def load_cached_file_on_startup(self):
        """Reads the session cache (see session_cache.py) and, if it
        points at a file that still exists, imports it automatically."""
        cached_path = read_last_file_path()
        if not cached_path:
            return
        if not Path(cached_path).is_file():
            self.window.show_status(f"Last file not found, skipping auto-load: {cached_path}")
            return
        self._import_from_path(cached_path)

    # -- new ------------------------------------------------

    def try_new(self):
        """Entry point for the New action (menu item / Ctrl+N). Checks
        for unsaved changes first, since starting fresh discards the
        whole current list -- proceeds straight to clearing if there's
        nothing to lose."""
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
        """Chosen from the unsaved-changes dialog: export first, then
        clear to a fresh session once the export succeeds."""
        self._after_export_callback = self._begin_new
        if self.last_file_path:
            self._export_to_path(self.last_file_path)
        else:
            self._open_export_dialog()

    def _begin_new(self):
        self.initiative_database.clear()
        self.undo_manager.clear()
        # New means "no longer working with any particular file" --
        # unlike import, which is still associated with the file it
        # just loaded. A later Export should prompt for a location
        # rather than silently overwriting whatever was open before.
        self.last_file_path = None
        self._set_dirty(False)
        self.on_state_changed(resort=False)
        self.window.show_status("Started a new initiative order.")

    # -- import ------------------------------------------------

    def try_import(self):
        """Entry point for the Import button. Checks for unsaved
        changes first, since importing replaces the whole creature
        list -- proceeds straight to the file picker if there's
        nothing to lose."""
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
        """Chosen from the unsaved-changes dialog: export first, then
        proceed to the import file picker once the export succeeds."""
        self._after_export_callback = self._begin_import
        if self.last_file_path:
            self._export_to_path(self.last_file_path)
        else:
            self._open_export_dialog()

    def _begin_import(self):
        """Opens the file picker to choose a CSV to import."""
        self.file_dialog.set_title("Import Initiative Tracker (CSV)")
        self.file_dialog.open(self.window, None, self._on_import_dialog_open)

    def _on_import_dialog_open(self, dialog, result):
        """Gtk.FileDialog.open() callback -- resolves the chosen file
        and hands it to _import_from_path."""
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
        """Shared by the file-picker-driven import flow and the
        startup auto-load, so both go through identical success/failure
        handling."""
        try:
            self.initiative_database.import_csv(path)
        except (OSError, csv.Error, ValueError) as e:
            self.window.show_status(f"Import failed: {e}")
            return

        self.last_file_path = path
        write_last_file_path(path)
        # Import replaces the whole in-memory state -- old undo/redo
        # commands would reference creature objects no longer in the
        # store, so the history stops being meaningful here.
        self.undo_manager.clear()
        self._set_dirty(False)
        self.on_state_changed(resort=True)
        self.window.show_status(f"Imported {path}")

    # -- export ------------------------------------------------

    def try_export(self):
        """Export to the last-used path; if none is known yet, this
        behaves the same as Export As."""
        self._after_export_callback = None
        if self.last_file_path:
            self._export_to_path(self.last_file_path)
        else:
            self._open_export_dialog()

    def try_export_as(self):
        """Always prompts for a location, regardless of any remembered
        last_file_path."""
        self._after_export_callback = None
        self._open_export_dialog()

    def _open_export_dialog(self):
        """Opens the file picker to choose a CSV export location."""
        self.file_dialog.set_title("Export Initiative Tracker (CSV)")
        self.file_dialog.set_initial_name("initiative.csv")
        self.file_dialog.save(self.window, None, self._on_export_dialog_save)

    def _on_export_dialog_save(self, dialog, result):
        """Gtk.FileDialog.save() callback -- resolves the chosen
        location and hands it to _export_to_path."""
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
        """Writes the current creature list to path as CSV, updates the
        session cache and dirty state on success, and runs any pending
        _after_export_callback (see its assignment sites for what that
        covers)."""
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
        """Called from AppWindow's "close-request" handler. Returns
        True if the close should be blocked (we're handling it,
        possibly asynchronously via the export flow), False if it
        should proceed immediately."""
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
        """Chosen from the unsaved-changes dialog: export first, then
        actually close the window once the export succeeds."""
        self._after_export_callback = self.window.destroy
        if self.last_file_path:
            self._export_to_path(self.last_file_path)
        else:
            self._open_export_dialog()