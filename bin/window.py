from gi.repository import Gio, Gtk

from models import InitiativeDatabase
from creature_dialogs import open_edit_dialog, open_edit_hitpoints_dialog, open_add_creature_dialog
from round_dialog import open_edit_round_dialog
from column_factory import CreatureColumnFactory
from undo_manager import UndoManager
from session_manager import SessionManager
from app_menus import build_hamburger_menu
import creature_commands


class AppWindow(Gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        """Builds the whole UI: headerbar, creature table, status line.
        Creature mutation/undo logic lives in creature_commands.py;
        file/session logic lives in session_manager.py -- this class
        owns widget construction and wires the two together via
        after_database_mutation."""
        super().__init__(*args, **kwargs)
        self.set_default_size(760, 480)

        self.initiative_database = InitiativeDatabase()
        self.undo_manager = UndoManager()
        self.session = SessionManager(
            window=self,
            initiative_database=self.initiative_database,
            undo_manager=self.undo_manager,
            on_state_changed=lambda resort: self.after_database_mutation(resort=resort, mark_dirty=False),
        )

        self._register_actions()

        self.creature_columns = CreatureColumnFactory(
            on_edit_requested=self._handle_edit_requested,
            on_hitpoints_edit_requested=self._handle_hitpoints_edit_requested,
            on_remove_requested=self._handle_remove_requested,
        )

        self.set_titlebar(self._build_headerbar())

        root = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            margin_top=6, margin_bottom=6, margin_start=6, margin_end=6,
        )
        self.set_child(root)

        # The round counter itself is the edit trigger -- a single
        # button reading "Round N", rather than a separate label plus
        # icon button -- styled flat in styling.py so it still reads
        # as plain centered text at rest.
        self.round_button = Gtk.Button(label="Round 1")
        self.round_button.add_css_class("round-counter")
        self.round_button.set_has_frame(False)
        self.round_button.set_halign(Gtk.Align.CENTER)
        self.round_button.set_tooltip_text("Set Round")
        self.round_button.connect("clicked", self.on_edit_round_clicked)
        root.append(self.round_button)
        self.update_round_label()

        # Native row selection gives full-row highlighting for the
        # current turn, driven by _sync_selection (called after any
        # real state change) rather than raw clicks -- a click can
        # still cause a transient native selection (column_factory.py),
        # overwritten next time state actually changes. Turn activation
        # is via the native "activate" signal, which fires on
        # double-click since single_click_activate is False below.
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

        # Intercept the titlebar close button (and, via Application.quit
        # routing app.quit through window.close(), Ctrl+Q / any "Quit"
        # menu item too) so unsaved changes get a chance to be exported
        # first instead of silently discarded.
        self.connect("close-request", self.on_close_request)

        # Auto-load whatever CSV was last opened/saved, if the cache
        # points at one that still exists. Happens last, after
        # everything above is fully constructed, since it goes through
        # the same import path that touches selection/round-label/etc.
        self.session.load_cached_file_on_startup()

    # -- construction helpers ------------------------------------------------

    def _register_actions(self):
        """Registers the win.* actions the headerbar hamburger menu,
        the traditional File menu (app_menus.py), and keybinds.py's
        Ctrl+N all reference by name."""
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

    def _build_headerbar(self):
        """GNOME-style headerbar: creature/turn actions at the start,
        the round counter centered below (see __init__), and a
        hamburger menu at the end for New/Import/Export/Export As (see
        app_menus.py). Plain Gtk.HeaderBar -- window-control theming is
        handled directly in cinnamon_theme.py rather than by relying on
        Adw.HeaderBar."""
        headerbar = Gtk.HeaderBar()

        add_button = Gtk.Button(label="Add Creature")
        add_button.add_css_class("action-add")
        # Gtk.HeaderBar conventionally renders packed buttons "flat"
        # (no visible fill until hover) by default -- this alone wasn't
        # enough to get the fill to render (styling.py's selectors
        # needed to be scoped more specifically too), but it's still
        # correct to have: it stops the button from requesting "flat"
        # behavior on its own, independent of whatever CSS wins.
        add_button.set_has_frame(True)
        add_button.connect("clicked", self.on_add_creature_clicked)
        headerbar.pack_start(add_button)

        next_turn_button = Gtk.Button(label="Next Turn")
        next_turn_button.add_css_class("action-next-turn")
        next_turn_button.set_has_frame(True)
        next_turn_button.connect("clicked", self.on_next_turn_clicked)
        headerbar.pack_start(next_turn_button)

        # No custom title_widget here -- the headerbar shows its normal
        # title text (SessionManager already manages this via
        # self.set_title(), including the "*" unsaved-changes prefix).
        # The round counter lives in its own row below the headerbar
        # instead (see __init__), since the two headerbar buttons above
        # left no good place for a centered title widget anyway.

        # Packed before menu_button, so it lands between the headerbar's
        # other end-packed content and the hamburger menu -- on the
        # opposite side from the window's own native title-bar controls
        # (minimize/maximize/close), which GtkHeaderBar renders at the
        # true outer edge and aren't pack_end() children themselves.
        titlebar_separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        titlebar_separator.set_margin_start(6)
        titlebar_separator.set_margin_end(6)
        headerbar.pack_end(titlebar_separator)

        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.set_menu_model(build_hamburger_menu())
        menu_button.set_tooltip_text("Menu")
        headerbar.pack_end(menu_button)

        return headerbar

    # -- shared post-mutation refresh -------------------------------------

    def after_database_mutation(self, resort=False, mark_dirty=True):
        """The single place every mutation (add/remove/edit/next-turn/
        turn-activation/new/import/undo/redo) routes through
        afterwards, so sorting, the current-turn selection, and the
        round display always stay in sync with the database.

        mark_dirty=False is used only via SessionManager's
        on_state_changed callback (i.e. only for import), which
        replaces the entire in-memory state with exactly what's on
        disk -- the result is, by definition, already in sync with a
        file, so it shouldn't be flagged as needing export.
        """
        if resort:
            self.initiative_database.resort()
        self._sync_selection()
        self.update_round_label()
        if mark_dirty:
            self.session.mark_dirty()

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
        """Refreshes the round-counter button's label to match the
        database's current round_number."""
        self.round_button.set_label(f"Round {self.initiative_database.round_number}")

    def on_edit_round_clicked(self, button):
        """Opens the Set Round dialog. Not routed through
        creature_commands/undo_manager -- like Next Turn and turn
        activation, manually setting the round is out of scope for
        the undo history."""
        open_edit_round_dialog(self, self.initiative_database.round_number, self._handle_round_committed)

    def _handle_round_committed(self, new_round):
        self.initiative_database.round_number = new_round
        self.update_round_label()
        self.session.mark_dirty()

    def show_status(self, message):
        """Displays a one-line status message below the creature table
        (import/export results, errors, etc.). Called by SessionManager
        too, via its window reference."""
        self.status_label.set_text(message)

    # -- undo / redo ------------------------------------------------

    def perform_undo(self):
        """Entry point for the app.undo action (Ctrl+Z). Commands built
        in creature_commands.py only mutate data, not the UI, so a
        refresh is triggered here unconditionally after every undo."""
        self.undo_manager.undo()
        self.after_database_mutation(resort=True)

    def perform_redo(self):
        """Entry point for the app.redo action (Ctrl+Y / Ctrl+Shift+Z)."""
        self.undo_manager.redo()
        self.after_database_mutation(resort=True)

    # -- column factory callbacks ------------------------------------------------

    def _handle_edit_requested(self, creature_obj, field_name, display_name):
        """Opens the generic text-field edit dialog for one creature
        field; the undo/redo command itself is built in
        creature_commands.py."""
        def on_committed(old_value, new_value, resort):
            creature_commands.edit_field(
                self.undo_manager, creature_obj, field_name, display_name, old_value, new_value
            )
            self.after_database_mutation(resort=resort)

        open_edit_dialog(self, creature_obj, field_name, display_name, on_committed)

    def _handle_hitpoints_edit_requested(self, creature_obj):
        """Opens the dedicated hitpoints dialog; the undo/redo command
        (covering current, max, and temporary HP together) is built in
        creature_commands.py."""
        def on_committed(old_hp, old_max, old_temp, new_hp, new_max, new_temp):
            creature_commands.edit_hitpoints(
                self.undo_manager, creature_obj, old_hp, old_max, old_temp, new_hp, new_max, new_temp
            )
            self.after_database_mutation(resort=False)

        open_edit_hitpoints_dialog(self, creature_obj, on_committed)

    def _handle_remove_requested(self, creature_obj):
        """Removes a creature via creature_commands, which also
        registers the matching undo/redo command."""
        resort = creature_commands.remove_creature(
            self.initiative_database, self.undo_manager, creature_obj
        )
        self.after_database_mutation(resort=resort)

    def _on_row_activated(self, column_view, position):
        """Native Gtk.ColumnView "activate" signal -- fires on
        double-click (single_click_activate is False). Manually sets
        whose turn it is, distinct from Next Turn advancing the order.
        Not undoable -- turn activation is out of scope for the undo
        history."""
        item = self.selection_model.get_item(position)
        if item is not None:
            self.initiative_database.set_current_creature(item)
            self.after_database_mutation(resort=False)

    # -- headerbar / menu actions ------------------------------------------------

    def on_next_turn_clicked(self, button):
        """Advances turn order by one creature (not undoable -- turn
        advancement is out of scope for the undo history)."""
        self.initiative_database.next_turn()
        self.after_database_mutation(resort=False)

    def on_add_creature_clicked(self, button):
        """Opens the Add Creature dialog."""
        open_add_creature_dialog(self, self._handle_creatures_added)

    def _handle_creatures_added(self, creatures):
        """Adds one or more new creatures via creature_commands, which
        also registers the matching undo/redo command (a bulk add
        counts as a single undo step)."""
        resort = creature_commands.add_creatures(self.initiative_database, self.undo_manager, creatures)
        self.after_database_mutation(resort=resort)

    # -- new / import / export / close ------------------------------------------------
    #
    # All actual logic lives in SessionManager (session_manager.py) --
    # these are thin win.* action handlers (activate signal: action,
    # param), matching the hamburger menu, the traditional File menu,
    # and keybinds.py's Ctrl+N.

    def on_new(self, action, param):
        self.session.try_new()

    def on_import(self, action, param):
        self.session.try_import()

    def on_export(self, action, param):
        self.session.try_export()

    def on_export_as(self, action, param):
        self.session.try_export_as()

    def on_close_request(self, window):
        """Gtk.Window's "close-request" signal -- fired by the titlebar
        close button, and by window.close() (which app.quit routes
        through). Returning True blocks the default close so
        SessionManager can ask first; returning False lets it proceed
        immediately."""
        return self.session.try_close()
