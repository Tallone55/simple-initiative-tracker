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

if sys.platform.startswith("linux"):
    # Runs for every Linux launch, not just the frozen portable build
    # (unlike the .desktop-installation block further down, which is
    # portable-only): the .deb-installed path launches via a plain
    # `python3 .../sit.py`, and its own .desktop file's
    # StartupWMClass=net.mystive.sit (see the shared template this and
    # that file both fill in, ui/net.mystive.sit.desktop.in) is only
    # correct if this app's own WM_CLASS is actually "net.mystive.sit"
    # there too -- confirmed directly (via xwininfo) that GTK derives
    # WM_CLASS from the running script/executable's own filename by
    # default, "sit.py" here, not from application_id, so without this
    # call every Linux launch method needs its own fix, not just the
    # frozen one.
    import gi as _gi
    _gi.require_version("GLib", "2.0")
    from gi.repository import GLib as _GLib
    _GLib.set_prgname("net.mystive.sit")

if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
    # Cinnamon (and Linux desktops generally) resolve a running
    # window's taskbar/Alt-Tab icon by matching its WM_CLASS against
    # an *installed* .desktop file's own basename, then using that
    # file's Icon= entry -- confirmed against multiple independent
    # sources, and matching the exact symptom reported: this portable
    # build only ever showed the correct icon when the .deb was also
    # installed, from the exact path the .deb installs it to. A
    # portable, un-installed extraction never has an installed
    # .desktop file of its own, so this doesn't work without one.
    #
    # (Blender's own portable Linux build was checked directly, in its
    # actual C++ source, as a candidate alternative: it sets the
    # taskbar/Alt-Tab icon by writing the X11 _NET_WM_ICON property
    # directly, bypassing .desktop-file matching entirely, using a
    # hardcoded, compiled-in icon. That's genuinely a cleaner fix on
    # X11 specifically -- no persistent file anywhere -- but it has no
    # equivalent on Wayland at all: the xdg-shell protocol gives
    # clients no way to hand the compositor an icon directly, so
    # Wayland is permanently dependent on .desktop-file/app_id
    # matching regardless. Cinnamon's own Wayland session is moving
    # from experimental to fully supported soon (Cinnamon 6.8), so an
    # X11-only fix would trade one platform's problem for stopping to
    # work correctly on the other as that rolls out. This installs a
    # .desktop file instead, specifically because it's the one
    # mechanism that actually covers both.)
    #
    # The template filled in below (ui/net.mystive.sit.desktop.in) is
    # the same one build_deb.sh fills in for the .deb's own .desktop
    # file -- see that script's own comment on this for which fields
    # are shared and which two (Exec=, Icon=) structurally can't be,
    # rather than duplicating that explanation here too.
    #
    # The actual .desktop file this installs isn't written directly
    # into ~/.local/share/applications/ -- it's written into this
    # bundle's own directory (refreshed on every launch, since the
    # correct Exec= path depends on wherever this particular
    # extraction currently lives, which can change), matching how
    # Blender ships its own .desktop file alongside its executable.
    # Only a *symlink* to that file goes into
    # ~/.local/share/applications/, the standard location the desktop
    # shell actually scans. That's what makes cleanup mostly
    # unnecessary to get right perfectly: if this bundle is ever moved
    # or deleted without this app running again to remove the symlink
    # itself, the symlink simply goes dangling, and GIO's own
    # .desktop-file scanning silently skips unreadable entries --
    # rather than continuing to show a fully "valid" file pointing at
    # a dead path, which is what writing a full, separate copy
    # directly into ~/.local/share/applications/ (tried first, then
    # reverted) would have left behind on anything short of a clean
    # exit. The symlink is still removed on normal exit below, as a
    # tidiness improvement on top of that, not as the only thing
    # keeping a dead reference from lingering.
    #
    # Skipped entirely if a system-installed .desktop file for this
    # app already exists (i.e. the .deb is also installed) -- that
    # file already does everything this one would, from a stable,
    # permanent path, so installing a second, competing menu entry
    # here would be redundant at best and confusing at worst.
    _SYSTEM_DESKTOP_FILE = "/usr/share/applications/net.mystive.sit.desktop"
    if not os.path.exists(_SYSTEM_DESKTOP_FILE):
        try:
            _bundle_dir = os.path.dirname(sys.executable)
            _icon_path = os.path.join(_bundle_dir, "share", "icons", "hicolor", "scalable", "apps", "net.mystive.sit.svg")

            _template_path = os.path.join(sys._MEIPASS, "ui", "net.mystive.sit.desktop.in")
            with open(_template_path) as _f:
                _desktop_content = _f.read()
            _desktop_content = (
                _desktop_content
                .replace("@NAME@", "Simple Initiative Tracker")
                .replace("@EXEC@", f"{sys.executable} %f")
                .replace("@ICON@", _icon_path)
            )

            _bundled_desktop_path = os.path.join(_bundle_dir, "net.mystive.sit.desktop")
            with open(_bundled_desktop_path, "w") as _f:
                _f.write(_desktop_content)

            _apps_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "applications")
            os.makedirs(_apps_dir, exist_ok=True)
            _link_path = os.path.join(_apps_dir, "net.mystive.sit.desktop")
            if os.path.lexists(_link_path):
                os.remove(_link_path)
            os.symlink(_bundled_desktop_path, _link_path)

            def _remove_symlink(_path=_link_path):
                try:
                    os.remove(_path)
                except OSError:
                    pass

            import atexit as _atexit
            _atexit.register(_remove_symlink)

            # Python's default SIGTERM handling terminates the process
            # immediately at the OS level, without running atexit
            # callbacks at all -- only normal interpreter shutdown
            # (sys.exit(), or the main script simply returning) does
            # that. sit.py's own __main__ block already converts
            # SIGINT (Ctrl-C) into a normal exit via KeyboardInterrupt,
            # but SIGTERM -- what a process manager, systemd, or a
            # plain `kill <pid>` (no -9) actually sends -- had no such
            # handling, confirmed directly: a bare SIGTERM left the
            # symlink behind, since _remove_symlink above never got a
            # chance to run. This converts SIGTERM into a normal
            # sys.exit() too, so it goes through the same atexit-based
            # cleanup as quitting the app normally, rather than
            # bypassing it.
            import signal as _signal
            _signal.signal(_signal.SIGTERM, lambda *_args: sys.exit(143))
        except OSError:
            pass

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
