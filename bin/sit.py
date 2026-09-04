import os
import sys

# Since Python 3.8, Windows no longer searches PATH (or the current
# directory) when a compiled extension module loads its own DLL
# dependencies -- a deliberate security change (avoiding DLL-hijacking
# via a writable PATH entry), covered in the 3.8 changelog under
# "secure DLL loading". The portable Windows launcher sets PATH to
# include runtime\lib (see packaging/windows/launcher.c) for anything
# that still does consult it, but that alone doesn't reach _gi.pyd's
# own GTK/GLib DLL dependencies -- os.add_dll_directory() is the
# actual replacement mechanism, and it only works called from inside
# Python, before the extension is imported. Guarded to Windows only
# and to when the portable bundle's own runtime/lib actually exists,
# since sit.py is shared by every platform/install method, including
# ones with no such directory at all (the .deb install, the Linux/
# macOS portable bundles, which set LD_LIBRARY_PATH/DYLD_* instead via
# their own shell launchers).
if sys.platform == "win32":
    _runtime_lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "runtime", "lib")
    if os.path.isdir(_runtime_lib):
        os.add_dll_directory(_runtime_lib)

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from application import Application


if __name__ == "__main__":
    app = Application()
    try:
        sys.exit(app.run(sys.argv))
    except KeyboardInterrupt:
        print("Caught KeyboardInterrupt, signal 130")
        sys.exit(130)
