#!/usr/bin/env bash
# Builds a self-contained .app bundle for Simple Initiative Tracker.
#
# MUST be run on macOS, with Homebrew's own GTK4 already installed.
#
# One-time setup:
#     brew install gtk4 libadwaita pygobject3 gobject-introspection librsvg
#
# Run from anywhere:
#     ./packaging/build_macos.sh
#
# Output: packaging/dist/Simple Initiative Tracker.app
#
# Portability boundary: everything the app needs travels in
# Contents/Frameworks and Contents/Resources EXCEPT macOS's own
# system frameworks and libSystem -- see collect_dylibs.py's
# denylist. Font rendering relies on the host's own installed fonts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMMON_DIR="$SCRIPT_DIR/common"
MACOS_DIR="$SCRIPT_DIR/macos"

source "$COMMON_DIR/app_metadata.sh"
source "$COMMON_DIR/project_metadata.sh"

# Dereferences symlinks (rather than cp -a/ditto, which both hit
# "File exists" errors partway through Homebrew's heavily-aliased
# install layout) so every recursive copy below is unconditionally
# safe regardless of how many alias chains a given tree happens to
# have.
copy_tree() {
    python3 -c '
import shutil, sys
src, dst = sys.argv[1], sys.argv[2]
shutil.rmtree(dst, ignore_errors=True)
shutil.copytree(src, dst, symlinks=False, dirs_exist_ok=True)
' "$1" "$2"
}

if [ "$(uname)" != "Darwin" ]; then
    echo "Error: this script must be run on macOS." >&2
    exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
    echo "Error: Homebrew not found. Install it from https://brew.sh, then:" >&2
    echo "  brew install gtk4 libadwaita pygobject3 gobject-introspection librsvg" >&2
    exit 1
fi

BREW_PREFIX="$(brew --prefix)"
ARCH="$(uname -m)"
APP_BUNDLE_NAME="${APP_NAME}.app"
TARBALL_NAME="${PKG_NAME}-${VERSION}-macos-${ARCH}"

BUILD_DIR="$SCRIPT_DIR/build/macos"
APP_DIR="$BUILD_DIR/$APP_BUNDLE_NAME"
CONTENTS="$APP_DIR/Contents"
DIST_DIR="$SCRIPT_DIR/dist"

echo "Building ${APP_NAME} ${VERSION} (macOS .app, $ARCH)..."
echo "  Homebrew prefix: $BREW_PREFIX"

rm -rf "$APP_DIR"
mkdir -p \
    "$CONTENTS/MacOS" \
    "$CONTENTS/Resources/bin" \
    "$CONTENTS/Resources/ui" \
    "$CONTENTS/Frameworks" \
    "$CONTENTS/Resources/lib/girepository-1.0" \
    "$CONTENTS/Resources/lib/gdk-pixbuf-2.0/loaders" \
    "$CONTENTS/Resources/share/glib-2.0/schemas" \
    "$DIST_DIR"

# -- application source ------------------------------------------------

cp "$PROJECT_ROOT"/bin/*.py "$CONTENTS/Resources/bin/"
cp "$PROJECT_ROOT"/ui/*.ui "$CONTENTS/Resources/ui/"

# -- portable Python interpreter ------------------------------------------------

PYTHON_FORMULA="$(brew deps --formula pygobject3 2>/dev/null | grep '^python@' | head -1 || true)"
if [ -n "$PYTHON_FORMULA" ] && PYTHON_PREFIX="$(brew --prefix "$PYTHON_FORMULA" 2>/dev/null)"; then
    PYTHON_FRAMEWORK_BIN="$PYTHON_PREFIX/bin/python3"
else
    PYTHON_FRAMEWORK_BIN="$(command -v python3 || true)"
fi
if [ ! -x "$PYTHON_FRAMEWORK_BIN" ]; then
    echo "Error: could not find a usable python3 (checked pygobject3's own python@ dependency via 'brew deps', then PATH)." >&2
    exit 1
fi
PYTHON_BASE_PREFIX="$("$PYTHON_FRAMEWORK_BIN" -c 'import sys; print(sys.base_prefix)')"
PYTHON_VERSION="$("$PYTHON_FRAMEWORK_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
SITE_PACKAGES="$("$PYTHON_FRAMEWORK_BIN" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"

copy_tree "$PYTHON_BASE_PREFIX" "$CONTENTS/Resources/python"
rm -rf "$CONTENTS/Resources/python/lib/python$PYTHON_VERSION/site-packages"/*

for pkg in gi cairo; do
    copy_tree "$SITE_PACKAGES/$pkg" "$CONTENTS/Resources/python/lib/python$PYTHON_VERSION/site-packages/$pkg"
done
for dist_info in "$SITE_PACKAGES"/pygobject-*.dist-info "$SITE_PACKAGES"/pycairo-*.dist-info; do
    if [ -d "$dist_info" ]; then
        copy_tree "$dist_info" "$CONTENTS/Resources/python/lib/python$PYTHON_VERSION/site-packages/$(basename "$dist_info")"
    fi
done

# -- GTK4/GLib/etc. dylib closure ------------------------------------------------

GTK_DYLIB="$(find "$BREW_PREFIX/opt/gtk4/lib" -name 'libgtk-4.*.dylib' | head -1)"
ADWAITA_DYLIB="$(find "$BREW_PREFIX/opt/libadwaita/lib" -name 'libadwaita-1.*.dylib' 2>/dev/null | head -1)"
GI_EXT="$(find "$SITE_PACKAGES/gi" -maxdepth 1 -name '_gi.cpython*.so' | head -1)"
GI_CAIRO_EXT="$(find "$SITE_PACKAGES/gi" -maxdepth 1 -name '_gi_cairo.cpython*.so' | head -1)"
PYCAIRO_EXT="$(find "$SITE_PACKAGES/cairo" -maxdepth 1 -name '_cairo.cpython*.so' | head -1)"
PIXBUF_QUERY_LOADERS="$(brew --prefix gdk-pixbuf)/bin/gdk-pixbuf-query-loaders"

if [ -z "$GTK_DYLIB" ]; then
    echo "Error: libgtk-4.dylib not found under $BREW_PREFIX/opt/gtk4/lib -- is 'brew install gtk4' done?" >&2
    exit 1
fi

SEEDS=("$GTK_DYLIB" "$PIXBUF_QUERY_LOADERS")
[ -n "$GI_EXT" ] && SEEDS+=("$GI_EXT")
[ -n "$GI_CAIRO_EXT" ] && SEEDS+=("$GI_CAIRO_EXT")
[ -n "$PYCAIRO_EXT" ] && SEEDS+=("$PYCAIRO_EXT")
[ -n "$ADWAITA_DYLIB" ] && SEEDS+=("$ADWAITA_DYLIB")

GDK_PIXBUF_LOADER="$(find "$BREW_PREFIX/lib/gdk-pixbuf-2.0" -name 'libpixbufloader-*.so' 2>/dev/null | head -1)"
if [ -n "$GDK_PIXBUF_LOADER" ]; then
    GDK_PIXBUF_LOADER_DIR="$(dirname "$GDK_PIXBUF_LOADER")"
    for loader in "$GDK_PIXBUF_LOADER_DIR"/*.so; do
        SEEDS+=("$loader")
    done
else
    GDK_PIXBUF_LOADER_DIR=""
    echo "Warning: no gdk-pixbuf loaders found under $BREW_PREFIX/lib/gdk-pixbuf-2.0 -- image loading (icons, PNGs, etc.) may not work in the built app." >&2
fi

python3 "$MACOS_DIR/collect_dylibs.py" --out "$CONTENTS/Frameworks" "${SEEDS[@]}"

if [ -d "$GDK_PIXBUF_LOADER_DIR" ]; then
    cp "$GDK_PIXBUF_LOADER_DIR"/*.so "$CONTENTS/Resources/lib/gdk-pixbuf-2.0/loaders/"
fi
cp "$PIXBUF_QUERY_LOADERS" "$CONTENTS/Resources/lib/gdk-pixbuf-2.0/"

# -- GObject Introspection typelibs ------------------------------------------------

GTK_TYPELIB="$(find "$BREW_PREFIX/lib/girepository-1.0" -name 'Gtk-4.0.typelib' 2>/dev/null | head -1)"
if [ -z "$GTK_TYPELIB" ]; then
    echo "Error: Gtk-4.0.typelib not found under $BREW_PREFIX/lib/girepository-1.0 -- is 'brew install gtk4' done?" >&2
    exit 1
fi
TYPELIB_DIR="$(dirname "$GTK_TYPELIB")"
cp "$TYPELIB_DIR"/*.typelib "$CONTENTS/Resources/lib/girepository-1.0/"

# -- GSettings schemas ------------------------------------------------

cp "$BREW_PREFIX/share/glib-2.0/schemas/gschemas.compiled" "$CONTENTS/Resources/share/glib-2.0/schemas/"

# -- rpath: point the bundled Python at Contents/Frameworks ------------------------------------------------

PYTHON_BIN="$CONTENTS/Resources/python/bin/python3"
install_name_tool -add_rpath "@executable_path/../Frameworks" "$PYTHON_BIN" 2>/dev/null || true
if [ -n "$GI_EXT" ]; then
    # The rpath must go on the copy inside the bundle, not $GI_EXT's
    # own original Homebrew path (still needed above as a
    # collect_dylibs.py seed).
    GI_EXT_BUNDLED="$CONTENTS/Resources/python/lib/python$PYTHON_VERSION/site-packages/gi/$(basename "$GI_EXT")"
    install_name_tool -add_rpath "@loader_path/../../../Frameworks" "$GI_EXT_BUNDLED" 2>/dev/null || true
else
    echo "Warning: PyGObject's _gi extension module wasn't found -- the built app likely can't import gi at runtime." >&2
fi

codesign --force --sign - "$PYTHON_BIN" 2>/dev/null || true
[ -n "$GI_EXT" ] && codesign --force --sign - "$GI_EXT_BUNDLED" 2>/dev/null || true

# -- icon ------------------------------------------------

ICON_SVG="$SCRIPT_DIR/$BUNDLE_ID.svg"
ICONSET_DIR="$BUILD_DIR/$BUNDLE_ID.iconset"
rm -rf "$ICONSET_DIR"
mkdir -p "$ICONSET_DIR"

if command -v rsvg-convert >/dev/null 2>&1; then
    for size in 16 32 128 256 512; do
        rsvg-convert -w "$size" -h "$size" "$ICON_SVG" -o "$ICONSET_DIR/icon_${size}x${size}.png"
        double=$((size * 2))
        rsvg-convert -w "$double" -h "$double" "$ICON_SVG" -o "$ICONSET_DIR/icon_${size}x${size}@2x.png"
    done
    iconutil -c icns "$ICONSET_DIR" -o "$CONTENTS/Resources/$BUNDLE_ID.icns"
else
    echo "Warning: rsvg-convert not found (part of librsvg) -- shipping without an app icon." >&2
    echo "         brew install librsvg to include one." >&2
fi

# -- Info.plist ------------------------------------------------

sed \
    -e "s/@EXECUTABLE_NAME@/$EXECUTABLE_NAME/g" \
    -e "s/@BUNDLE_ID@/$BUNDLE_ID/g" \
    -e "s/@APP_NAME@/$APP_NAME/g" \
    -e "s/@VERSION@/$VERSION/g" \
    "$MACOS_DIR/Info.plist.in" > "$CONTENTS/Info.plist"

# -- launcher ------------------------------------------------

cat > "$CONTENTS/MacOS/$EXECUTABLE_NAME" << 'LAUNCHER'
#!/bin/sh
set -e
HERE="$(CDPATH= cd -- "$(dirname -- "$0")/../Resources" && pwd)"

export GI_TYPELIB_PATH="$HERE/lib/girepository-1.0"
export GSETTINGS_SCHEMA_DIR="$HERE/share/glib-2.0/schemas"
export XDG_DATA_DIRS="$HERE/share${XDG_DATA_DIRS:+:$XDG_DATA_DIRS}"

PIXBUF_CACHE="$HERE/lib/gdk-pixbuf-2.0/loaders.cache.runtime"
"$HERE/lib/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders" "$HERE/lib/gdk-pixbuf-2.0/loaders/"*.so \
    > "$PIXBUF_CACHE" 2>/dev/null || true
export GDK_PIXBUF_MODULE_FILE="$PIXBUF_CACHE"

exec "$HERE/python/bin/python3" "$HERE/bin/sit.py" "$@"
LAUNCHER
chmod 755 "$CONTENTS/MacOS/$EXECUTABLE_NAME"

# -- archive ------------------------------------------------

rm -rf "${DIST_DIR:?}/$APP_BUNDLE_NAME"
copy_tree "$APP_DIR" "$DIST_DIR/$APP_BUNDLE_NAME"

echo
echo "Built: $DIST_DIR/$APP_BUNDLE_NAME"
echo "Run with:   open \"$DIST_DIR/$APP_BUNDLE_NAME\""
echo "(Unsigned -- first launch needs a right-click > Open, or:"
echo " xattr -cr \"$DIST_DIR/$APP_BUNDLE_NAME\"  to clear the quarantine flag)"
