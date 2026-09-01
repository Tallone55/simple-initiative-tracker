"""Modal dialog for confirming unsaved changes, built from its .ui
file."""

from gi.repository import Gtk

from ui_paths import UNSAVED_CHANGES_UI_PATH


def open_unsaved_changes_dialog(parent, on_export, on_discard, message=None):
    """on_export() runs if the user chooses to export first -- the
    caller proceeds (closing, importing, etc.) once the export
    actually succeeds. on_discard() runs if the user proceeds without
    exporting. Neither runs on Cancel. message overrides the default
    wording, since this dialog is reused for both closing and
    importing."""
    builder = Gtk.Builder()
    builder.add_from_file(UNSAVED_CHANGES_UI_PATH)

    window = builder.get_object("unsaved_window")
    message_label = builder.get_object("message_label")
    export_button = builder.get_object("export_button")
    discard_button = builder.get_object("discard_button")
    cancel_button = builder.get_object("cancel_button")

    if message is not None:
        message_label.set_text(message)

    window.set_transient_for(parent)

    def handle_export(_button):
        window.destroy()
        on_export()

    def handle_discard(_button):
        window.destroy()
        on_discard()

    def handle_cancel(_button):
        window.destroy()

    export_button.connect("clicked", handle_export)
    discard_button.connect("clicked", handle_discard)
    cancel_button.connect("clicked", handle_cancel)
    window.present()
