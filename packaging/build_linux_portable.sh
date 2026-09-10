#!/usr/bin/env bash
# Builds a self-contained, "run in place" Linux bundle for Simple
# Initiative Tracker using PyInstaller -- extract the .tar.gz
# anywhere and run the launcher directly, no installation step.
#
# Must be run on a Linux machine with the app's runtime dependencies
# already available (e.g. via `uv sync --extra build`) -- this
# script bundles that working runtime, not build it from scratch.
#
# One-time setup, beyond the project's own `uv sync --extra build`:
#     sudo apt-get install -y gir1.2-girepository-3.0
# PyGObject >= 3.52 switched its own C extension from linking against
# libgirepository-1.0 to libgirepository-2.0, which has no separate,
# introspectable "GIRepository" typelib of its own at all -- its
# functionality is native to the C library. PyInstaller's own GTK4/gi
# hook still needs to introspect *something* named "GIRepository" to
# discover what to collect, and specifically expects one named
# "GIRepository" version "3.0" for this newer architecture (see
# PyInstaller/utils/hooks/gi.py's own "new_api" branch) -- which is
# what gir1.2-girepository-3.0 provides. Confirmed directly: without
# it, the build produces zero .typelib files at all and the app
# crashes on startup with AttributeError: 'gi.repository.GObject'
# object has no attribute 'Property', not a clearer error pointing at
# the missing package.
#
# Run from anywhere:
#     ./packaging/build_linux_portable.sh
#
# Output: packaging/dist/<package-name>-<version>-linux-x86_64.tar.gz
#
# Portability boundary: everything PyInstaller's own GTK4/gi hook
# collects (GTK4, GLib, Pango, cairo, HarfBuzz, gdk-pixbuf, and their
# dependencies, plus a minimal icon/theme/locale subset -- see the
# hooksconfig in the generated .spec) travels in the bundle, EXCEPT
# glibc, the graphics stack, and X11/Wayland client libraries, which
# come from the host. Font rendering relies on the host's own
# fontconfig/installed fonts.
#
# This replaced an earlier, hand-rolled dependency-closure walker
# (manually tracing which shared libraries and stdlib modules the app
# needed, including a runtime-exercise-based tracer for catching
# stdlib lazy imports) that produced a smaller bundle -- roughly 50MB
# vs. this one's roughly 140MB, since PyInstaller's own bootloader
# dlopen()s libpython at runtime rather than being a self-contained
# interpreter binary, and its static bytecode-level dependency
# analysis is deliberately more conservative than runtime-exercise
# tracing would be. Traded that size for not needing a hand-maintained
# exercise harness to stay accurate as the app grows: the earlier
# tracer's own coverage was only as good as what it actually drove
# the app through, silently and without warning whenever a new code
# path went unexercised -- that maintenance burden, not a bug in the
# tracer itself, is what motivated moving off of it in favor of
# PyInstaller's own static analysis, which needs no matching harness.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMMON_DIR="$SCRIPT_DIR/common"

source "$COMMON_DIR/app_metadata.sh"
source "$COMMON_DIR/project_metadata.sh"
source "$COMMON_DIR/signing.sh"

ARCH="$(uname -m)"
BUNDLE_NAME="${PKG_NAME}-${VERSION}-linux-${ARCH}"
BUILD_DIR="$SCRIPT_DIR/build/linux-portable"
DIST_DIR="$SCRIPT_DIR/dist"
STAGE_DIR="$BUILD_DIR/stage"
TARBALL="$DIST_DIR/$BUNDLE_NAME.tar.gz"

rm -rf "$BUILD_DIR"
mkdir -p "$STAGE_DIR/bin" "$DIST_DIR"

if ! command -v uv >/dev/null 2>&1; then
    echo "Error: uv not found -- install it from https://docs.astral.sh/uv/ first." >&2
    exit 1
fi
cd "$PROJECT_ROOT"
# Every Python invocation below goes through `uv run` rather than a
# bare `python3`, specifically so this script works the same way run
# fresh (as its own header instructs -- "run from anywhere") as it
# does with the venv already active: `uv run` always resolves to this
# project's own .venv regardless of what's on PATH or already
# activated in the calling shell, where a bare `python3` would
# silently fall through to the system interpreter -- which has no
# reason to have PyInstaller installed, and, if it happens to have
# its own separate PyGObject, may not exhibit the GIRepository-3.0 gap
# checked for below the same way this project's own does, checking
# gi's own version instead of a straightforwardly missing import.
if ! uv run --extra build python3 -c "import PyInstaller" >/dev/null 2>&1; then
    echo "Error: PyInstaller not importable -- run 'uv sync --extra build' first." >&2
    exit 1
fi
if ! uv run --extra build python3 -c "import gi; gi.require_version('GIRepository', '3.0'); from gi.repository import GIRepository" >/dev/null 2>&1; then
    echo "Error: GIRepository 3.0 typelib not found -- is gir1.2-girepository-3.0 installed? (see this script's own header comment for why this specific package is needed)" >&2
    exit 1
fi

# -- stamped app source ---------------------------------------------

cp "$PROJECT_ROOT"/bin/*.py "$STAGE_DIR/bin/"
_stamp_app_metadata "$STAGE_DIR/bin/app_metadata.py"

# -- PyInstaller spec -------------------------------------------------

SPEC_FILE="$BUILD_DIR/sit.spec"
cat > "$SPEC_FILE" << SPECEOF
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["$STAGE_DIR/bin/sit.py"],
    pathex=[],
    binaries=[],
    datas=[("$PROJECT_ROOT/ui", "ui")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={
        "gi": {
            "module-versions": {
                "Gtk": "4.0",
                "Gdk": "4.0",
            },
            # "hicolor" removed from this list: PyInstaller's own gi
            # hook collects the WHOLE hicolor icon theme tree present
            # on the build machine when this is set -- confirmed
            # directly, on this project's own build machine, that this
            # pulled in every hicolor icon belonging to LibreOffice,
            # ImageMagick, and everything else installed there,
            # entirely unrelated to this app, along with a stale,
            # pre-built icon-theme.cache reflecting that build
            # machine's own icon set, not this bundle's. This app's
            # own icon is handled separately already, via the explicit
            # cp into share/icons/hicolor/ further down this script --
            # nothing here ever needed PyInstaller's own hicolor
            # collection to begin with, only Adwaita, for GTK's own UI
            # chrome (buttons, spinners, and the like). A real,
            # confirmed source of unnecessary bloat and a genuinely
            # confusing bundled artifact either way -- not confirmed
            # to be the cause of a real report of the taskbar icon
            # regressing after the wrapper-script removal below, since
            # direct testing here still resolved the icon correctly
            # even with the stale hicolor cache present, but removed
            # regardless since it was never actually needed.
            "icons": ["Adwaita"],
            "themes": ["Adwaita"],
            "languages": ["en"],
        },
    },
    excludes=[],
    runtime_hooks=[],
    noarchive=False,
    optimize=0,
)

# PyInstaller's own gi.repository.Gio hook (hook-gi.repository.Gio.py)
# unconditionally globs and bundles *every* .so in the build
# machine's gio/modules/ directory -- it has no hooksconfig knob to
# narrow this, since GIO loads these as runtime plugins rather than
# via anything PyInstaller's own import-based analysis could trace.
# Confirmed directly (ldd across the whole collected binary set) that
# three of these -- GIO's TLS backend and its two proxy-resolution
# backends -- pull in an entirely self-contained ~12MB cluster
# (gnutls, openssl's libcrypto, curl, ldap, kerberos, and their own
# transitive deps) that nothing else in this bundle touches, since
# this app has no networking functionality anywhere in its own code
# to exercise Gio's TLS/proxy machinery in the first place. Excluded
# by destination name below, which -- being just a handful of
# specific, individually-verified filenames rather than an inferred
# rule -- stays simple to audit; if this assumption ever stops
# holding (e.g. a future GTK/glib update makes something else start
# needing one of these), the validation pass right after PyInstaller
# runs is what actually catches that, by checking the real, final
# bundle rather than trusting this list to still be correct on faith.
_dead_gio_modules = {
    "gio_modules/libgiognutls.so",
    "gio_modules/libgiolibproxy.so",
    "gio_modules/libgiognomeproxy.so",
}
_dead_transitive_libs = {
    "libgnutls.so.30", "libcrypto.so.3", "libcurl-gnutls.so.4",
    "libldap.so.2", "liblber.so.2", "libproxy.so.1",
    "libpxbackend-1.0.so", "librtmp.so.1", "libp11-kit.so.0",
    "libgssapi_krb5.so.2", "libkrb5.so.3", "libkrb5support.so.0",
    "libk5crypto.so.3", "libkeyutils.so.1", "libnghttp2.so.14",
    "libsasl2.so.2", "libssh.so.4", "libpsl.so.5", "libidn2.so.0",
    "libtasn1.so.6",
}
import os as _os
a.binaries = [
    entry for entry in a.binaries
    if entry[0] not in _dead_gio_modules
    and _os.path.basename(entry[0]) not in _dead_transitive_libs
]

# The "icons": ["Adwaita"] hooksconfig setting above collects
# share/icons/Adwaita/ wholesale -- confirmed directly, in PyInstaller's
# own hook-gi.repository.Gtk.py source, that there's no finer-grained
# knob than "which theme names", not "which subdirectories within a
# theme". Adwaita/cursors/ alone is 11MB of this app's own ~14MB total
# icon payload -- and it's mouse cursor bitmaps (arrow, hand,
# text-select, and so on), which GTK4 apps resolve through the window
# system's own configured cursor theme (X11's XCURSOR_THEME/
# XCURSOR_PATH, or the Wayland compositor's own setting), not through
# an application's own bundled icon theme the way widget/button icons
# are. Nothing in this app -- or in GTK4's own generic widget chrome,
# which does still need the rest of Adwaita for things like window
# controls and checkboxes -- looks up a cursor shape by consulting a
# bundled icons/*/cursors/ directory. Excluded by path prefix below,
# the same way the GIO cluster above is excluded by name: a specific,
# individually-reasoned rule, not a blanket "trim icons" pass, so it
# stays easy to audit if it ever turns out to be wrong.
a.datas = [
    entry for entry in a.datas
    if "icons/Adwaita/cursors/" not in entry[0]
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="$EXECUTABLE_NAME",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="$EXECUTABLE_NAME",
)
SPECEOF

uv run --extra build python3 -m PyInstaller \
    --distpath "$STAGE_DIR" \
    --workpath "$BUILD_DIR/pyinstaller-work" \
    --noconfirm \
    "$SPEC_FILE"

BUNDLE_DIR="$STAGE_DIR/$EXECUTABLE_NAME"

# -- validate the exclusion above is still safe -----------------------
#
# Checks the real, final, built bundle -- not the assumption baked
# into the exclude list above -- for any shared library with a
# dangling reference to something no longer present. This is what
# actually keeps the exclusion above safe over time: if a future GTK,
# glib, or PyInstaller hook update ever makes some other, legitimate
# part of this bundle start needing one of the libraries excluded
# above, this fails the build immediately with the exact missing
# library named, rather than shipping a portable bundle that only
# fails once some user's machine happens to exercise that code path.
if command -v ldd >/dev/null 2>&1; then
    _dangling=""
    for f in "$BUNDLE_DIR/_internal"/*.so* "$BUNDLE_DIR/_internal/gio_modules"/*.so; do
        [ -f "$f" ] || continue
        missing="$(ldd "$f" 2>/dev/null | grep "not found" || true)"
        if [ -n "$missing" ]; then
            _dangling="$_dangling\n$(basename "$f"): $missing"
        fi
    done
    if [ -n "$_dangling" ]; then
        echo "Error: excluding the dead GIO TLS/proxy cluster left a dangling library reference -- something else must now depend on one of the excluded libraries. Re-check packaging/build_linux_portable.sh's own _dead_gio_modules/_dead_transitive_libs lists against this:" >&2
        printf '%b\n' "$_dangling" >&2
        exit 1
    fi
fi

# -- icon (for desktop integration on systems that pick this up from
#    a portable extraction -- matches the icon path convention the
#    .deb build's own desktop file references) ----------------------

mkdir -p "$BUNDLE_DIR/share/icons/hicolor/scalable/apps"
cp "$PROJECT_ROOT/ui/$BUNDLE_ID.svg" "$BUNDLE_DIR/share/icons/hicolor/scalable/apps/"

# No launcher wrapper here, and no XDG_DATA_DIRS-related handling of
# any kind, after several iterations of both that never actually
# addressed the real problem. A wrapper script that set XDG_DATA_DIRS
# was tried, removed for a single-executable bundle with the same fix
# moved into bin/sit.py itself, then reintroduced (with the real
# binary hidden as a dotfile) after a real report that the taskbar
# icon had regressed -- all of which turned out to be chasing the
# wrong layer. The actual cause: Cinnamon (and modern Linux desktops
# generally) resolve a running window's taskbar icon by matching its
# WM_CLASS against an *installed* .desktop file, not by asking the
# app's own process what it thinks its icon is -- confirmed directly
# against the exact symptom reported, that this build only ever showed
# the correct icon when the .deb was also installed, from the exact
# path the .deb installs it to. No amount of correctly setting this
# process's own environment could ever have fixed that, since
# Cinnamon's own panel process never reads it. The real fix -- setting
# a stable window identity via GLib.set_prgname() and installing a
# real .desktop file to ~/.local/share/applications/ on launch -- lives
# in bin/sit.py now, where it belongs: this is about how the app
# presents itself to the desktop shell, not something the build script
# should construct on the app's behalf. See that file's own comment on
# this for the full account, including how it was actually confirmed
# (by directly querying a running window's real WM_CLASS with
# xwininfo, not assumed).

# -- archive ----------------------------------------------------------

mv "$BUNDLE_DIR" "$BUILD_DIR/$BUNDLE_NAME"
tar -C "$BUILD_DIR" -czf "$TARBALL" "$BUNDLE_NAME"
sign_file_gpg "$TARBALL"

echo
echo "Built: $TARBALL"
[ -f "$TARBALL.asc" ] && echo "Signature: $TARBALL.asc (verify with: gpg --verify $TARBALL.asc $TARBALL)"
echo "Run with:   tar xzf $(basename "$TARBALL") && ./${BUNDLE_NAME}/${EXECUTABLE_NAME}"
