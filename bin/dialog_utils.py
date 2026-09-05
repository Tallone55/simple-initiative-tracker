"""Small helper shared by every modal dialog opener in this app."""

from gi.repository import GLib

_REVEAL_DELAY_MS = 120


def present_settled(window):
    """Presents `window` hidden (opacity 0), then reveals it a short
    moment later, rather than presenting it visibly right away.

    This works around an X11 window-manager race that couldn't be
    fixed by flushing the app's own main loop first (an earlier
    attempt at that): the positioning negotiation happens between GTK
    and the window manager, a separate process, over asynchronous X11
    round-trips the app has no way to force-flush from its own side.
    A window manager that keeps modal dialogs centered on their
    parent (Muffin/Metacity, which Cinnamon uses) can place a freshly
    mapped window using a still-settling size, then re-center it once
    the real size arrives a moment later -- a visible jump. Since
    that negotiation can't be synchronized from here, this instead
    keeps the window invisible (still interactive, just not painted)
    for the short window where that settling happens, so whatever
    repositioning occurs happens off-screen from the person's
    perspective, and only reveals it once it's done.

    Confirmed this really is timing-dependent, not a static sizing
    issue: it doesn't reproduce on the stats editor
    (creature_stats_dialog.py), which spends much longer constructing
    its ~100 widgets before ever calling present() than the small
    .ui-file dialogs take to load and show.
    """
    window.set_opacity(0)
    window.present()

    def reveal():
        window.set_opacity(1)
        return False

    GLib.timeout_add(_REVEAL_DELAY_MS, reveal)

