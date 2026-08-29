import csv

from gi.repository import Gio, Gtk, GLib

from constants import FILE_PICKER_UI_PATH
from models import InitiativeDatabase
from dialogs import open_edit_dialog, open_edit_hitpoints_dialog, open_add_creature_dialog
from column_factory import CreatureColumnFactory


class AppWindow(Gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_default_size(760, 480)

        self.initiative_database = InitiativeDatabase()
        self.last_file_path = None

        self.creature_columns = CreatureColumnFactory(
            on_edit_requested=self._handle_edit_requested,
            on_hitpoints_edit_requested=self._handle_hitpoints_edit_requested,
            on_remove_requested=self._handle_remove_requested,
        )

        self.file_dialog = self._load_file_dialog()

        root = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            margin_top=4, margin_bottom=4, margin_start=4, margin_end=4,
        )
        self.set_child(root)

        root.append(self._build_toolbar())
        self.update_round_label()

        # Native row selection gives us full-row highlighting for free,
        # instead of the earlier per-cell CSS-class approach. Selection
        # is normally driven by our own code (_sync_selection, called
        # after any real state change) rather than raw clicks -- but a
        # single click can still cause a transient native selection on
        # its own (see column_factory.py), which just gets overwritten
        # the next time something actually changes state.
        #
        # Turn activation is via the native "activate" signal (fires on
        # double-click by default -- single_click_activate is False
        # below to make that explicit rather than relying on the default).
        self.selection_model = Gtk.SingleSelection(model=self.initiative_database.sorted_model)
        self.selection_model.set_autoselect(False)
        self.selection_model.set_can_unselect(True)
        self.column_view = Gtk.ColumnView(model=self.selection_model, vexpand=True)
        self.column_view.set_single_click_activate(False)
        self.column_view.connect("activate", self._on_row_activated)
        for column in self.creature_columns.columns:
            self.column_view.append_column(column)

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.set_child(self.column_view)
        root.append(scrolled)

        self.status_label = Gtk.Label(label="", xalign=0)
        self.status_label.add_css_class("dim-label")
        root.append(self.status_label)

        self._sync_selection()

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
        # Left group: creature/turn management. Right group: file I/O.
        # A CenterBox keeps them pinned to opposite ends regardless of
        # window width, giving a clean visual split between the two
        # kinds of action.
        left_group = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        add_button = Gtk.Button(label="Add Creature")
        add_button.add_css_class("action-add")
        add_button.connect("clicked", self.on_add_creature_clicked)
        left_group.append(add_button)

        next_turn_button = Gtk.Button(label="Next Turn")
        next_turn_button.add_css_class("action-next-turn")
        next_turn_button.connect("clicked", self.on_next_turn_clicked)
        left_group.append(next_turn_button)

        right_group = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        import_button = Gtk.Button(label="Import")
        import_button.connect("clicked", self.on_import_clicked)
        right_group.append(import_button)

        export_button = Gtk.Button(label="Export")
        export_button.connect("clicked", self.on_export_clicked)
        right_group.append(export_button)

        export_as_button = Gtk.Button(label="Export As\u2026")
        export_as_button.connect("clicked", self.on_export_as_clicked)
        right_group.append(export_as_button)

        self.round_label = Gtk.Label(label="Round 1")
        self.round_label.add_css_class("round-counter")

        toolbar = Gtk.CenterBox(orientation=Gtk.Orientation.HORIZONTAL)
        toolbar.set_start_widget(left_group)
        toolbar.set_center_widget(self.round_label)
        toolbar.set_end_widget(right_group)
        return toolbar

    # -- shared post-mutation refresh -------------------------------------

    def after_database_mutation(self, resort=False):
        """The single place every mutation (add/remove/edit/next-turn/
        import) routes through afterwards, so sorting, the current-turn
        selection, and the round display always stay in sync with the
        database."""
        if resort:
            self.initiative_database.resort()
        self._sync_selection()
        self.update_round_label()

    def _sync_selection(self):
        """Moves native row selection to match current_creature. This is
        the only thing that changes selection -- not GTK's own
        click-to-select behavior -- so selection always reflects whose
        turn it actually is rather than wherever the user last clicked.
        """
        current = self.initiative_database.current_creature
        if current is None:
            self.selection_model.set_selected(Gtk.INVALID_LIST_POSITION)
            return
        n = self.initiative_database.sorted_model.get_n_items()
        for i in range(n):
            if self.initiative_database.sorted_model.get_item(i) is current:
                self.selection_model.select_item(i, True)
                return

    def update_round_label(self):
        self.round_label.set_label(f"Round {self.initiative_database.round_number}")

    def show_status(self, message):
        self.status_label.set_text(message)

    # -- column factory callbacks ------------------------------------------------

    def _handle_edit_requested(self, creature_obj, field_name, display_name):
        open_edit_dialog(
            self, creature_obj, field_name, display_name, self.after_database_mutation
        )

    def _handle_hitpoints_edit_requested(self, creature_obj):
        open_edit_hitpoints_dialog(self, creature_obj, self.after_database_mutation)

    def _handle_remove_requested(self, creature_obj):
        self.initiative_database.remove_creature(creature_obj)
        self.after_database_mutation(resort=False)

    def _on_row_activated(self, column_view, position):
        """Native Gtk.ColumnView "activate" signal -- fires on
        double-click (single_click_activate is False). Manually sets
        whose turn it is, distinct from Next Turn advancing the order."""
        item = self.selection_model.get_item(position)
        if item is not None:
            self.initiative_database.set_current_creature(item)
            self.after_database_mutation(resort=False)

    # -- toolbar actions ------------------------------------------------

    def on_next_turn_clicked(self, button):
        self.initiative_database.next_turn()
        self.after_database_mutation(resort=False)

    def on_add_creature_clicked(self, button):
        open_add_creature_dialog(self, self._handle_creatures_added)

    def _handle_creatures_added(self, creatures):
        for creature in creatures:
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
        """Export to the last-used path; if none is known yet, this
        behaves the same as Export As."""
        if self.last_file_path:
            self.export_to_path(self.last_file_path)
        else:
            self._open_export_dialog()

    def on_export_as_clicked(self, button):
        """Always prompts for a location, regardless of any remembered
        last_file_path."""
        self._open_export_dialog()

    def _open_export_dialog(self):
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
