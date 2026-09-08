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
            "icons": ["Adwaita", "hicolor"],
            "themes": ["Adwaita"],
            "languages": ["en"],
        },
    },
    excludes=[],
    runtime_hooks=[],
    noarchive=False,
    optimize=0,
)
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
    upx=False,
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
    upx=False,
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

# -- icon (for desktop integration on systems that pick this up from
#    a portable extraction -- matches the icon path convention the
#    .deb build's own desktop file references) ----------------------

mkdir -p "$BUNDLE_DIR/share/icons/hicolor/scalable/apps"
cp "$PROJECT_ROOT/ui/$BUNDLE_ID.svg" "$BUNDLE_DIR/share/icons/hicolor/scalable/apps/"

# -- archive ----------------------------------------------------------

mv "$BUNDLE_DIR" "$BUILD_DIR/$BUNDLE_NAME"
tar -C "$BUILD_DIR" -czf "$TARBALL" "$BUNDLE_NAME"
sign_file_gpg "$TARBALL"

echo
echo "Built: $TARBALL"
[ -f "$TARBALL.asc" ] && echo "Signature: $TARBALL.asc (verify with: gpg --verify $TARBALL.asc $TARBALL)"
echo "Run with:   tar xzf $(basename "$TARBALL") && ./${BUNDLE_NAME}/${EXECUTABLE_NAME}"
