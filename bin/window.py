from gi.repository import Gio, Gtk

from models import InitiativeDatabase
from creature_dialogs import open_edit_dialog, open_edit_hitpoints_dialog, open_add_creature_dialog
from round_dialog import open_edit_round_dialog
from creature_stats_dialog import open_creature_stats_dialog
from column_factory import CreatureColumnFactory
from undo_manager import UndoManager
from session_manager import SessionManager
from app_menus import build_hamburger_menu
from app_mode import Mode, MODE_LABELS, MODE_TO_INT, mode_from_int
from app_metadata import APP_NAME, VERSION, MAINTAINER, MAINTAINER_EMAIL, REPO_URL
import creature_commands


class AppWindow(Gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_default_size(760, 480)

        self.initiative_database = InitiativeDatabase()
        self.undo_manager = UndoManager()
        self.mode = Mode.SIMPLE
        self.session = SessionManager(
            window=self,
            initiative_database=self.initiative_database,
            undo_manager=self.undo_manager,
            on_state_changed=self._handle_state_changed,
        )

        self._register_actions()

        self.creature_columns = CreatureColumnFactory(
            on_edit_requested=self._handle_edit_requested,
            on_hitpoints_edit_requested=self._handle_hitpoints_edit_requested,
            on_remove_requested=self._handle_remove_requested,
            on_stats_requested=self._handle_stats_requested,
        )

        self.set_titlebar(self._build_headerbar())

        root = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            margin_top=6, margin_bottom=6, margin_start=6, margin_end=6,
        )
        self.set_child(root)

        self.round_button = Gtk.Button(label="Round 1")
        self.round_button.add_css_class("round-counter")
        self.round_button.set_has_frame(False)
        self.round_button.set_halign(Gtk.Align.CENTER)
        self.round_button.set_tooltip_text("Set Round")
        self.round_button.connect("clicked", self.on_edit_round_clicked)
        root.append(self.round_button)
        self.update_round_label()

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

        self.connect("close-request", self.on_close_request)
        self.session.load_cached_file_on_startup()

    # -- construction helpers ------------------------------------------------

    def _register_actions(self):
        new_action = Gio.SimpleAction(name="new")
        new_action.connect("activate", self.on_new)
        self.add_action(new_action)

        import_action = Gio.SimpleAction(name="import")
        import_action.connect("activate", self.on_import)
        self.add_action(import_action)

        export_action = Gio.SimpleAction(name="export")
        export_action.connect("activate", self.on_export)
        self.add_action(export_action)

        export_as_action = Gio.SimpleAction(name="export-as")
        export_as_action.connect("activate", self.on_export_as)
        self.add_action(export_as_action)

        about_action = Gio.SimpleAction(name="about")
        about_action.connect("activate", self.on_about)
        self.add_action(about_action)

    def _build_headerbar(self):
        headerbar = Gtk.HeaderBar()

        add_button = Gtk.Button(label="Add Creature")
        add_button.add_css_class("action-add")
        add_button.set_has_frame(True)
        add_button.connect("clicked", self.on_add_creature_clicked)
        headerbar.pack_start(add_button)

        next_turn_button = Gtk.Button(label="Next Turn")
        next_turn_button.add_css_class("action-next-turn")
        next_turn_button.set_has_frame(True)
        next_turn_button.connect("clicked", self.on_next_turn_clicked)
        headerbar.pack_start(next_turn_button)

        # pack_end() stacks inward from the edge: first call ends up
        # closest to the window controls, so order here (hamburger,
        # separator, mode button) puts the mode button innermost.
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.set_menu_model(build_hamburger_menu())
        menu_button.set_tooltip_text("Menu")
        headerbar.pack_end(menu_button)

        titlebar_separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        titlebar_separator.set_margin_start(6)
        titlebar_separator.set_margin_end(6)
        headerbar.pack_end(titlebar_separator)

        self.mode_button = Gtk.MenuButton()
        self.mode_button.set_label(MODE_LABELS[self.mode])
        self.mode_button.set_tooltip_text("Switch mode")
        self.mode_button.set_popover(self._build_mode_popover())
        headerbar.pack_end(self.mode_button)

        return headerbar

    def _build_mode_popover(self):
        popover = Gtk.Popover()
        list_box = Gtk.ListBox()
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        list_box.add_css_class("boxed-list")

        self._mode_check_icons = {}
        for mode in Mode:
            row = Gtk.ListBoxRow()
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                               margin_top=6, margin_bottom=6, margin_start=10, margin_end=10)
            row_box.append(Gtk.Label(label=MODE_LABELS[mode], xalign=0, hexpand=True))
            check = Gtk.Image.new_from_icon_name("object-select-symbolic")
            check.set_visible(mode is self.mode)
            self._mode_check_icons[mode] = check
            row_box.append(check)
            row.set_child(row_box)
            row.mode = mode
            list_box.append(row)

        def on_row_activated(_list_box, row):
            self._set_mode(row.mode)
            popover.popdown()

        list_box.connect("row-activated", on_row_activated)
        popover.set_child(list_box)
        return popover

    def _set_mode(self, mode):
        if mode is self.mode:
            return
        self.mode = mode
        self.initiative_database.mode = MODE_TO_INT[mode]
        self.mode_button.set_label(MODE_LABELS[mode])
        for candidate_mode, check in self._mode_check_icons.items():
            check.set_visible(candidate_mode is mode)
        self.creature_columns.set_combat_columns_visible(mode is Mode.COMBAT_5E)

    def _handle_state_changed(self, resort):
        self._set_mode(mode_from_int(self.initiative_database.mode))
        self.after_database_mutation(resort=resort, mark_dirty=False)

    # -- shared post-mutation refresh -------------------------------------

    def after_database_mutation(self, resort=False, mark_dirty=True):
        """The single place every mutation routes through afterwards to
        keep sorting, selection, and the round display in sync."""
        if resort:
            self.initiative_database.resort()
        self._sync_selection()
        self.update_round_label()
        if mark_dirty:
            self.session.mark_dirty()

    def _sync_selection(self):
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
        self.round_button.set_label(f"Round {self.initiative_database.round_number}")

    def on_edit_round_clicked(self, button):
        open_edit_round_dialog(self, self.initiative_database.round_number, self._handle_round_committed)

    def _handle_round_committed(self, new_round):
        self.initiative_database.round_number = new_round
        self.update_round_label()
        self.session.mark_dirty()

    def show_status(self, message):
        self.status_label.set_text(message)

    # -- undo / redo ------------------------------------------------

    def perform_undo(self):
        self.undo_manager.undo()
        self.after_database_mutation(resort=True)

    def perform_redo(self):
        self.undo_manager.redo()
        self.after_database_mutation(resort=True)

    # -- column factory callbacks ------------------------------------------------

    def _handle_edit_requested(self, creature_obj, field_name, display_name):
        def on_committed(old_value, new_value, resort):
            creature_commands.edit_field(
                self.undo_manager, creature_obj, field_name, display_name, old_value, new_value
            )
            self.after_database_mutation(resort=resort)

        open_edit_dialog(self, creature_obj, field_name, display_name, on_committed)

    def _handle_hitpoints_edit_requested(self, creature_obj):
        def on_committed(old_hp, old_max, old_temp, new_hp, new_max, new_temp):
            creature_commands.edit_hitpoints(
                self.undo_manager, creature_obj, old_hp, old_max, old_temp, new_hp, new_max, new_temp
            )
            self.after_database_mutation(resort=False)

        open_edit_hitpoints_dialog(self, creature_obj, on_committed)

    def _handle_stats_requested(self, creature_obj):
        old_stats = {field: getattr(creature_obj, field) for field in creature_commands.STATS_FIELDS}

        def on_committed(new_stats):
            for field, value in new_stats.items():
                setattr(creature_obj, field, value)
            creature_commands.edit_stats(self.undo_manager, creature_obj, old_stats, new_stats)
            self.after_database_mutation(resort=False)

        open_creature_stats_dialog(self, old_stats, on_committed)

    def _handle_remove_requested(self, creature_obj):
        resort = creature_commands.remove_creature(
            self.initiative_database, self.undo_manager, creature_obj
        )
        self.after_database_mutation(resort=resort)

    def _on_row_activated(self, column_view, position):
        item = self.selection_model.get_item(position)
        if item is not None:
            self.initiative_database.set_current_creature(item)
            self.after_database_mutation(resort=False)

    # -- headerbar / menu actions ------------------------------------------------

    def on_next_turn_clicked(self, button):
        self.initiative_database.next_turn()
        self.after_database_mutation(resort=False)

    def on_add_creature_clicked(self, button):
        open_add_creature_dialog(self, self.mode, self._handle_creatures_added)

    def _handle_creatures_added(self, creatures):
        resort = creature_commands.add_creatures(self.initiative_database, self.undo_manager, creatures)
        self.after_database_mutation(resort=resort)

    # -- new / import / export / close ------------------------------------------------

    def on_new(self, action, param):
        self.session.try_new()

    def on_import(self, action, param):
        self.session.try_import()

    def on_export(self, action, param):
        self.session.try_export()

    def on_export_as(self, action, param):
        self.session.try_export_as()

    def on_about(self, action, param):
        about = Gtk.AboutDialog(transient_for=self, modal=True)
        about.set_program_name(APP_NAME)
        about.set_version(VERSION)
        about.set_website(REPO_URL)
        about.set_website_label("GitHub Repository")
        about.set_authors([f"{MAINTAINER} <{MAINTAINER_EMAIL}>"])
        about.set_license_type(Gtk.License.MIT_X11)
        about.present()

    def on_close_request(self, window):
        return self.session.try_close()
