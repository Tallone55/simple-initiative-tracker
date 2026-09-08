#!/usr/bin/env bash
# Builds a portable Windows .exe for Simple Initiative Tracker using
# PyInstaller.
#
# ***UNTESTED*** -- written by adapting the verified Linux build
# script (build_linux_portable.sh) to Windows's own conventions, but
# never actually run: no Windows machine was available to build or
# launch this on. Treat the first real run of this script, on real
# Windows hardware, as the actual verification step -- not this
# comment. In particular, the GIRepository-3.0 issue this script
# works around (see below) was diagnosed and fixed on Linux
# specifically; whether MSYS2's own PyGObject build hits the same
# gap, and whether the same fix applies, is not confirmed here.
#
# MUST be run from an MSYS2 MINGW64 shell on Windows.
#
# One-time setup, from an MSYS2 MINGW64 shell:
#     pacman -S --needed mingw-w64-x86_64-gtk4 \
#         mingw-w64-x86_64-python mingw-w64-x86_64-python-gobject \
#         mingw-w64-x86_64-python-cairo mingw-w64-x86_64-adwaita-icon-theme \
#         mingw-w64-x86_64-python-pip
#     python -m pip install pyinstaller
#
# Run from anywhere:
#     ./packaging/build_windows.sh
#
# Output: packaging/dist/<package-name>-<version>-windows-x86_64/
# (a onedir build -- unlike the earlier, hand-rolled Windows script
# this replaced, this doesn't produce a single self-extracting .exe;
# see the note near the bottom of this script about why)
#
# This replaced an earlier, hand-rolled Windows build script that
# compiled its own native launcher.c to start the app. PyInstaller's
# own EXE() step produces a native Windows executable directly, so
# this script doesn't compile or ship a separate native launcher at
# all.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMMON_DIR="$SCRIPT_DIR/common"

source "$COMMON_DIR/app_metadata.sh"
source "$COMMON_DIR/project_metadata.sh"
source "$COMMON_DIR/signing.sh"

if ! command -v python >/dev/null 2>&1; then
    echo "Error: python not found -- run this from an MSYS2 MINGW64 shell with mingw-w64-x86_64-python installed." >&2
    exit 1
fi
if ! python -c "import PyInstaller" >/dev/null 2>&1; then
    echo "Error: PyInstaller not importable -- run 'python -m pip install pyinstaller' first (see this script's own header comment)." >&2
    exit 1
fi
# Same check as the verified Linux script, same reasoning (see header
# comment) -- unconfirmed here whether MSYS2's own PyGObject build
# hits this at all, but if it does, this catches it with a clear
# message rather than the opaque AttributeError PyInstaller itself
# produces without it.
if ! python -c "import gi; gi.require_version('GIRepository', '3.0'); from gi.repository import GIRepository" >/dev/null 2>&1; then
    echo "Error: GIRepository 3.0 typelib not found. If this is the same gap found on Linux (PyGObject >= 3.52 linking against libgirepository-2.0, which has no typelib of its own), look for whatever MSYS2 package provides GIRepository-3.0's introspection data -- unconfirmed here which one that is, or whether it exists at all in MSYS2's repos yet." >&2
    exit 1
fi

BUNDLE_NAME="${PKG_NAME}-${VERSION}-windows-x86_64"
BUILD_DIR="$SCRIPT_DIR/build/windows"
DIST_DIR="$SCRIPT_DIR/dist"
STAGE_DIR="$BUILD_DIR/stage"

rm -rf "$BUILD_DIR"
mkdir -p "$STAGE_DIR/bin" "$DIST_DIR"

# -- stamped app source ---------------------------------------------

cp "$PROJECT_ROOT"/bin/*.py "$STAGE_DIR/bin/"
_stamp_app_metadata "$STAGE_DIR/bin/app_metadata.py"

# -- icon: PyInstaller's EXE() wants a Windows .ico, not the app's own
#    .svg -- ImageMagick or a similar converter would need to be
#    available; left as a manual step here since it's untested either
#    way and this project doesn't otherwise depend on ImageMagick.
#    Uncomment and adapt once verified on real Windows:
#
#    magick "$PROJECT_ROOT/ui/$BUNDLE_ID.svg" -resize 256x256 "$BUILD_DIR/icon.ico"
#
ICO_PATH=""
if [ -f "$BUILD_DIR/icon.ico" ]; then
    ICO_PATH="$BUILD_DIR/icon.ico"
fi

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
    icon="$ICO_PATH",
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

python -m PyInstaller \
    --distpath "$STAGE_DIR" \
    --workpath "$BUILD_DIR/pyinstaller-work" \
    --noconfirm \
    "$SPEC_FILE"

BUNDLE_DIR="$STAGE_DIR/$EXECUTABLE_NAME"
mv "$BUNDLE_DIR" "$BUILD_DIR/$BUNDLE_NAME"

sign_file_authenticode "$BUILD_DIR/$BUNDLE_NAME/$EXECUTABLE_NAME.exe"

# The previous, hand-rolled Windows script packaged its output as a
# single self-extracting .exe via 7-Zip SFX -- not attempted here.
# PyInstaller's own onedir output is a folder, not a single file, and
# turning a folder into a self-extracting archive is a packaging step
# independent of PyInstaller itself; whatever the previous script did
# for that step (see build_windows.sh) could likely be reused as-is
# against this folder instead, once this is confirmed to actually
# work on real Windows. Left as a plain, zipped folder for now.
DIST_ZIP="$DIST_DIR/$BUNDLE_NAME.zip"
(cd "$BUILD_DIR" && zip -qr "$DIST_ZIP" "$BUNDLE_NAME")

echo
echo "Built: $DIST_ZIP"
echo "Run with:   unzip $(basename "$DIST_ZIP") && ${BUNDLE_NAME}/${EXECUTABLE_NAME}.exe"
echo
echo "UNTESTED -- see this script's own header comment. Verify this actually launches before distributing it."
