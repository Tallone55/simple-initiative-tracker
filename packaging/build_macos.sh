#!/usr/bin/env bash
# Builds a self-contained .app bundle for Simple Initiative Tracker --
# the same "run in place" philosophy as the Linux portable build
# (build_linux_portable.sh) and the Windows portable build
# (build_windows.sh): everything the app needs travels inside the
# bundle, no separate install step, just double-click it (or drag it
# to /Applications, entirely optional).
#
# MUST be run on macOS, with Homebrew's own GTK4 already installed --
# there's no such thing as a portable prebuilt PyGObject wheel, since
# it's a thin binding over the system/Homebrew's own GObject
# Introspection, the same reasoning build_linux_portable.sh's own
# docstring gives for Linux.
#
# One-time setup:
#     brew install gtk4 libadwaita pygobject3 gobject-introspection librsvg
#
# Run from anywhere:
#     ./packaging/build_macos.sh
#
# Output: packaging/dist/Simple Initiative Tracker.app
# (scratch work happens in packaging/build/macos/, safe to delete)
#
# Portability boundary: everything the app needs travels in the
# bundle's Contents/Frameworks and Contents/Resources EXCEPT macOS's
# own system frameworks and libSystem -- see collect_dylibs.py's own
# denylist for the exact set. Font rendering relies on the host's own
# installed fonts (via Core Text, which GTK4's macOS backend uses)
# rather than bundling a font stack, matching the same choice the
# Linux and Windows portable builds make for their own font stacks.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMMON_DIR="$SCRIPT_DIR/common"
MACOS_DIR="$SCRIPT_DIR/macos"

source "$COMMON_DIR/app_metadata.sh"
source "$COMMON_DIR/version.sh"

# Used for every recursive directory copy below instead of cp -a or
# ditto -- both, in turn, hit a "File exists" error partway through a
# Homebrew-sourced tree (first the Python.framework copy with cp -a,
# then again one level deeper with ditto, then again after resolving
# one of the two paths involved via realpath()). Homebrew's install
# layout turned out to alias the same real directory under more than
# one apparent path in more than one place, not just the one place
# each previous fix addressed -- so rather than continuing to
# canonicalize individual paths one discovery at a time, every
# symlink encountered during these copies is dereferenced into a real
# copy of its target's actual content (symlinks=False), which removes
# the entire class of bug at once: there's no longer any alias chain
# left that could cause the same real directory to be visited, and
# therefore created at the destination, twice within one copy.
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
# Homebrew's own Python (whichever one PyGObject was installed
# against) copied wholesale, then site-packages narrowed to just gi
# and cairo, the same trim the Linux/Windows builds each do for their
# own bundled interpreter.

# Asked from Homebrew's own dependency graph rather than hardcoded --
# pygobject3 depends on whichever "python@X.Y" formula is current,
# and that version number drifts with every Homebrew release (this
# was previously hardcoded to "python@3.13" as a guess, which is
# exactly the kind of assumption that broke build_macos.sh's very
# first real run for an unrelated reason -- not worth leaving a
# second one sitting here for the *next* run to trip over).
PYTHON_FORMULA="$(brew deps --formula pygobject3 2>/dev/null | grep '^python@' | head -1 || true)"
if [ -n "$PYTHON_FORMULA" ] && PYTHON_PREFIX="$(brew --prefix "$PYTHON_FORMULA" 2>/dev/null)"; then
    PYTHON_FRAMEWORK_BIN="$PYTHON_PREFIX/bin/python3"
else
    # Falls back to whatever "python3" resolves to on PATH if the
    # dependency lookup itself didn't work out.
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
[ -n "$ADWAITA_DYLIB" ] && SEEDS+=("$ADWAITA_DYLIB")  # sit.py requires Adw 1 alongside Gtk 4

GDK_PIXBUF_LOADER="$(find "$BREW_PREFIX/lib/gdk-pixbuf-2.0" -name 'libpixbufloader-*.so' 2>/dev/null | head -1)"
if [ -n "$GDK_PIXBUF_LOADER" ]; then
    GDK_PIXBUF_LOADER_DIR="$(dirname "$GDK_PIXBUF_LOADER")"
    for loader in "$GDK_PIXBUF_LOADER_DIR"/*.so; do
        SEEDS+=("$loader")
    done
else
    # Empty rather than unset: downstream checks test for this
    # specifically (an empty find result piped through dirname would
    # otherwise silently become ".", the current directory -- not an
    # error -- and later steps would glob whatever unrelated files
    # happen to be sitting there instead of failing loudly here).
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
# collect_dylibs.py already rewrote the collected dylibs to reference
# each other via @rpath -- this is what makes @rpath actually resolve
# to Contents/Frameworks for the interpreter that loads them.

PYTHON_BIN="$CONTENTS/Resources/python/bin/python3"
install_name_tool -add_rpath "@executable_path/../Frameworks" "$PYTHON_BIN" 2>/dev/null || true
if [ -n "$GI_EXT" ]; then
    # $GI_EXT itself still points at the *original* Homebrew source
    # file (correct as a seed for collect_dylibs.py above, since
    # that's what needs to be walked for its real dependencies) --
    # but the rpath needs to go on the actual copy that ended up
    # inside the bundle, or the bundled _gi module never gets one and
    # "import gi" fails at runtime with a dyld "Library not loaded"
    # error despite the build itself completing without any
    # complaint.
    GI_EXT_BUNDLED="$CONTENTS/Resources/python/lib/python$PYTHON_VERSION/site-packages/gi/$(basename "$GI_EXT")"
    install_name_tool -add_rpath "@loader_path/../../../Frameworks" "$GI_EXT_BUNDLED" 2>/dev/null || true
else
    echo "Warning: PyGObject's _gi extension module wasn't found -- the built app likely can't import gi at runtime." >&2
fi

# Re-signed with a fresh ad-hoc signature after install_name_tool
# invalidates whatever Homebrew originally applied -- same reasoning,
# and same fix, as collect_dylibs.py's own _rewrite_install_names.
codesign --force --sign - "$PYTHON_BIN" 2>/dev/null || true
[ -n "$GI_EXT" ] && codesign --force --sign - "$GI_EXT_BUNDLED" 2>/dev/null || true

# -- icon ------------------------------------------------
# .icns has to be built from a set of rasterized PNG sizes -- rsvg-convert
# (from librsvg, a GTK4/gdk-pixbuf dependency already on the build
# machine) renders those from the project's one source SVG, then
# iconutil (a standard macOS command-line tool) assembles the .icns.

ICON_SVG="$SCRIPT_DIR/debian/$BUNDLE_ID.svg"
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
# A plain shell script here (rather than a compiled stub, unlike the
# Windows build) is entirely standard -- Contents/MacOS/<executable>
# just needs to be executable, and macOS doesn't require it to be a
# native binary the way Windows requires an actual .exe.

cat > "$CONTENTS/MacOS/$EXECUTABLE_NAME" << 'LAUNCHER'
#!/bin/sh
# Simple Initiative Tracker -- .app bundle launcher.
set -e
HERE="$(CDPATH= cd -- "$(dirname -- "$0")/../Resources" && pwd)"

export GI_TYPELIB_PATH="$HERE/lib/girepository-1.0"
export GSETTINGS_SCHEMA_DIR="$HERE/share/glib-2.0/schemas"
export XDG_DATA_DIRS="$HERE/share${XDG_DATA_DIRS:+:$XDG_DATA_DIRS}"

# gdk-pixbuf's own loader cache embeds each loader's absolute path, so
# it's regenerated fresh on every launch against wherever this bundle
# actually is right now, rather than baked in once at build time --
# same reasoning as the Linux and Windows portable builds.
PIXBUF_CACHE="$HERE/lib/gdk-pixbuf-2.0/loaders.cache.runtime"
"$HERE/lib/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders" "$HERE/lib/gdk-pixbuf-2.0/loaders/"*.so \
    > "$PIXBUF_CACHE" 2>/dev/null || true
export GDK_PIXBUF_MODULE_FILE="$PIXBUF_CACHE"

exec "$HERE/python/bin/python3" "$HERE/bin/sit.py" "$@"
LAUNCHER
chmod 755 "$CONTENTS/MacOS/$EXECUTABLE_NAME"

# -- archive ------------------------------------------------
# The .app *is* the distributable on macOS (Finder already treats it
# as a single double-clickable item) -- copied straight to dist/
# rather than wrapped in a further zip/dmg.

rm -rf "${DIST_DIR:?}/$APP_BUNDLE_NAME"
copy_tree "$APP_DIR" "$DIST_DIR/$APP_BUNDLE_NAME"

echo
echo "Built: $DIST_DIR/$APP_BUNDLE_NAME"
echo "Run with:   open \"$DIST_DIR/$APP_BUNDLE_NAME\""
echo "(Unsigned -- first launch needs a right-click > Open, or:"
echo " xattr -cr \"$DIST_DIR/$APP_BUNDLE_NAME\"  to clear the quarantine flag)"
