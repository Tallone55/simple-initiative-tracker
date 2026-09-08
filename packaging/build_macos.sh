#!/usr/bin/env bash
# Builds a self-contained .app bundle for Simple Initiative Tracker
# using PyInstaller.
#
# ***UNTESTED*** -- written by adapting the verified Linux build
# script (build_linux_portable.sh) to macOS's own conventions and
# PyInstaller's own documented BUNDLE() support, but never actually
# run: no macOS machine was available to build or launch this on.
# Treat the first real run of this script, on real macOS hardware, as
# the actual verification step -- not this comment. In particular,
# the GIRepository-3.0 issue this script works around (see below) was
# diagnosed and fixed on Linux specifically; whether Homebrew's own
# PyGObject build hits the same gap, and whether the same fix
# applies, is not confirmed here.
#
# MUST be run on macOS, with Homebrew's own GTK4 already installed.
#
# One-time setup:
#     brew install gtk4 pygobject3 gobject-introspection librsvg
#     uv sync --extra build
#
# Run from anywhere:
#     ./packaging/build_macos.sh
#
# Output: packaging/dist/Simple Initiative Tracker.app
#
# This replaced an earlier, hand-rolled macOS build script that
# generated Info.plist by hand and rewrote dylib rpaths itself.
# PyInstaller's own BUNDLE() step does both of those natively, so
# this script doesn't reimplement either -- see PyInstaller's own
# macOS packaging docs for exactly what BUNDLE() does and doesn't
# cover
# (https://pyinstaller.org/en/stable/spec-files.html#spec-file-options-for-a-macos-bundle).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMMON_DIR="$SCRIPT_DIR/common"

source "$COMMON_DIR/app_metadata.sh"
source "$COMMON_DIR/project_metadata.sh"
source "$COMMON_DIR/signing.sh"

if ! command -v brew >/dev/null 2>&1; then
    echo "Error: Homebrew not found. Install it from https://brew.sh, then:" >&2
    echo "  brew install gtk4 pygobject3 gobject-introspection librsvg" >&2
    exit 1
fi
BREW_PREFIX="$(brew --prefix)"

if ! python3 -c "import PyInstaller" >/dev/null 2>&1; then
    echo "Error: PyInstaller not importable -- run 'uv sync --extra build' first." >&2
    exit 1
fi
# Same check as the verified Linux script, same reasoning (see header
# comment) -- unconfirmed here whether Homebrew's own PyGObject build
# hits this at all, but if it does, this catches it with a clear
# message rather than the opaque AttributeError PyInstaller itself
# produces without it.
if ! python3 -c "import gi; gi.require_version('GIRepository', '3.0'); from gi.repository import GIRepository" >/dev/null 2>&1; then
    echo "Error: GIRepository 3.0 typelib not found. If this is the same gap found on Linux (PyGObject >= 3.52 linking against libgirepository-2.0, which has no typelib of its own), look for whatever Homebrew formula provides GIRepository-3.0's introspection data -- unconfirmed here which one that is." >&2
    exit 1
fi

ARCH="$(uname -m)"
BUILD_DIR="$SCRIPT_DIR/build/macos"
DIST_DIR="$SCRIPT_DIR/dist"
STAGE_DIR="$BUILD_DIR/stage"

rm -rf "$BUILD_DIR"
mkdir -p "$STAGE_DIR/bin" "$DIST_DIR"

# -- stamped app source ---------------------------------------------

cp "$PROJECT_ROOT"/bin/*.py "$STAGE_DIR/bin/"
_stamp_app_metadata "$STAGE_DIR/bin/app_metadata.py"

# -- icon: .icns, converted the same way build_macos.sh already does
#    (unchanged from that script -- this part isn't PyInstaller's
#    concern) -----------------------------------------------------

ICONSET_DIR="$BUILD_DIR/icon.iconset"
mkdir -p "$ICONSET_DIR"
for size in 16 32 128 256 512; do
    rsvg-convert -w "$size" -h "$size" "$PROJECT_ROOT/ui/$BUNDLE_ID.svg" -o "$ICONSET_DIR/icon_${size}x${size}.png"
    double=$((size * 2))
    rsvg-convert -w "$double" -h "$double" "$PROJECT_ROOT/ui/$BUNDLE_ID.svg" -o "$ICONSET_DIR/icon_${size}x${size}@2x.png"
done
ICNS_PATH="$BUILD_DIR/$BUNDLE_ID.icns"
iconutil -c icns "$ICONSET_DIR" -o "$ICNS_PATH"

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
app = BUNDLE(
    coll,
    name="$APP_NAME.app",
    icon="$ICNS_PATH",
    bundle_identifier="$BUNDLE_ID",
    version="$VERSION",
    info_plist={
        "CFBundleShortVersionString": "$VERSION",
        "NSHumanReadableCopyright": "$MAINTAINER",
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "Comma-Separated Values",
                "CFBundleTypeRole": "Editor",
                "LSItemContentTypes": ["public.comma-separated-values-text"],
                "CFBundleTypeExtensions": ["csv"],
                "LSHandlerRank": "Alternate",
            }
        ],
    },
)
SPECEOF

python3 -m PyInstaller \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_DIR/pyinstaller-work" \
    --noconfirm \
    "$SPEC_FILE"

APP_BUNDLE_PATH="$DIST_DIR/$APP_NAME.app"

sign_app_macos "$APP_BUNDLE_PATH"

echo
echo "Built: $APP_BUNDLE_PATH"
echo "Run with:   open \"$APP_BUNDLE_PATH\""
echo
echo "UNTESTED -- see this script's own header comment. Verify this actually launches before distributing it."
