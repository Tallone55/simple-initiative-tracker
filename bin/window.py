from gi.repository import Gtk

from models import InitiativeDatabase
from creature_dialogs import open_edit_dialog, open_edit_hitpoints_dialog, open_add_creature_dialog
from column_factory import CreatureColumnFactory
from undo_manager import UndoManager
from session_manager import SessionManager
import creature_commands


class AppWindow(Gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        """Builds the whole UI: toolbar, creature table, status line.
        Creature mutation/undo logic lives in creature_commands.py;
        file/session logic (import/export/close/cache) lives in
        session_manager.py -- this class owns widget construction and
        wires the two together via after_database_mutation."""
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

        self.creature_columns = CreatureColumnFactory(
            on_edit_requested=self._handle_edit_requested,
            on_hitpoints_edit_requested=self._handle_hitpoints_edit_requested,
            on_remove_requested=self._handle_remove_requested,
        )

        root = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            margin_top=6, margin_bottom=6, margin_start=6, margin_end=6,
        )
        self.set_child(root)

        root.append(self._build_toolbar())
        self.update_round_label()

        # Native row selection gives us full-row highlighting for the
        # current turn. Selection is normally driven by our own code
        # (_sync_selection, called after any real state change) rather
        # than raw clicks -- but a single click can still cause a
        # transient native selection on its own (see column_factory.py),
        # which just gets overwritten the next time something actually
        # changes state.
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

    def after_database_mutation(self, resort=False, mark_dirty=True):
        """The single place every mutation (add/remove/edit/next-turn/
        import/undo/redo) routes through afterwards, so sorting, the
        current-turn selection, and the round display always stay in
        sync with the database.

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
        """Refreshes the centered round-counter label to match the
        database's current round_number."""
        self.round_label.set_label(f"Round {self.initiative_database.round_number}")

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
        (covering current and max HP together) is built in
        creature_commands.py."""
        def on_committed(old_hp, old_max, new_hp, new_max):
            creature_commands.edit_hitpoints(
                self.undo_manager, creature_obj, old_hp, old_max, new_hp, new_max
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

    # -- toolbar actions ------------------------------------------------

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

    # -- import / export / close ------------------------------------------------
    #
    # All actual logic lives in SessionManager (session_manager.py) --
    # these are thin entry points matching the buttons/signals that
    # trigger them.

    def on_import_clicked(self, button):
        self.session.try_import()

    def on_export_clicked(self, button):
        self.session.try_export()

    def on_export_as_clicked(self, button):
        self.session.try_export_as()

    def on_close_request(self, window):
        """Gtk.Window's "close-request" signal -- fired by the titlebar
        close button, and by window.close() (which app.quit routes
        through). Returning True blocks the default close so
        SessionManager can ask first; returning False lets it proceed
        immediately."""
        return self.session.try_close()
