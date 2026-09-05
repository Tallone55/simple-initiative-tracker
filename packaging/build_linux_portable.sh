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
# Output: packaging/dist/<package-name>-<version>-linux-x86_64.tar.gz
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
source "$COMMON_DIR/project_metadata.sh"

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
_stamp_app_metadata "$STAGE_DIR/bin/app_metadata.py"
cp "$PROJECT_ROOT"/ui/*.ui "$STAGE_DIR/ui/"

# -- portable Python interpreter ------------------------------------------------

# Built up explicitly from proven-needed pieces, rather than copying
# the whole interpreter prefix and pruning specific things out
# afterward (bin/'s other executables -- pip, idle, pydoc,
# python3.14-config; include/; share/; Tcl/Tk's native libraries;
# the unused libpythonX.Y.so.1.0 -- all had to be discovered and
# removed by hand in earlier passes at this, one at a time, which is
# exactly the same architectural problem this replaces on Windows.
# Nothing here is copied speculatively:
#   - bin/python$PYTHON_VERSION is the one executable the launcher
#     script actually runs; confirmed directly (ldd) its own only
#     dependencies are the standard glibc family already covered by
#     collect_shared_libs.py's own denylist as host-provided -- so
#     it's also seeded into that same closure walk below, the same
#     validate-before-bundling mechanism already used for the GTK
#     stack, rather than asserted once and left unverified against
#     a future Python version that might need something new.
#   - lib/python$PYTHON_VERSION/ is the traced stdlib (unchanged
#     from before): import every one of this app's own bin/*.py
#     files and record what actually lands in sys.modules, then copy
#     only that -- the same dependency-tracing technique packagers
#     like PyInstaller use internally (see list_needed_stdlib.py's
#     own docstring).
#   - site-packages holds only gi/cairo and their dist-info, same as
#     before.
mkdir -p "$STAGE_DIR/runtime/python/bin"
cp -a "$PYTHON_INTERPRETER/bin/python$PYTHON_VERSION" "$STAGE_DIR/runtime/python/bin/"

BUNDLED_STDLIB="$STAGE_DIR/runtime/python/lib/python$PYTHON_VERSION"
mkdir -p "$BUNDLED_STDLIB"
NEEDED_STDLIB_NAMES="$(uv run --project "$PROJECT_ROOT" python "$COMMON_DIR/list_needed_stdlib.py" "$PROJECT_ROOT/bin")"
if [ -z "$NEEDED_STDLIB_NAMES" ]; then
    echo "Error: list_needed_stdlib.py produced no output -- the trace itself failed." >&2
    exit 1
fi
while IFS= read -r name; do
    name="${name%$'\r'}"
    [ -z "$name" ] && continue
    src="$PYTHON_INTERPRETER/lib/python$PYTHON_VERSION/$name"
    if [ ! -e "$src" ]; then
        echo "Warning: traced stdlib name '$name' not found at $src -- skipping." >&2
        continue
    fi
    cp -a "$src" "$BUNDLED_STDLIB/"
done <<< "$NEEDED_STDLIB_NAMES"
find "$BUNDLED_STDLIB" -name '__pycache__' -type d -prune -exec rm -rf {} +

mkdir -p "$BUNDLED_STDLIB/site-packages"
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

SEEDS=("$GTK_LIB" "$GI_EXT" "$GI_CAIRO_EXT" "$PYCAIRO_EXT" "$PIXBUF_QUERY_LOADERS" "$PYTHON_INTERPRETER/bin/python$PYTHON_VERSION")
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

cp "$SCRIPT_DIR/$BUNDLE_ID.svg" "$STAGE_DIR/runtime/share/icons/hicolor/scalable/apps/$BUNDLE_ID.svg"

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
