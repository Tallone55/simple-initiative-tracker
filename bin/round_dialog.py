"""Modal dialog for manually setting the round counter."""

from gi.repository import Gtk

from ui_paths import EDIT_ROUND_UI_PATH
from expressions import evaluate_int_expression, ExpressionError


def open_edit_round_dialog(parent, current_round, on_committed):
    """on_committed(new_round: int) is called after a successful
    Confirm, once the dialog has already been destroyed."""
    builder = Gtk.Builder()
    builder.add_from_file(EDIT_ROUND_UI_PATH)

    window = builder.get_object("edit_round_window")
    entry = builder.get_object("round_entry")
    error_label = builder.get_object("error_label")
    confirm_button = builder.get_object("confirm_button")
    cancel_button = builder.get_object("cancel_button")

    window.set_transient_for(parent)
    entry.set_text(str(current_round))

    def show_error(message):
        entry.add_css_class("error")
        error_label.set_text(message)
        error_label.set_visible(True)

    def on_confirm(_button):
        entry.remove_css_class("error")
        error_label.set_visible(False)

        try:
            new_round = evaluate_int_expression(entry.get_text())
        except ExpressionError:
            show_error("Round must be a positive whole number or expression.")
            return

        if new_round < 1:
            show_error("Round must be 1 or greater.")
            return

        window.destroy()
        on_committed(new_round)

    def on_cancel(_button):
        window.destroy()

    confirm_button.connect("clicked", on_confirm)
    cancel_button.connect("clicked", on_cancel)
    window.present()
