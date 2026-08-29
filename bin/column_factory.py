"""Builds the Gtk.ColumnView columns for creature entries.

Gtk.ColumnView (rather than a hand-built Gtk.ListView row) is what gives
us resizable columns whose header and body cells stay aligned for free --
that alignment/resize behavior is built into the widget, not something we
maintain by hand.

The current-turn highlight is driven by native row selection (a
Gtk.SingleSelection on the ColumnView) rather than a per-cell CSS class:
an earlier per-cell approach had a CSS specificity bug (a later rule
silently overrode the highlight's background-color on most cells) and
never fully solved the "highlight spans the whole row" problem cleanly.
Native selection handles that for free.

Turn activation is via Gtk.ColumnView's own "activate" signal (fires on
double-click by default), connected in AppWindow -- not implemented here
via per-cell gesture n_press detection. That was tried first and doesn't
work reliably: each field's edit dialog is modal and opens instantly on
a single click's release, which swallows the second click of a
double-click before it could ever be recognized as one. Per-cell clicks
here are deliberately left unclaimed (see _build_field_column) so a
click still reaches the row's own native selection handling underneath,
keeping label clicks and background clicks consistent with each other.

Minimum column width: Gtk.ColumnViewColumn has no min-width property.
Interactively dragging a column below its content's natural size doesn't
reduce the real layout allocation given to header or body content at
all, so overflow-hiding/ellipsizing never gets a smaller allocation to
act on in that specific scenario -- the fix there is intercepting the
column's own fixed-width and clamping it back up (_enforce_min_width).

Ellipsizing long content: a *different* scenario from the above, and one
where ellipsizing genuinely works -- a column with an explicit starting
fixed-width (not just a floor) that happens to be smaller than an
unusually long value (a long creature name, or a large number from a
dice-expression edit). Since Gtk.ColumnViewColumn auto-grows to fit
content when fixed-width is unset, each column is given an explicit
starting fixed-width equal to its floor, so long content has an actual
fixed budget to overflow against instead of just growing the column.
"""

from gi.repository import Gtk, Pango


class CreatureColumnFactory:
    def __init__(
        self,
        on_edit_requested,
        on_hitpoints_edit_requested,
        on_remove_requested,
    ):
        """
        on_edit_requested(creature_obj, field_name, display_name) -- called
            on a click on the Creature / Armor Class / Initiative Roll cell.
        on_hitpoints_edit_requested(creature_obj) -- called on a click on
            the Hitpoints cell (routed separately since it opens a
            dedicated current/max HP dialog rather than the generic
            text-field editor).
        on_remove_requested(creature_obj) -- called when a row's remove
            button is clicked.

        Turn activation (double-click) is handled separately, at the
        Gtk.ColumnView level in AppWindow -- not here. See the module
        docstring for why.
        """
        self.on_edit_requested = on_edit_requested
        self.on_hitpoints_edit_requested = on_hitpoints_edit_requested
        self.on_remove_requested = on_remove_requested

        self.columns = [
            self._build_field_column(
                title="Creature",
                getter=lambda c: c.name,
                notify_props=["name"],
                on_click=lambda c: self.on_edit_requested(c, "name", "Creature"),
                expand=True,
                min_width=140,
            ),
            self._build_field_column(
                title="Hitpoints",
                getter=self._format_hitpoints,
                notify_props=["hitpoints", "max-hitpoints"],
                on_click=lambda c: self.on_hitpoints_edit_requested(c),
                min_width=90,
            ),
            self._build_field_column(
                title="Armor Class",
                getter=lambda c: str(c.armor_class),
                notify_props=["armor-class"],
                on_click=lambda c: self.on_edit_requested(c, "armor_class", "Armor Class"),
                min_width=110,
            ),
            self._build_field_column(
                title="Initiative Roll",
                getter=lambda c: str(c.initiative_roll),
                notify_props=["initiative-roll"],
                on_click=lambda c: self.on_edit_requested(c, "initiative_roll", "Initiative Roll"),
                min_width=120,
            ),
            self._build_remove_column(min_width=48),
        ]

    @staticmethod
    def _format_hitpoints(creature_obj):
        return f"{creature_obj.hitpoints}/{creature_obj.max_hitpoints}"

    # -- generic text-cell column ------------------------------------------------

    def _build_field_column(self, title, getter, notify_props, on_click, expand=False, min_width=80):
        factory = Gtk.SignalListItemFactory()

        def on_setup(factory, list_item):
            label = Gtk.Label(label="", xalign=0, hexpand=True)
            label.add_css_class("editable-cell")
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_overflow(Gtk.Overflow.HIDDEN)
            label.set_cursor_from_name("pointer")
            # Gtk.ColumnViewColumn has no min-width property of its own --
            # a resizable column's floor is derived from its cells' actual
            # size requests, so this is what stops the column from being
            # dragged down to (or below) zero and overlapping its neighbors.
            label.set_size_request(min_width, -1)

            click_gesture = Gtk.GestureClick()
            click_gesture.set_button(1)  # left click only
            label.add_controller(click_gesture)

            list_item.set_child(label)
            list_item.notify_handler_ids = []
            list_item.click_gesture = click_gesture
            list_item.click_handler_id = None

        def on_bind(factory, list_item):
            creature_obj = list_item.get_item()
            label = list_item.get_child()

            def refresh(*_args):
                label.set_label(getter(creature_obj))
            refresh()

            list_item.notify_handler_ids = [
                creature_obj.connect(f"notify::{prop}", refresh) for prop in notify_props
            ]

            def handle_click(gesture, n_press, x, y):
                # Every click here always opens the edit dialog,
                # regardless of n_press -- distinguishing single vs.
                # double click here doesn't work reliably, since the
                # edit dialog is modal and pops up instantly on the
                # first click's release, which swallows the second click
                # before a double-click could ever be recognized. Turn
                # activation is handled separately, at the ColumnView
                # level, via double-clicks landing outside these cells.
                on_click(creature_obj)
                # Deliberately NOT claiming this gesture's state: letting
                # the click also reach the row's own native selection
                # handling means a click here causes the same transient
                # visual selection that clicking row background does,
                # rather than labels behaving differently from
                # everything else. It's only ever "transient" because
                # _sync_selection() re-asserts the real current turn
                # after any actual state change.

            list_item.click_handler_id = list_item.click_gesture.connect(
                "released", handle_click
            )

        def on_unbind(factory, list_item):
            creature_obj = list_item.get_item()
            for hid in list_item.notify_handler_ids:
                creature_obj.disconnect(hid)
            list_item.notify_handler_ids = []

            if list_item.click_handler_id is not None:
                list_item.click_gesture.disconnect(list_item.click_handler_id)
                list_item.click_handler_id = None

        factory.connect("setup", on_setup)
        factory.connect("bind", on_bind)
        factory.connect("unbind", on_unbind)

        column = Gtk.ColumnViewColumn(title=title, factory=factory)
        column.set_resizable(True)
        column.set_expand(expand)
        # Without an explicit starting fixed-width, the column auto-grows
        # to fit its content's natural size -- so an unusually long value
        # would just widen the column rather than ever get ellipsized.
        # Giving it a real starting width (rather than leaving it at -1
        # / auto) means long content actually has a fixed budget to
        # overflow against.
        column.set_fixed_width(min_width)
        self._enforce_min_width(column, min_width)
        return column

    @staticmethod
    def _enforce_min_width(column, min_width):
        """Gtk.ColumnViewColumn has no min-width property -- resizable
        columns just have their fixed-width set directly to the drag
        position, with no clamping against content size. So instead we
        watch fixed-width itself and snap it back up if a drag pushes it
        below our floor. -1 means "unset / natural sizing", which we
        leave alone.
        """
        def on_notify_fixed_width(col, _pspec):
            width = col.get_fixed_width()
            if width != -1 and width < min_width:
                col.set_fixed_width(min_width)

        column.connect("notify::fixed-width", on_notify_fixed_width)

    # -- remove (trash-can icon) column ------------------------------------------------

    def _build_remove_column(self, min_width=48):
        factory = Gtk.SignalListItemFactory()

        def on_setup(factory, list_item):
            button = Gtk.Button.new_from_icon_name("user-trash-symbolic")
            button.set_tooltip_text("Remove")
            button.add_css_class("flat")
            button.set_overflow(Gtk.Overflow.HIDDEN)
            button.set_size_request(min_width, -1)
            list_item.set_child(button)
            list_item.click_handler_id = None

        def on_bind(factory, list_item):
            creature_obj = list_item.get_item()
            button = list_item.get_child()
            list_item.click_handler_id = button.connect(
                "clicked", lambda b: self.on_remove_requested(creature_obj)
            )

        def on_unbind(factory, list_item):
            button = list_item.get_child()
            if list_item.click_handler_id is not None:
                button.disconnect(list_item.click_handler_id)
                list_item.click_handler_id = None

        factory.connect("setup", on_setup)
        factory.connect("bind", on_bind)
        factory.connect("unbind", on_unbind)

        column = Gtk.ColumnViewColumn(title="", factory=factory)
        column.set_resizable(False)
        column.set_fixed_width(min_width)
        return column
