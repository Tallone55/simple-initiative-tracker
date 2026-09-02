#!/usr/bin/env bash
# Builds a self-contained, "run in place" Linux bundle for Simple
# Initiative Tracker -- the same distribution style as Blender's own
# portable Linux download: extract the .tar.gz anywhere and run the
# launcher directly, no installation step.
#
# Must be run on a Linux machine with the app's own runtime
# dependencies already available (a working dev environment -- see
# the project's pyproject.toml/uv.lock -- with GTK4, GObject
# Introspection, and PyGObject/pycairo already built against them,
# e.g. via `uv sync`), since this script's job is to COPY that
# already-working runtime into a portable form, not build it from
# scratch. Run from anywhere:
#
#     ./packaging/build_linux_portable.sh
#
# Output: packaging/dist/initiative-tracker-<version>-linux-x86_64.tar.gz
# (scratch work happens in packaging/build/linux-portable/, safe to delete)
#
# Portability boundary: everything the app needs travels in the
# bundle's runtime/ folder (a matching Python interpreter, GTK4,
# GLib, Pango, cairo, HarfBuzz, gdk-pixbuf, and their dependencies)
# EXCEPT glibc itself, the graphics stack (OpenGL/EGL/Vulkan/DRM), and
# X11/Wayland client libraries -- those must come from the host, the
# same boundary AppImage/linuxdeploy-built bundles and Blender's own
# portable Linux build both draw, since bundling a mismatched GPU
# driver or display-protocol library is far more likely to break
# rendering than help. See collect_shared_libs.py's own docstring for
# the exact denylist.
#
# Font rendering also relies on the host's own fontconfig
# configuration and installed fonts (/etc/fonts) rather than bundling
# a font stack -- again matching Blender's own portable Linux build.

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
# Reuses whatever interpreter + PyGObject/pycairo build the project's
# own uv-managed .venv already has -- see the project's uv.lock -- so
# this script never needs its own separate build step for those.

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
# python-build-standalone's own tree (bin/, lib/, include/, share/) is
# already relocatable by design -- copied wholesale, then PyGObject/
# pycairo (built against the system's GTK4 dev headers -- there's no
# such thing as a portable prebuilt PyGObject wheel, since it's a
# thin binding over the system's own GObject Introspection) are
# layered in from the project's own .venv on top.

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
[ -n "$ADWAITA_LIB" ] && SEEDS+=("$ADWAITA_LIB")  # sit.py requires Adw 1 alongside Gtk 4

# gdk-pixbuf's individual format loaders (PNG, JPEG, etc.) are
# dlopen()'d plugins, not link-time dependencies of anything else
# seeded above, so their own dependencies (libpng, libjpeg, libtiff,
# ...) need to be seeded explicitly too, rather than relying on some
# other seed happening to pull the same libraries in already.
GDK_PIXBUF_LOADER_DIR="$(dirname "$(find /usr/lib -name 'libpixbufloader-*.so' | head -1)")"
for loader in "$GDK_PIXBUF_LOADER_DIR"/*.so; do
    SEEDS+=("$loader")
done

python3 "$SCRIPT_DIR/linux/collect_shared_libs.py" --out "$STAGE_DIR/runtime/lib" "${SEEDS[@]}"

# The loader .so files are themselves plugins, so collect_shared_libs.py
# (which only follows link-time dependency edges) never copies the
# loaders themselves, only what they in turn depend on -- copied
# explicitly here, along with the query tool used to (re)generate
# their cache file in the launcher script at every run, since the
# cache embeds each loader's absolute path and the bundle must keep
# working if it's extracted somewhere else later.
cp "$GDK_PIXBUF_LOADER_DIR"/*.so "$STAGE_DIR/runtime/lib/gdk-pixbuf-2.0/loaders/"
cp "$PIXBUF_QUERY_LOADERS" "$STAGE_DIR/runtime/lib/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders"

# -- GObject Introspection typelibs ------------------------------------------------

TYPELIB_DIR="$(dirname "$(find /usr/lib -name 'Gtk-4.0.typelib' | head -1)")"
cp "$TYPELIB_DIR"/*.typelib "$STAGE_DIR/runtime/lib/girepository-1.0/"

# -- GSettings schemas ------------------------------------------------
# The compiled cache doesn't embed absolute paths (unlike gdk-pixbuf's
# loaders.cache above), so a plain copy is safe -- GSETTINGS_SCHEMA_DIR
# just needs to point at whatever directory holds it, at any location.

cp /usr/share/glib-2.0/schemas/gschemas.compiled "$STAGE_DIR/runtime/share/glib-2.0/schemas/"

# -- icon (optional nicety, not required for the app to run) ------------------------------------------------

cp "$SCRIPT_DIR/debian/$BUNDLE_ID.svg" "$STAGE_DIR/runtime/share/icons/hicolor/scalable/apps/$BUNDLE_ID.svg"

# -- launcher ------------------------------------------------

cat > "$STAGE_DIR/$EXECUTABLE_NAME" << 'LAUNCHER'
#!/bin/sh
# Simple Initiative Tracker -- portable launcher. Safe to run in
# place from any location (a USB drive, an extracted download,
# anywhere) -- everything this app needs beyond glibc, the graphics
# stack, and X11/Wayland travels alongside it in runtime/.
set -e
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
RUNTIME="$HERE/runtime"

export LD_LIBRARY_PATH="$RUNTIME/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export GI_TYPELIB_PATH="$RUNTIME/lib/girepository-1.0"
export GSETTINGS_SCHEMA_DIR="$RUNTIME/share/glib-2.0/schemas"
export XDG_DATA_DIRS="$RUNTIME/share${XDG_DATA_DIRS:+:$XDG_DATA_DIRS}"

# gdk-pixbuf's own loader cache embeds each loader's absolute path, so
# it's regenerated fresh on every launch against wherever this bundle
# actually is right now, rather than baked in once at build time.
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
