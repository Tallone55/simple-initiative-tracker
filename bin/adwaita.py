"""Detects whether libadwaita is available, letting application.py use
Adw.Application as its base class when it is (triggering libadwaita's
own native theme integration -- including Linux Mint's patched build
reading real system theme colors natively, see theme_sync.py's module
docstring) and gracefully falling back to plain Gtk.Application when
it isn't.

gi.require_version() raises a plain, catchable ValueError for a
missing namespace (confirmed directly, not assumed -- unlike the
Gio.Settings missing-schema case elsewhere in this codebase, which
hard-aborts the process instead), so a straightforward try/except is
correct and sufficient here.
"""

import gi

try:
    gi.require_version("Adw", "1")
    from gi.repository import Adw
    AVAILABLE = True
except ValueError:
    Adw = None
    AVAILABLE = False
