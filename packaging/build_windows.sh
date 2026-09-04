#!/usr/bin/env bash
# Builds a portable Windows .exe for Simple Initiative Tracker.
#
# MUST be run from an MSYS2 MINGW64 shell on Windows.
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
# Output: packaging/dist/<package-name>-<version>-windows-x86_64.exe
# (a self-extracting archive; falls back to a plain .zip if 7-Zip
# isn't installed)
#
# Portability boundary: everything the app needs travels in
# runtime/ (Python, GTK4, GLib, Pango, cairo, HarfBuzz, gdk-pixbuf,
# and their MSYS2-provided dependencies) EXCEPT the core Windows
# OS/CRT DLLs -- see collect_dlls.py's denylist. Font rendering
# relies on the host's own installed fonts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMMON_DIR="$SCRIPT_DIR/common"
WIN_DIR="$SCRIPT_DIR/windows"

source "$COMMON_DIR/app_metadata.sh"
source "$COMMON_DIR/project_metadata.sh"

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
GI_EXT="$(find "$SITE_PACKAGES/gi" -maxdepth 1 -name '_gi*.pyd' ! -name '_gi_cairo*' | head -1)"
GI_CAIRO_EXT="$(find "$SITE_PACKAGES/gi" -maxdepth 1 -name '_gi_cairo*.pyd' | head -1)"
PYCAIRO_EXT="$(find "$SITE_PACKAGES/cairo" -maxdepth 1 -name '_cairo*.pyd' | head -1)"
PIXBUF_QUERY_LOADERS="$MINGW_ROOT/bin/gdk-pixbuf-query-loaders.exe"

if [ ! -f "$GTK_DLL" ]; then
    echo "Error: $GTK_DLL not found -- is mingw-w64-x86_64-gtk4 installed?" >&2
    exit 1
fi

SEEDS=("$GTK_DLL" "$PIXBUF_QUERY_LOADERS")
if [ -n "$GI_EXT" ]; then
    SEEDS+=("$GI_EXT")
else
    echo "Warning: PyGObject's _gi extension module wasn't found -- the built app likely can't import gi at runtime." >&2
fi
[ -n "$GI_CAIRO_EXT" ] && SEEDS+=("$GI_CAIRO_EXT")
[ -n "$PYCAIRO_EXT" ] && SEEDS+=("$PYCAIRO_EXT")
[ -f "$ADWAITA_DLL" ] && SEEDS+=("$ADWAITA_DLL")

PIXBUF_LOADER="$(find "$MINGW_ROOT/lib/gdk-pixbuf-2.0" -name 'libpixbufloader-*.dll' 2>/dev/null | head -1)"
if [ -z "$PIXBUF_LOADER" ]; then
    echo "Error: no gdk-pixbuf loader DLLs found under $MINGW_ROOT/lib/gdk-pixbuf-2.0 -- is mingw-w64-x86_64-gdk-pixbuf2 installed?" >&2
    exit 1
fi
PIXBUF_LOADER_DIR="$(dirname "$PIXBUF_LOADER")"
for loader in "$PIXBUF_LOADER_DIR"/*.dll; do
    SEEDS+=("$loader")
done

python3 "$WIN_DIR/collect_dlls.py" \
    --out "$STAGE_DIR/runtime/lib" \
    --search-path "$MINGW_ROOT/bin" \
    "${SEEDS[@]}"

cp "$PIXBUF_LOADER_DIR"/*.dll "$STAGE_DIR/runtime/lib/gdk-pixbuf-2.0/loaders/"
cp "$PIXBUF_QUERY_LOADERS" "$STAGE_DIR/runtime/lib/gdk-pixbuf-2.0/"

# -- GObject Introspection typelibs ------------------------------------------------

cp "$MINGW_ROOT/lib/girepository-1.0"/*.typelib "$STAGE_DIR/runtime/lib/girepository-1.0/"

# -- GSettings schemas ------------------------------------------------

cp "$MINGW_ROOT/share/glib-2.0/schemas/gschemas.compiled" "$STAGE_DIR/runtime/share/glib-2.0/schemas/"

# -- icon ------------------------------------------------

cp "$SCRIPT_DIR/$BUNDLE_ID.svg" "$STAGE_DIR/runtime/share/icons/hicolor/scalable/apps/$BUNDLE_ID.svg"

# -- native launcher ------------------------------------------------

x86_64-w64-mingw32-gcc -municode -mwindows -O2 \
    -o "$STAGE_DIR/${APP_NAME// /}.exe" \
    "$WIN_DIR/launcher.c" -lshlwapi

# -- archive (self-extracting .exe) ------------------------------------------------

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
