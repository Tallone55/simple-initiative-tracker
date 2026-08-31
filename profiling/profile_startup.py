#!/usr/bin/env python3
"""Diagnostic script profiling the ENTIRE startup sequence -- including
gi/GTK import and typelib-loading overhead, and Gtk.Application's own
do_startup (display connection, theme/icon/font loading) -- not just
AppWindow construction.

Run this instead of sit.py:

    python profile_startup.py > profile.log

(direct redirection is simpler than piping through `cat` -- not that
`| cat >` was itself the bug here, just one less moving part)

Prints two views once do_activate finishes (right after the window
would normally be constructed and shown), then quits without entering
an interactive session -- the window may flash briefly on screen; that's
expected and harmless for a diagnostic run.

Not part of the shipped app; delete this file once you're done with it.
"""

import cProfile
import pstats
import sys

profiler = cProfile.Profile()
profiler.enable()

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: F401 -- import is the thing being profiled

from application import Application


class ProfilingApplication(Application):
    """A real subclass overriding do_activate in its class body, rather
    than monkeypatching Application.do_activate after the fact.

    GObject virtual-function overrides (do_startup, do_activate, etc.)
    are wired into GTK's C-level dispatch table at class-definition
    time. Reassigning Application.do_activate as a plain attribute after
    the class already exists doesn't update that table -- GTK keeps
    calling the original, unpatched do_activate, which is exactly why
    an earlier version of this script launched the real interactive app
    and printed nothing: the profiling/print/quit code never ran at
    all. Defining the override here, in the normal class body of a
    subclass, lets PyGObject register it correctly.

    Also uses its own distinct application_id rather than inheriting
    the real app's ("net.mystive.sit") -- GApplication enforces
    single-instance via D-Bus by default, so if the real app happened
    to already be running under that ID, launching this script would
    just signal the EXISTING process to activate/raise its window
    rather than ever running our own do_activate in this process at
    all. That's a second, independent explanation for the same "full
    app launches, nothing prints" symptom, so it's worth ruling out too.
    """

    def __init__(self):
        # Bypass Application.__init__ (which hardcodes the real app's
        # ID) and call Gtk.Application.__init__ directly with our own.
        Gtk.Application.__init__(self, application_id="net.mystive.sit.profile")
        self.window = None

    def do_activate(self):
        super().do_activate()
        profiler.disable()

        stats = pstats.Stats(profiler, stream=sys.stdout)

        print("=" * 70)
        print("Top 40 by CUMULATIVE time, from process start through do_activate")
        print("(includes gi import, typelib loading, and Gtk.Application's own")
        print("do_startup -- not just AppWindow construction)")
        print("=" * 70)
        stats.sort_stats("cumulative").print_stats(40)

        print("=" * 70)
        print("Top 40 by TOTAL time (self time, excluding sub-calls)")
        print("=" * 70)
        stats.sort_stats("tottime").print_stats(40)

        # Piped output (as opposed to a terminal) is fully block-buffered
        # by default -- flush explicitly so the log is complete even if
        # something below doesn't exit perfectly cleanly.
        sys.stdout.flush()

        if self.window:
            self.window.destroy()
        self.quit()


if __name__ == "__main__":
    app = ProfilingApplication()
    app.run([])
