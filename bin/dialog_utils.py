"""Small shared helper for wiring keyboard shortcuts onto this app's
modal dialog windows. Every dialog here is a plain Gtk.Window built
from a .ui file (not Gtk.Dialog, which would give Escape/response
handling for free) with its own Cancel button and, on some of them,
an Update/Confirm button -- this is what makes Escape and Enter
behave identically to clicking those buttons, rather than each dialog
wiring its own key handling and risking them drifting out of sync
with each other."""

from gi.repository import Gtk, Gdk


def wire_dialog_shortcuts(window, *, on_escape=None, on_confirm=None, confirm_entries=()):
    """on_escape/on_confirm are called with no arguments when the
    corresponding key is pressed; pass a dialog's own on_cancel/
    on_update handler directly (both are already written to ignore
    the button-click argument they normally receive, via a leading
    underscore, so a no-argument call is safe). Either can be omitted
    for a dialog that has no equivalent action.

    Escape is caught here, at the window level, and that alone is
    enough -- nothing in this app's own entries has a built-in
    binding for it. Enter/Return is different: confirmed directly
    (against GTK's own documented event-propagation behavior) that a
    focused Gtk.Entry's built-in handling for Return -- what drives
    its own "activate" signal -- returns True and stops the keypress
    from ever bubbling up to a window-level controller at all. A
    window-level Enter check alone would silently do nothing for the
    single most common case, typing in a field and pressing Enter, so
    on_confirm is instead wired directly onto each of confirm_entries'
    own "activate" signal -- GTK's own native "Enter was pressed in
    this field" mechanism -- with the window-level check below kept
    only as a fallback for focus landing somewhere that isn't an
    entry (a checkbox, or the window itself)."""
    def on_key_pressed(_controller, keyval, _keycode, state):
        if keyval == Gdk.KEY_Escape and on_escape is not None:
            on_escape()
            return True
        if (
            on_confirm is not None
            and keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter)
        ):
            on_confirm()
            return True
        return False

    key_controller = Gtk.EventControllerKey()
    key_controller.connect("key-pressed", on_key_pressed)
    window.add_controller(key_controller)

    if on_confirm is not None:
        for entry in confirm_entries:
            entry.connect("activate", lambda _entry: on_confirm())
