import os
import sys

if getattr(sys, "frozen", False) and sys.platform == "win32":
    # Modern GTK renders text via Cairo using PangoFT2 (FreeType), not
    # the legacy PangoWin32/GDI backend, and FreeType text shaping is
    # itself driven by fontconfig -- which needs its own config file
    # (fonts.conf) to know where to look for fonts at all, including
    # Windows' own system font directory. build_windows.sh collects
    # that config into this bundle (see its own comment on this, right
    # where it's collected) specifically because PyInstaller's GTK4/gi
    # hook has no built-in awareness that fontconfig needs it, the
    # same way it has no built-in awareness of GIO's modules directory
    # elsewhere in this same file. Set as early as possible, before
    # anything GTK/Pango-related initializes fontconfig's own global
    # state.
    #
    # Uses sys._MEIPASS here, not sys.executable's own directory the
    # way the Linux XDG_DATA_DIRS block below does -- a real,
    # deliberate difference, not an inconsistency: this data was
    # collected via PyInstaller's own `datas` list in the .spec file,
    # which places things under _MEIPASS (_internal/ for a onedir
    # build), whereas the Linux share/ directory below is copied in by
    # build_linux_portable.sh itself, after PyInstaller runs, directly
    # into the bundle root alongside the executable -- confirmed
    # directly, earlier in this project, that _MEIPASS and
    # sys.executable's own directory are NOT the same location for a
    # onedir build, which is exactly why this distinction matters here
    # rather than being interchangeable.
    _fontconfig_dir = os.path.join(sys._MEIPASS, "fontconfig")
    if os.path.isdir(_fontconfig_dir):
        os.environ["FONTCONFIG_PATH"] = _fontconfig_dir

if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
    # GTK4 removed the old GTK3 per-window icon-setting APIs
    # (gtk_window_set_icon_name()/set_icon()) entirely -- a GTK4 app's
    # own window/taskbar icon comes only from icon-theme lookup
    # against its own application ID, and that lookup only searches
    # $XDG_DATA_DIRS. This bundle carries its own copy of the app icon
    # under share/icons/hicolor/..., alongside this executable itself
    # (sys.executable, when frozen, points at this same file -- taken
    # from the running binary's own path rather than
    # sys._MEIPASS, which points one level too deep, at _internal/,
    # confirmed directly rather than assumed). Extracted anywhere,
    # that share/ directory is never on the default XDG_DATA_DIRS
    # search path on its own, so without this, the icon lookup misses
    # silently and the desktop falls back to its own generic default
    # icon -- confirmed directly as the exact cause of a real "wrong
    # icon in the taskbar and file manager" report. Set here, in the
    # app's own entry point, rather than via a separate wrapper shell
    # script this package used to ship alongside the real compiled
    # binary -- the two-file split answered its own question ("which
    # one do I actually run?") worse than just having the one real
    # executable handle this itself.
    _bundle_dir = os.path.dirname(sys.executable)
    _bundle_share = os.path.join(_bundle_dir, "share")
    if os.path.isdir(_bundle_share):
        os.environ["XDG_DATA_DIRS"] = _bundle_share + ":" + os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share")

import gi

gi.require_version("Gtk", "4.0")

from application import Application


if __name__ == "__main__":
    app = Application()
    try:
        sys.exit(app.run(sys.argv))
    except KeyboardInterrupt:
        print("Caught KeyboardInterrupt, signal 130")
        sys.exit(130)
