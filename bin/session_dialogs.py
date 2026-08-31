"""Modal dialog for confirming unsaved changes, built from its .ui
file. A plain function, like the ones in creature_dialogs.py -- takes
the parent window and callbacks rather than needing to know about
AppWindow internals.
"""

from gi.repository import Gtk

from ui_paths import UNSAVED_CHANGES_UI_PATH


def open_unsaved_changes_dialog(parent, on_export, on_discard, message=None):
    """on_export() is called if the user chooses to export first -- the
    caller is responsible for proceeding (closing, importing, etc.)
    afterward once the export actually succeeds. on_discard() is called
    if the user chooses to proceed without exporting. Neither is called
    on Cancel.

    message overrides the default "...before closing?" wording -- this
    dialog is reused for both closing the app and starting an import,
    which have different consequences worth describing accurately.
    """
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
