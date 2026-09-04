#!/usr/bin/env bash
# Builds a self-contained, "run in place" Linux bundle for Simple
# Initiative Tracker -- extract the .tar.gz anywhere and run the
# launcher directly, no installation step.
#
# Must be run on a Linux machine with the app's runtime dependencies
# already available (e.g. via `uv sync`) -- this script copies that
# working runtime into a portable form, not build it from scratch.
#
# Run from anywhere:
#     ./packaging/build_linux_portable.sh
#
# Output: packaging/dist/initiative-tracker-<version>-linux-x86_64.tar.gz
#
# Portability boundary: everything the app needs travels in
# runtime/ (Python, GTK4, GLib, Pango, cairo, HarfBuzz, gdk-pixbuf,
# and their dependencies) EXCEPT glibc, the graphics stack, and
# X11/Wayland client libraries, which come from the host. Font
# rendering relies on the host's fontconfig/installed fonts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMMON_DIR="$SCRIPT_DIR/common"

source "$COMMON_DIR/app_metadata.sh"
source "$COMMON_DIR/version.sh"

ARCH="$(uname -m)"
BUNDLE_NAME="${PKG_NAME}-${VERSION}-linux-${ARCH}"

BUILD_DIR="$SCRIPT_DIR/build/linux-portable"
STAGE_DIR="$BUILD_DIR/$BUNDLE_NAME"
DIST_DIR="$SCRIPT_DIR/dist"
TARBALL="$DIST_DIR/${BUNDLE_NAME}.tar.gz"

# -- locate the runtime to bundle ------------------------------------------------

PYTHON_INTERPRETER="$(cd "$PROJECT_ROOT" && uv run python -c 'import sys; print(sys.base_prefix)')"
VENV_SITE_PACKAGES="$(cd "$PROJECT_ROOT" && uv run python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
PYTHON_VERSION="$(cd "$PROJECT_ROOT" && uv run python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

if [ ! -d "$PYTHON_INTERPRETER" ]; then
    echo "Error: could not resolve the portable Python interpreter's base_prefix ($PYTHON_INTERPRETER)." >&2
    exit 1
fi

echo "Building ${APP_NAME} ${VERSION} (Linux portable, $ARCH)..."
echo "  Python runtime:  $PYTHON_INTERPRETER"
echo "  site-packages:   $VENV_SITE_PACKAGES"

rm -rf "$STAGE_DIR"
mkdir -p \
    "$STAGE_DIR/bin" \
    "$STAGE_DIR/ui" \
    "$STAGE_DIR/runtime/lib/girepository-1.0" \
    "$STAGE_DIR/runtime/lib/gdk-pixbuf-2.0/loaders" \
    "$STAGE_DIR/runtime/share/glib-2.0/schemas" \
    "$STAGE_DIR/runtime/share/icons/hicolor/scalable/apps" \
    "$DIST_DIR"

# -- application source ------------------------------------------------

cp "$PROJECT_ROOT"/bin/*.py "$STAGE_DIR/bin/"
cp "$PROJECT_ROOT"/ui/*.ui "$STAGE_DIR/ui/"

# -- portable Python interpreter ------------------------------------------------

cp -a "$PYTHON_INTERPRETER" "$STAGE_DIR/runtime/python"
rm -rf "$STAGE_DIR/runtime/python/lib/python$PYTHON_VERSION/site-packages"/*

for pkg in gi cairo; do
    cp -a "$VENV_SITE_PACKAGES/$pkg" "$STAGE_DIR/runtime/python/lib/python$PYTHON_VERSION/site-packages/"
done
for dist_info in "$VENV_SITE_PACKAGES"/pygobject-*.dist-info "$VENV_SITE_PACKAGES"/pycairo-*.dist-info; do
    cp -a "$dist_info" "$STAGE_DIR/runtime/python/lib/python$PYTHON_VERSION/site-packages/"
done

# -- GTK4/GLib/etc. shared library closure ------------------------------------------------

GTK_LIB="$(ldconfig -p | awk '/libgtk-4\.so\.1 /{print $NF; exit}')"
ADWAITA_LIB="$(ldconfig -p | awk '/libadwaita-1\.so\.1 /{print $NF; exit}')"
GI_EXT="$(find "$VENV_SITE_PACKAGES/gi" -maxdepth 1 -name '_gi.cpython*.so' | head -1)"
GI_CAIRO_EXT="$(find "$VENV_SITE_PACKAGES/gi" -maxdepth 1 -name '_gi_cairo.cpython*.so' | head -1)"
PYCAIRO_EXT="$(find "$VENV_SITE_PACKAGES/cairo" -maxdepth 1 -name '_cairo.cpython*.so' | head -1)"
PIXBUF_QUERY_LOADERS="$(command -v gdk-pixbuf-query-loaders || find /usr/lib -name gdk-pixbuf-query-loaders | head -1)"

if [ -z "$GTK_LIB" ]; then
    echo "Error: libgtk-4.so.1 not found via ldconfig -- is GTK4 installed on this build machine?" >&2
    exit 1
fi

SEEDS=("$GTK_LIB" "$GI_EXT" "$GI_CAIRO_EXT" "$PYCAIRO_EXT" "$PIXBUF_QUERY_LOADERS")
[ -n "$ADWAITA_LIB" ] && SEEDS+=("$ADWAITA_LIB")

# gdk-pixbuf loaders are dlopen()'d plugins, not link-time
# dependencies, so their own deps need seeding explicitly too.
GDK_PIXBUF_LOADER_DIR="$(dirname "$(find /usr/lib -name 'libpixbufloader-*.so' | head -1)")"
for loader in "$GDK_PIXBUF_LOADER_DIR"/*.so; do
    SEEDS+=("$loader")
done

python3 "$SCRIPT_DIR/linux/collect_shared_libs.py" --out "$STAGE_DIR/runtime/lib" "${SEEDS[@]}"

cp "$GDK_PIXBUF_LOADER_DIR"/*.so "$STAGE_DIR/runtime/lib/gdk-pixbuf-2.0/loaders/"
cp "$PIXBUF_QUERY_LOADERS" "$STAGE_DIR/runtime/lib/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders"

# -- GObject Introspection typelibs ------------------------------------------------

TYPELIB_DIR="$(dirname "$(find /usr/lib -name 'Gtk-4.0.typelib' | head -1)")"
cp "$TYPELIB_DIR"/*.typelib "$STAGE_DIR/runtime/lib/girepository-1.0/"

# -- GSettings schemas ------------------------------------------------

cp /usr/share/glib-2.0/schemas/gschemas.compiled "$STAGE_DIR/runtime/share/glib-2.0/schemas/"

# -- icon ------------------------------------------------

cp "$SCRIPT_DIR/debian/$BUNDLE_ID.svg" "$STAGE_DIR/runtime/share/icons/hicolor/scalable/apps/$BUNDLE_ID.svg"

# -- launcher ------------------------------------------------

cat > "$STAGE_DIR/$EXECUTABLE_NAME" << 'LAUNCHER'
#!/bin/sh
set -e
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
RUNTIME="$HERE/runtime"

export LD_LIBRARY_PATH="$RUNTIME/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export GI_TYPELIB_PATH="$RUNTIME/lib/girepository-1.0"
export GSETTINGS_SCHEMA_DIR="$RUNTIME/share/glib-2.0/schemas"
export XDG_DATA_DIRS="$RUNTIME/share${XDG_DATA_DIRS:+:$XDG_DATA_DIRS}"

# Regenerated fresh every run since the cache embeds absolute paths.
PIXBUF_CACHE="$RUNTIME/lib/gdk-pixbuf-2.0/loaders.cache.runtime"
"$RUNTIME/lib/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders" "$RUNTIME/lib/gdk-pixbuf-2.0/loaders/"*.so \
    > "$PIXBUF_CACHE" 2>/dev/null || true
export GDK_PIXBUF_MODULE_FILE="$PIXBUF_CACHE"

export PYTHONHOME="$RUNTIME/python"
PYTHON_BIN="$(ls "$RUNTIME/python/bin/python3."* 2>/dev/null | head -1)"
exec "$PYTHON_BIN" "$HERE/bin/sit.py" "$@"
LAUNCHER
chmod 755 "$STAGE_DIR/$EXECUTABLE_NAME"

# -- archive ------------------------------------------------

tar -C "$BUILD_DIR" -czf "$TARBALL" "$BUNDLE_NAME"

echo
echo "Built: $TARBALL"
echo "Run with:   tar xzf $(basename "$TARBALL") && ./${BUNDLE_NAME}/${EXECUTABLE_NAME}"
