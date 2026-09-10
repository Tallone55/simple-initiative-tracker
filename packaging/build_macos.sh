#!/usr/bin/env bash
# Builds a self-contained .app bundle for Simple Initiative Tracker
# using PyInstaller. Confirmed working on real macOS hardware.
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
# PyInstaller's own BUNDLE() step generates Info.plist and handles
# dylib/rpath rewriting natively -- see PyInstaller's own macOS
# packaging docs for exactly what it covers
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
# PyGObject >= 3.52 links against libgirepository-2.0, which has no
# typelib of its own -- PyInstaller's own GTK4/gi hook needs one named
# GIRepository 3.0 to discover what to collect (see build_deb.sh's own
# comment on the same gap, diagnosed there first). Confirmed here too.
if ! python3 -c "import gi; gi.require_version('GIRepository', '3.0'); from gi.repository import GIRepository" >/dev/null 2>&1; then
    echo "Error: GIRepository 3.0 typelib not found. Check which Homebrew formula provides it (gobject-introspection should)." >&2
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

# -- icon: .icns, converted from the app's own SVG ------------------

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
            # "hicolor" removed from this list: PyInstaller's own gi
            # hook collects the WHOLE hicolor icon theme tree present
            # on the build machine when this is set -- confirmed
            # directly, on this project's own Linux build machine,
            # that this pulled in every hicolor icon belonging to
            # whatever else happened to be installed there, entirely
            # unrelated to this app, along with a stale, pre-built
            # icon-theme.cache reflecting that build machine's own
            # icon set, not this bundle's. This app's own icon is
            # never resolved through icon-theme lookup at all -- its
            # .desktop-equivalent on this platform (the .app bundle's
            # own icon, set via icon= on BUNDLE() below) uses a direct
            # .icns file, not a name -- so nothing here ever needed
            # PyInstaller's own hicolor collection to begin with, only
            # Adwaita, for GTK's own UI chrome (buttons, spinners, and
            # the like).
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

# Adwaita/cursors/ -- mouse cursor bitmaps (arrow, hand, text-select,
# and so on) -- is excluded the same way, and for the same reason, as
# on the Linux build: confirmed there that this is 11MB of this app's
# ~14MB total icon payload, and that GTK4 apps resolve cursor shapes
# through the window system's own configured cursor theme, not
# through an application's own bundled icon theme. That's even more
# clearly true on macOS specifically, which uses native AppKit cursor
# APIs for this rather than anything X11/Wayland-style at all -- so if
# anything, this app has even less use for a bundled cursor theme here
# than it does on Linux, not less reason to exclude it.
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
