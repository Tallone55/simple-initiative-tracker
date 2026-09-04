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
its files is enough to capture the complete stdlib closure: Python
fully executes a module's own import statements the moment it's
imported, whether or not anything in that module is ever actually
called. This is the same technique dependency-tracing packagers like
PyInstaller and cx_Freeze use internally, applied directly rather
than adopting the full tool (which has its own known friction with
PyGObject/GTK4's introspection-based imports).

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


def main():
    bin_dir = os.path.abspath(sys.argv[1])
    sys.path.insert(0, bin_dir)

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

    for name in sorted(needed):
        print(name)


if __name__ == "__main__":
    main()
