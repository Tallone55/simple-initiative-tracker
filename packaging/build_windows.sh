#!/usr/bin/env bash
# Builds a portable Windows .exe for Simple Initiative Tracker using
# PyInstaller.
#
# Confirmed functional on real Windows hardware: builds cleanly and
# the resulting portable app runs correctly, icon included. Was
# written and initially delivered untested (adapted from the verified
# Linux build script, build_linux_portable.sh, to Windows's own
# conventions), then went through two real, on-hardware fixes before
# reaching this point:
#   - An MSYS2-path-translation bug in the generated .spec file --
#     PyInstaller reported the entry script as not found, traced to
#     POSIX-style paths embedded in generated text never getting
#     MSYS2's usual argv-to-Windows-path conversion (that conversion
#     only applies to live command-line arguments, not to text
#     written into a file a separate process reads back later).
#   - A missing app icon -- the SVG-to-.ico conversion had been left
#     as a commented-out manual step rather than real code, so the
#     .exe carried no icon resource at all and fell back to Windows'
#     generic default.
# Both are fixed in the script as it stands now. The GIRepository-3.0
# issue this script works around (see below) was originally diagnosed
# and fixed on Linux; confirmed separately, on Windows, not to block
# here either.
#
# MUST be run from an MSYS2 MINGW64 shell on Windows.
#
# One-time setup, from an MSYS2 MINGW64 shell:
#     pacman -S --needed mingw-w64-x86_64-gtk4 \
#         mingw-w64-x86_64-python mingw-w64-x86_64-python-gobject \
#         mingw-w64-x86_64-python-cairo mingw-w64-x86_64-adwaita-icon-theme \
#         mingw-w64-x86_64-python-pip mingw-w64-x86_64-librsvg
#     python -m pip install pyinstaller Pillow
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
if ! command -v cygpath >/dev/null 2>&1; then
    echo "Error: cygpath not found -- this script must run from an MSYS2 shell (cygpath ships with the msys2-runtime base package)." >&2
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
#    .svg. Rasterized via rsvg-convert (mingw-w64-x86_64-librsvg --
#    the same tool the macOS script uses via Homebrew's own librsvg)
#    at a single high resolution, then packed into a proper
#    multi-resolution .ico (16/24/32/48/256px, the standard Windows
#    icon size set -- Explorer, the taskbar, and Alt-Tab each prefer a
#    different one of these, so shipping only one size makes some of
#    them look soft or blurry even once an icon shows up at all) via
#    Pillow, which every PyInstaller install already needs anyway.
#    Previously left as a commented-out, never-actually-run manual
#    step -- confirmed directly that this produces exactly the
#    symptom you'd expect from an .exe with no icon resource embedded
#    at all: PyInstaller's own EXE(icon="") writes nothing into the
#    PE's resource section, so Explorer and the taskbar both fall back
#    to Windows' own generic default application icon instead of
#    erroring or warning about it.
ICO_PATH=""
if command -v rsvg-convert >/dev/null 2>&1; then
    RSVG_PNG="$BUILD_DIR/icon-256.png"
    rsvg-convert -w 256 -h 256 "$PROJECT_ROOT/ui/$BUNDLE_ID.svg" -o "$RSVG_PNG"
    # See the "Every path interpolated..." comment further down for
    # why this needs cygpath -m: sys.argv is a live argv element to a
    # spawned native-Windows python.exe (like --distpath/--workpath
    # below), which MSYS2 auto-converts -- BUT this project isn't
    # relying on that auto-conversion working the same way twice in a
    # row without being able to test it, so it's made explicit here
    # too rather than assumed.
    python - "$(cygpath -m "$RSVG_PNG")" "$(cygpath -m "$BUILD_DIR/icon.ico")" << 'PYEOF'
import sys
from PIL import Image
src, dst = sys.argv[1], sys.argv[2]
Image.open(src).save(dst, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (256, 256)])
PYEOF
    ICO_PATH="$BUILD_DIR/icon.ico"
else
    echo "Warning: rsvg-convert not found -- building without an app icon (install mingw-w64-x86_64-librsvg; see this script's own header comment). The .exe and its taskbar icon will fall back to Windows' generic default icon." >&2
fi

# -- PyInstaller spec -------------------------------------------------
#
# Every path interpolated into the .spec file below goes through
# `cygpath -m` first, converting it from MSYS2's own POSIX-style
# representation (e.g. /d/a/simple-initiative-tracker/...) to a real
# Windows path with a drive letter (D:/a/simple-initiative-tracker/...
# -- forward slashes, so it embeds safely in a Python string literal
# without backslash-escaping). This is NOT redundant with MSYS2's
# well-known automatic argv path conversion: that conversion only
# applies to arguments actually passed on a spawned process's command
# line (which is why --distpath/--workpath below don't need this same
# treatment), not to text written into a file that a later, separate
# process reads back -- the .spec file here is generated once by bash
# and then read by PyInstaller's own native-Windows Python, which
# never sees these paths as argv and so never gets the chance to
# translate them. Confirmed directly: without this conversion,
# PyInstaller's own script-not-found error shows the raw, untranslated
# path with a spurious drive letter prepended (Windows treats a
# leading "/" with no drive letter as "root of the current drive",
# reading "d" as a literal folder name rather than as MSYS2's own
# drive-letter marker) -- e.g. D:/d/a/simple-initiative-tracker/... for
# an original /d/a/simple-initiative-tracker/... path.
WIN_STAGE_DIR="$(cygpath -m "$STAGE_DIR")"
WIN_PROJECT_ROOT="$(cygpath -m "$PROJECT_ROOT")"
WIN_ICO_PATH=""
if [ -n "$ICO_PATH" ]; then
    WIN_ICO_PATH="$(cygpath -m "$ICO_PATH")"
fi

SPEC_FILE="$BUILD_DIR/sit.spec"
cat > "$SPEC_FILE" << SPECEOF
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["$WIN_STAGE_DIR/bin/sit.py"],
    pathex=[],
    binaries=[],
    datas=[("$WIN_PROJECT_ROOT/ui", "ui")],
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
    icon="$WIN_ICO_PATH",
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
