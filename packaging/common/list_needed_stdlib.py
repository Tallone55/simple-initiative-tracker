#!/usr/bin/env python3
"""Determines exactly which top-level standard-library modules/
packages this app needs, by importing every one of its own source
files and recording what actually lands in sys.modules -- rather than
copying the entire stdlib and manually guessing which parts are safe
to exclude, or the reverse (selectively copying a guessed-at include
list, which is what silently broke the `collections` import before:
a `*.py` glob pattern doesn't match package directories, and nobody
had enumerated the real, complete list by hand).

None of this app's own imports are local/conditional (all are plain
module-level `import`/`from` statements), so importing every one of
its files captures every stdlib module *this app's own code* reaches
for. This is the same technique dependency-tracing packagers like
PyInstaller and cx_Freeze use internally, applied directly rather
than adopting the full tool (which has its own known friction with
PyGObject/GTK4's introspection-based imports).

That guarantee doesn't extend to the stdlib's own internals, though:
a stdlib module can do its own lazy import inside a function body,
triggered only when that specific function is *called*, not when the
module is merely imported -- invisible to this trace unless that
exact call path happens to run during it. Confirmed directly, not
hypothetically: pathlib's own Path.as_uri() does `from urllib.request
import pathname2url` inline, inside the method itself, so `urllib`
never appeared in sys.modules during this trace despite being a real
runtime dependency, and a real portable build shipped without it,
crashing with ModuleNotFoundError the moment cinnamon_theme.py's own
titlebutton-image resolution called .as_uri() on a real path. Since
this class of gap can't be found by tracing alone -- there's no way
to know which stdlib method bodies do their own lazy imports without
either reading their source or hitting the crash -- confirmed-needed
names go in _ALWAYS_INCLUDE below as they're found, each with the
call path that needs it.

Prints one name per line to stdout -- either a bare "<name>.py" file
or a top-level package directory name under the stdlib's own
lib/pythonX.Y directory -- each meant to be copied as-is (Python
packages are directories; this intentionally doesn't try to prune
individual files *within* a needed package, since a package's own
submodules routinely import each other in ways not worth
re-deriving here).

Usage:
    list_needed_stdlib.py BIN_DIR
"""

import importlib
import os
import sys

# Confirmed-needed stdlib top-level names this trace can't discover on
# its own (see the lazy-import limitation in the module docstring
# above), kept alongside whatever call path actually needs each one.
# Discovered by actually calling the triggering code and diffing
# sys.modules before/after on the project's own Python 3.14 (not
# system Python -- confirmed directly that this matters: an earlier
# pass at this used system Python 3.12 and missed `email` entirely,
# since 3.12's import chain here happens to differ from 3.14's).
# Filtered down from the full transitive closure to only the names
# that actually have a stdlib file to copy -- most of what pathlib's
# as_uri() pulls in transitively (_socket, _ssl, math, itertools, and
# a dozen more) are true C built-ins with no separate file, already
# correctly excluded by the file-under-stdlib-dir check below on
# their own; only these five aren't.
_ALWAYS_INCLUDE = {
    # pathlib.Path.as_uri() -- used by cinnamon_theme.py to build
    # file:// URIs for CSS background-image references -- does
    # `from urllib.request import pathname2url` inline inside the
    # method body itself, not at module level. urllib.request in turn
    # does top-level `import email`, `import http.client`, and
    # `import hashlib`; email itself does top-level `import quopri`;
    # ipaddress is pulled in via urllib.parse. Suffixed with ".py"
    # for the three that are single-file modules rather than
    # packages, matching the naming convention the rest of this
    # trace already uses for that distinction -- confirmed necessary
    # directly: getting this wrong for even one of these produced a
    # silent "not found -- skipping" warning in the build log and a
    # real ModuleNotFoundError at runtime, exactly the failure mode
    # this whole allowlist exists to prevent in the first place.
    "urllib", "email", "hashlib.py", "http", "ipaddress.py", "quopri.py",
}


def main():
    # Forces LF-only stdout regardless of platform. Without this,
    # Python's default text-mode stdout on Windows translates \n to
    # \r\n -- and when a bash `while read` loop consumes that output
    # line by line, `read` strips the \n delimiter but leaves the
    # preceding \r attached to the variable, silently corrupting
    # every single name it reads (confirmed directly: a real build
    # log showed a 100% failure rate, every one of 78 traced names
    # failing its own file-existence check, which is exactly what a
    # stray trailing \r on every line produces).
    sys.stdout.reconfigure(newline="\n")

    bin_dir = os.path.abspath(sys.argv[1])
    sys.path.insert(0, bin_dir)

    # Pinned here explicitly, before importing anything: this walks
    # bin/*.py in alphabetical order, and application.py -- which
    # imports Gtk without pinning a version itself, relying on sit.py
    # having already done so -- sorts before sit.py, the file that
    # actually calls gi.require_version(). Without pinning it here
    # too, that produces a real PyGIWarning during this trace
    # (confirmed directly against a real build log), and more
    # importantly risks resolving a different GTK typelib version
    # than the real app would if more than one happens to be
    # installed on the build machine -- silently changing what this
    # trace discovers as needed.
    import gi
    gi.require_version("Gtk", "4.0")

    for filename in sorted(os.listdir(bin_dir)):
        if not filename.endswith(".py"):
            continue
        module_name = filename[:-3]
        try:
            importlib.import_module(module_name)
        except Exception as e:
            print(f"warning: could not import {module_name}: {e}", file=sys.stderr)

    stdlib_dir = os.path.normpath(os.path.dirname(os.__file__))

    needed = set()
    for mod in list(sys.modules.values()):
        file = getattr(mod, "__file__", None)
        if not file:
            continue  # built-in/frozen (e.g. sys itself) -- no file to copy
        file = os.path.normpath(file)
        if file != stdlib_dir and not file.startswith(stdlib_dir + os.sep):
            continue  # not part of the stdlib (our own bin/ files, site-packages, ...)
        rel = os.path.relpath(file, stdlib_dir)
        top = rel.split(os.sep)[0]
        needed.add(top)

    needed |= _ALWAYS_INCLUDE

    for name in sorted(needed):
        print(name)


if __name__ == "__main__":
    main()
