#!/usr/bin/env bash
# Builds a portable Windows .exe for Simple Initiative Tracker -- the
# same "run in place" philosophy as the Linux portable build
# (build_linux_portable.sh) and the macOS .app bundle (build_macos.sh):
# a single self-contained folder, everything the app needs bundled
# alongside it, distributed as SimpleInitiativeTracker.exe plus the
# runtime/ folder it depends on.
#
# MUST be run from an MSYS2 MINGW64 shell on Windows (not WSL, not
# Git Bash, not plain MSYS) -- that's the environment PyGObject's own
# Windows documentation recommends, and the only practical source for
# a working GTK4 + PyGObject + GObject-Introspection build on
# Windows: https://pygobject.gnome.org/getting_started.html
#
# One-time setup, from an MSYS2 MINGW64 shell:
#     pacman -S --needed mingw-w64-x86_64-gtk4 mingw-w64-x86_64-libadwaita \
#         mingw-w64-x86_64-python mingw-w64-x86_64-python-gobject \
#         mingw-w64-x86_64-python-cairo mingw-w64-x86_64-adwaita-icon-theme \
#         mingw-w64-x86_64-gcc mingw-w64-x86_64-7zip
#
# Run from anywhere:
#     ./packaging/build_windows.sh
#
# Output: packaging/dist/initiative-tracker-<version>-windows-x86_64.exe
# (a self-extracting archive; falls back to a plain .zip of the same
# folder if 7-Zip isn't installed -- see the archiving step below)
# (scratch work happens in packaging/build/windows/, safe to delete)
#
# Portability boundary: everything the app needs travels in the
# bundle's runtime/ folder (a matching Python interpreter, GTK4, GLib,
# Pango, cairo, HarfBuzz, gdk-pixbuf, and their MSYS2-provided
# dependencies) EXCEPT the small set of core OS/CRT DLLs Windows
# itself services (kernel32, ntdll, user32, the api-ms-win-* virtual
# DLLs, ...) -- see collect_dlls.py's own denylist for the exact set.
#
# Font rendering relies on the host's own installed fonts (via
# DirectWrite/GDI, which MSYS2's GTK4 build uses on Windows) rather
# than bundling a font stack, matching the same choice the Linux
# portable build makes for fontconfig.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMMON_DIR="$SCRIPT_DIR/common"
WIN_DIR="$SCRIPT_DIR/windows"

source "$COMMON_DIR/app_metadata.sh"
source "$COMMON_DIR/version.sh"

if [ "${MSYSTEM:-}" != "MINGW64" ]; then
    echo "Error: this script must be run from an MSYS2 MINGW64 shell (found MSYSTEM='${MSYSTEM:-<unset>}')." >&2
    echo "Open 'MSYS2 MINGW64' from the Start Menu, then re-run this script from there." >&2
    exit 1
fi

MINGW_ROOT="/mingw64"
ARCH="x86_64"
BUNDLE_NAME="${PKG_NAME}-${VERSION}-windows-${ARCH}"

BUILD_DIR="$SCRIPT_DIR/build/windows"
STAGE_DIR="$BUILD_DIR/$BUNDLE_NAME"
DIST_DIR="$SCRIPT_DIR/dist"

echo "Building ${APP_NAME} ${VERSION} (Windows portable, $ARCH)..."

rm -rf "$STAGE_DIR"
mkdir -p \
    "$STAGE_DIR/bin" \
    "$STAGE_DIR/ui" \
    "$STAGE_DIR/runtime/python" \
    "$STAGE_DIR/runtime/lib/girepository-1.0" \
    "$STAGE_DIR/runtime/lib/gdk-pixbuf-2.0/loaders" \
    "$STAGE_DIR/runtime/share/glib-2.0/schemas" \
    "$STAGE_DIR/runtime/share/icons/hicolor/scalable/apps" \
    "$DIST_DIR"

# -- application source ------------------------------------------------

cp "$PROJECT_ROOT"/bin/*.py "$STAGE_DIR/bin/"
cp "$PROJECT_ROOT"/ui/*.ui "$STAGE_DIR/ui/"

# -- portable Python interpreter ------------------------------------------------
# MSYS2's own mingw-w64 Python build (not python.org's -- that one
# can't load MSYS2-built extension modules) is already a real,
# mostly-relocatable install under /mingw64; copied wholesale minus
# its own site-packages, which get replaced by exactly the two
# packages the app needs (gi, cairo) so nothing else MSYS2 happens to
# have installed system-wide leaks into the bundle.

PYTHON_VERSION="$("$MINGW_ROOT/bin/python3" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
SITE_PACKAGES="$MINGW_ROOT/lib/python$PYTHON_VERSION/site-packages"

cp -a "$MINGW_ROOT/bin"/python3*.dll "$STAGE_DIR/runtime/python/" 2>/dev/null || true
cp -a "$MINGW_ROOT/bin/python3.exe" "$MINGW_ROOT/bin/pythonw.exe" "$STAGE_DIR/runtime/python/"
mkdir -p "$STAGE_DIR/runtime/python/lib/python$PYTHON_VERSION/site-packages"
cp -a "$MINGW_ROOT/lib/python$PYTHON_VERSION"/*.py "$MINGW_ROOT/lib/python$PYTHON_VERSION"/*.zip \
    "$STAGE_DIR/runtime/python/lib/python$PYTHON_VERSION/" 2>/dev/null || true
cp -a "$MINGW_ROOT/lib/python$PYTHON_VERSION/encodings" "$STAGE_DIR/runtime/python/lib/python$PYTHON_VERSION/"
cp -a "$MINGW_ROOT/lib/python$PYTHON_VERSION/lib-dynload" "$STAGE_DIR/runtime/python/lib/python$PYTHON_VERSION/" 2>/dev/null || true

for pkg in gi cairo; do
    cp -a "$SITE_PACKAGES/$pkg" "$STAGE_DIR/runtime/python/lib/python$PYTHON_VERSION/site-packages/"
done
for dist_info in "$SITE_PACKAGES"/pygobject-*.dist-info "$SITE_PACKAGES"/pycairo-*.dist-info; do
    [ -d "$dist_info" ] && cp -a "$dist_info" "$STAGE_DIR/runtime/python/lib/python$PYTHON_VERSION/site-packages/"
done

# -- GTK4/GLib/etc. DLL closure ------------------------------------------------

GTK_DLL="$MINGW_ROOT/bin/libgtk-4-1.dll"
ADWAITA_DLL="$MINGW_ROOT/bin/libadwaita-1-0.dll"
GI_EXT="$(find "$SITE_PACKAGES/gi" -maxdepth 1 -name '_gi.cp*-mingw*.pyd' -o -name '_gi.pyd' | head -1)"
GI_CAIRO_EXT="$(find "$SITE_PACKAGES/gi" -maxdepth 1 -name '_gi_cairo*.pyd' | head -1)"
PYCAIRO_EXT="$(find "$SITE_PACKAGES/cairo" -maxdepth 1 -name '_cairo*.pyd' | head -1)"
PIXBUF_QUERY_LOADERS="$MINGW_ROOT/bin/gdk-pixbuf-query-loaders.exe"

if [ ! -f "$GTK_DLL" ]; then
    echo "Error: $GTK_DLL not found -- is mingw-w64-x86_64-gtk4 installed?" >&2
    exit 1
fi

SEEDS=("$GTK_DLL" "$PIXBUF_QUERY_LOADERS")
[ -n "$GI_EXT" ] && SEEDS+=("$GI_EXT")
[ -n "$GI_CAIRO_EXT" ] && SEEDS+=("$GI_CAIRO_EXT")
[ -n "$PYCAIRO_EXT" ] && SEEDS+=("$PYCAIRO_EXT")
[ -f "$ADWAITA_DLL" ] && SEEDS+=("$ADWAITA_DLL")  # sit.py requires Adw 1 alongside Gtk 4

PIXBUF_LOADER_DIR="$(dirname "$(find "$MINGW_ROOT/lib/gdk-pixbuf-2.0" -name 'libpixbufloader-*.dll' | head -1)")"
for loader in "$PIXBUF_LOADER_DIR"/*.dll; do
    SEEDS+=("$loader")
done

python3 "$WIN_DIR/collect_dlls.py" \
    --out "$STAGE_DIR/runtime/lib" \
    --search-path "$MINGW_ROOT/bin" \
    "${SEEDS[@]}"

# Loader DLLs are dlopen()'d plugins, not link-time dependencies of
# anything seeded above, so they're never reached by collect_dlls.py's
# own import-table walk -- copied explicitly here, alongside the query
# tool the launcher uses to regenerate their cache at every run (its
# cache file embeds an absolute path, so it can't be baked in once at
# build time -- same reasoning as the Linux portable build).
cp "$PIXBUF_LOADER_DIR"/*.dll "$STAGE_DIR/runtime/lib/gdk-pixbuf-2.0/loaders/"
cp "$PIXBUF_QUERY_LOADERS" "$STAGE_DIR/runtime/lib/gdk-pixbuf-2.0/"

# -- GObject Introspection typelibs ------------------------------------------------

cp "$MINGW_ROOT/lib/girepository-1.0"/*.typelib "$STAGE_DIR/runtime/lib/girepository-1.0/"

# -- GSettings schemas ------------------------------------------------

cp "$MINGW_ROOT/share/glib-2.0/schemas/gschemas.compiled" "$STAGE_DIR/runtime/share/glib-2.0/schemas/"

# -- icon (optional nicety, not required for the app to run) ------------------------------------------------

cp "$SCRIPT_DIR/debian/$BUNDLE_ID.svg" "$STAGE_DIR/runtime/share/icons/hicolor/scalable/apps/$BUNDLE_ID.svg"

# -- native launcher ------------------------------------------------
# Compiled fresh here rather than checked in as a binary -- see
# windows/launcher.c for why a tiny compiled stub is needed at all
# (env vars GI/GLib read have to be set before bin/sit.py's own
# "import gi" runs, and pythonw.exe alone doesn't know what script to
# launch anyway).

x86_64-w64-mingw32-gcc -municode -mwindows -O2 \
    -o "$STAGE_DIR/${APP_NAME// /}.exe" \
    "$WIN_DIR/launcher.c" -lshlwapi

# -- archive (self-extracting .exe) ------------------------------------------------
# A single double-clickable SimpleInitiativeTracker.exe already exists
# inside $STAGE_DIR, but the *distributable* still needs to carry the
# runtime/ folder alongside it -- wrapped here as a 7-Zip
# self-extracting archive (a genuine, ordinary .exe: the standard 7z
# SFX module concatenated with a small config block and the
# compressed archive) so the download itself is one .exe, matching
# the macOS .app bundle and Linux .tar.gz archive being the single
# artifact for their platforms too. Falls back to a plain .zip if
# 7-Zip isn't installed, since the portable folder is still fully
# usable either way -- just not as one file.

SEVEN_ZIP="$(command -v 7z || command -v 7z.exe || true)"
SFX_MODULE="$(find "$MINGW_ROOT" -iname '7zS2.sfx' -o -iname '7zSD.sfx' -o -iname '7z.sfx' 2>/dev/null | head -1)"

OUTPUT_EXE="$DIST_DIR/${BUNDLE_NAME}.exe"
rm -f "$OUTPUT_EXE"

if [ -n "$SEVEN_ZIP" ] && [ -n "$SFX_MODULE" ]; then
    ARCHIVE_7Z="$BUILD_DIR/${BUNDLE_NAME}.7z"
    rm -f "$ARCHIVE_7Z"
    (cd "$BUILD_DIR" && "$SEVEN_ZIP" a -mx=7 "$ARCHIVE_7Z" "$BUNDLE_NAME" >/dev/null)

    SFX_CONFIG="$BUILD_DIR/sfx_config.txt"
    cat > "$SFX_CONFIG" << SFXCONFIG
;!@Install@!UTF-8!
Title="${APP_NAME}"
BeginPrompt="Extract and run ${APP_NAME} ${VERSION}?"
RunProgram="${BUNDLE_NAME}\\${APP_NAME// /}.exe"
;!@InstallEnd@!
SFXCONFIG

    cat "$SFX_MODULE" "$SFX_CONFIG" "$ARCHIVE_7Z" > "$OUTPUT_EXE"
    chmod 755 "$OUTPUT_EXE"

    echo
    echo "Built: $OUTPUT_EXE"
    echo "Run with:   double-click ${BUNDLE_NAME}.exe -- it extracts itself and launches ${APP_NAME}."
else
    echo "Warning: 7z (with an SFX module) not found -- install mingw-w64-x86_64-7zip for a" >&2
    echo "         single-.exe distributable. Falling back to a .zip of the portable folder." >&2
    ZIP_FILE="$DIST_DIR/${BUNDLE_NAME}.zip"
    (cd "$BUILD_DIR" && rm -f "$ZIP_FILE" && zip -rq "$ZIP_FILE" "$BUNDLE_NAME")

    echo
    echo "Built: $ZIP_FILE"
    echo "Run with:   unzip it, then double-click ${APP_NAME// /}.exe inside ${BUNDLE_NAME}/"
fi
