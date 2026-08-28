import csv

from gi.repository import Gio, Gtk, GLib

from constants import FILE_PICKER_UI_PATH, CSV_HEADERS
from models import InitiativeDatabase
from dialogs import open_edit_dialog, open_add_creature_dialog
from row_factory import CreatureRowFactory


class AppWindow(Gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_default_size(720, 480)

        self.initiative_database = InitiativeDatabase()
        self.last_file_path = None

        self.row_factory = CreatureRowFactory(
            on_edit_requested=self._handle_edit_requested,
            on_remove_requested=self._handle_remove_requested,
            is_current_fn=lambda c: self.initiative_database.current_creature is c,
        )

        self.file_dialog = self._load_file_dialog()

        root = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            margin_top=6, margin_bottom=6, margin_start=6, margin_end=6,
        )
        self.set_child(root)

        root.append(self._build_toolbar())
        root.append(self._build_column_header())

        selection_model = Gtk.NoSelection(model=self.initiative_database.sorted_model)
        self.list_view = Gtk.ListView(
            model=selection_model, factory=self.row_factory.factory, vexpand=True
        )
        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.set_child(self.list_view)
        root.append(scrolled)

        self.status_label = Gtk.Label(label="", xalign=0)
        self.status_label.add_css_class("dim-label")
        root.append(self.status_label)

    # -- construction helpers ------------------------------------------------

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

    def _build_toolbar(self):
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        add_button = Gtk.Button(label="Add Creature")
        add_button.connect("clicked", self.on_add_creature_clicked)
        toolbar.append(add_button)

        next_turn_button = Gtk.Button(label="Next Turn")
        next_turn_button.connect("clicked", self.on_next_turn_clicked)
        toolbar.append(next_turn_button)

        import_button = Gtk.Button(label="Import")
        import_button.connect("clicked", self.on_import_clicked)
        toolbar.append(import_button)

        export_button = Gtk.Button(label="Export")
        export_button.connect("clicked", self.on_export_clicked)
        toolbar.append(export_button)

        return toolbar

    def _build_column_header(self):
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for text in (*CSV_HEADERS, ""):
            lbl = Gtk.Label(label=text, hexpand=True, xalign=0)
            lbl.add_css_class("heading")
            header.append(lbl)
        return header

    # -- shared post-mutation refresh -------------------------------------

    def after_database_mutation(self, resort=False):
        """The single place every mutation (add/remove/edit/next-turn/
        import) routes through afterwards, so sorting and the current-turn
        highlight always stay in sync with the database."""
        if resort:
            self.initiative_database.resort()
        self.row_factory.refresh_highlights()

    def show_status(self, message):
        self.status_label.set_text(message)

    # -- row factory callbacks ------------------------------------------------

    def _handle_edit_requested(self, creature_obj, field_name, display_name):
        open_edit_dialog(
            self, creature_obj, field_name, display_name, self.after_database_mutation
        )

    def _handle_remove_requested(self, creature_obj):
        self.initiative_database.remove_creature(creature_obj)
        self.after_database_mutation(resort=False)

    # -- toolbar actions ------------------------------------------------

    def on_next_turn_clicked(self, button):
        self.initiative_database.next_turn()
        self.after_database_mutation(resort=False)

    def on_add_creature_clicked(self, button):
        open_add_creature_dialog(self, self._handle_creature_added)

    def _handle_creature_added(self, creature):
        self.initiative_database.add_creature(creature)
        self.after_database_mutation(resort=True)

    # -- import / export ------------------------------------------------

    def on_import_clicked(self, button):
        self.file_dialog.set_title("Import Initiative Tracker (CSV)")
        self.file_dialog.open(self, None, self.on_import_dialog_open)

    def on_import_dialog_open(self, dialog, result):
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error as e:
            if e.matches(Gtk.DialogError.quark(), Gtk.DialogError.DISMISSED):
                return
            self.show_status(f"Error opening file dialog: {e.message}")
            return

        if gfile is None:
            return

        path = gfile.get_path()
        try:
            self.initiative_database.import_csv(path)
        except (OSError, csv.Error, ValueError) as e:
            self.show_status(f"Import failed: {e}")
            return

        self.last_file_path = path
        self.after_database_mutation(resort=True)
        self.show_status(f"Imported {path}")

    def on_export_clicked(self, button):
        if self.last_file_path:
            self.export_to_path(self.last_file_path)
            return

        self.file_dialog.set_title("Export Initiative Tracker (CSV)")
        self.file_dialog.set_initial_name("initiative.csv")
        self.file_dialog.save(self, None, self.on_export_dialog_save)

    def on_export_dialog_save(self, dialog, result):
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error as e:
            if e.matches(Gtk.DialogError.quark(), Gtk.DialogError.DISMISSED):
                return
            self.show_status(f"Error opening file dialog: {e.message}")
            return

        if gfile is None:
            return

        self.export_to_path(gfile.get_path())

    def export_to_path(self, path):
        try:
            self.initiative_database.export_csv(path)
        except OSError as e:
            self.show_status(f"Export failed: {e}")
            return

        self.last_file_path = path
        self.show_status(f"Exported to {path}")
