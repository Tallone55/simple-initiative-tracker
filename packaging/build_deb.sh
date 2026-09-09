#!/usr/bin/env bash
# Builds a .deb package for Simple Initiative Tracker.
#
# Run from anywhere:
#     ./packaging/build_deb.sh
#
# Output: packaging/dist/<package-name>_<version>_all.deb

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMMON_DIR="$SCRIPT_DIR/common"

source "$COMMON_DIR/app_metadata.sh"
source "$COMMON_DIR/project_metadata.sh"
source "$COMMON_DIR/signing.sh"

BUILD_DIR="$SCRIPT_DIR/build/deb"
PKGROOT="$BUILD_DIR/pkgroot"
DIST_DIR="$SCRIPT_DIR/dist"

ARCH="all"
DEB_FILE="$DIST_DIR/${PKG_NAME}_${VERSION}_${ARCH}.deb"

echo "Building ${APP_NAME} ${VERSION} (.deb)..."

rm -rf "$PKGROOT"
mkdir -p \
    "$PKGROOT/DEBIAN" \
    "$PKGROOT/usr/lib/$PKG_NAME/bin" \
    "$PKGROOT/usr/lib/$PKG_NAME/ui" \
    "$PKGROOT/usr/bin" \
    "$PKGROOT/usr/share/applications" \
    "$PKGROOT/usr/share/icons/hicolor/scalable/apps" \
    "$DIST_DIR"

# -- control files ------------------------------------------------

cat > "$PKGROOT/DEBIAN/control" << CONTROL
Package: $PKG_NAME
Version: $VERSION
Section: games
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0 (>= 4.10), librsvg2-common
Maintainer: $MAINTAINER ($MAINTAINER_EMAIL)
Description: $APP_NAME
 $DESCRIPTION
 Tracks creature hitpoints, armor class, and turn order, with support
 for dice-notation and arithmetic expressions, CSV import/export, and
 undo/redo. Supports some (hacked-together) Cinnamon theming.
CONTROL

cat > "$PKGROOT/DEBIAN/postinst" << POSTINST
#!/bin/sh
set -e

# No touch, no gtk-update-icon-cache, no update-desktop-database here
# anymore. All three were tried, in every order and combination this
# investigation went through (touch alone; touch then a full
# copy-then-rename; both cache-rebuild calls before the .desktop file
# existed; both after it; both removed entirely, relying only on
# hicolor-icon-theme's and desktop-file-utils's own dpkg triggers --
# see /var/lib/dpkg/info/*.triggers, both register "interest-noawait"
# on the relevant directory and fire automatically regardless of
# anything this script does) -- confirmed, each time, via a real
# install watched end to end with inotifywait, that the underlying
# filesystem state (icon before .desktop file, correct cache content,
# correct dpkg file tracking) was exactly as intended, and confirmed,
# each time, that the reported symptom persisted anyway. That's a
# strong signal this was never something happening at the filesystem
# level, or reachable from this script, to begin with -- see
# data.tar's own comment on how the actual .desktop file ordering is
# now guaranteed regardless of postinst.
#
# \$2 is the previously-configured version when dpkg is upgrading an
# existing install in place (its own convention: postinst is called
# as "configure <most-recently-configured-version>"), empty on a
# fresh install. dpkg itself already handles the actual file
# replacement and the removal of anything dropped between versions --
# this is just surfacing that an upgrade happened, since a running
# GUI instance won't pick up the new files until it's restarted.
if [ "\$1" = "configure" ] && [ -n "\${2:-}" ]; then
    echo "Upgraded $APP_NAME from \$2 to $VERSION."
    echo "If $APP_NAME was already running, restart it to use the new version."
fi

exit 0
POSTINST

cat > "$PKGROOT/DEBIAN/prerm" << PRERM
#!/bin/sh
set -e

# Run unconditionally (upgrade, remove, or deconfigure alike), not
# just on upgrade: confirmed directly that dpkg won't force-delete a
# directory containing files it doesn't know about even on a full
# removal -- it leaves the directory (and whatever untracked content
# is in it) behind with just a warning, rather than risking deleting
# something that might be user data. __pycache__ was never part of
# this package's own file list either way (Python generates it at
# runtime, this package never ships it), so dpkg has no way to know
# to remove it on its own on any path.
find /usr/lib/$PKG_NAME/bin -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

exit 0
PRERM

# -- application source ------------------------------------------------

cp "$PROJECT_ROOT"/bin/*.py "$PKGROOT/usr/lib/$PKG_NAME/bin/"
_stamp_app_metadata "$PKGROOT/usr/lib/$PKG_NAME/bin/app_metadata.py"
cp "$PROJECT_ROOT"/ui/*.ui "$PKGROOT/usr/lib/$PKG_NAME/ui/"
cp "$PROJECT_ROOT/ui/$BUNDLE_ID.svg" "$PKGROOT/usr/lib/$PKG_NAME/ui/"

# -- launcher ------------------------------------------------

cat > "$PKGROOT/usr/bin/$EXECUTABLE_NAME" << LAUNCHER
#!/bin/sh
exec python3 /usr/lib/$PKG_NAME/bin/sit.py "\$@"
LAUNCHER

# -- desktop entry + icon ------------------------------------------------
#
# Name=, Comment=, Categories=, MimeType=, Terminal=, StartupNotify=,
# and StartupWMClass= all come from a single shared template
# (ui/net.mystive.sit.desktop.in) rather than being hand-written here
# a second time -- bin/sit.py fills in the exact same template for the
# portable Linux build's own .desktop file. Only Exec= and Icon= are
# filled in separately by each (Name= is shared too, via $APP_NAME
# here and a matching hardcoded string there, rather than being pulled
# from this project's own single build-time source of truth a second
# way -- there isn't an equivalent to app_metadata.sh's own shell
# variables reachable from a frozen PyInstaller build): Exec= is a
# fixed, installed path here ("$EXECUTABLE_NAME %f", resolved via
# $PATH) but has to be resolved fresh at runtime there (an extracted,
# portable bundle's own location isn't known until it's actually
# running).
#
# Icon= is an absolute path here, not a bare icon-theme name, even
# though this .deb does install the icon into the system's own
# hicolor theme, where a bare name would normally resolve correctly
# on its own. Tried as a further, later attempt after ordering, dpkg
# file tracking, and every combination of cache-rebuild calls all
# independently failed to resolve a real, reported "menu icon stuck on
# the generic fallback" symptom: a bare name depends on Cinnamon's own
# icon-theme name-to-file resolution succeeding, which is exactly the
# layer every one of those previous fixes was trying, indirectly, to
# get right -- an absolute path bypasses that resolution step
# entirely, the same way the portable build's own .desktop file
# already has to (an extracted bundle's icon was never installed into
# an icon theme location at all, so it never had a name to resolve in
# the first place, and has used an absolute path from the start). This
# is only possible for this .deb specifically because it installs the
# icon to a single, fixed, always-the-same path -- not something the
# portable build could ever rely on, since its own install location
# varies by wherever it happens to be extracted.
#
# Written directly to its real, final location -- a normal,
# dpkg-tracked package file, same as everything else here. An earlier
# version staged this elsewhere and copied it into place from
# postinst instead, specifically to control *when* it appeared
# relative to the icon below; that's now handled by controlling
# data.tar's own member order further down this script, which gets
# the same ordering guarantee without giving up dpkg's own tracking of
# this file (see postinst's own comment on why that tracking turned
# out to matter for real, beyond just being tidy).
DESKTOP_TEMPLATE="$PROJECT_ROOT/ui/$BUNDLE_ID.desktop.in"
if [ ! -f "$DESKTOP_TEMPLATE" ]; then
    echo "Error: expected .desktop template at $DESKTOP_TEMPLATE (not found)." >&2
    exit 1
fi
sed \
    -e "s|@NAME@|$APP_NAME|" \
    -e "s|@EXEC@|$EXECUTABLE_NAME %f|" \
    -e "s|@ICON@|/usr/share/icons/hicolor/scalable/apps/$BUNDLE_ID.svg|" \
    "$DESKTOP_TEMPLATE" > "$PKGROOT/usr/share/applications/$BUNDLE_ID.desktop"

ICON_SRC="$PROJECT_ROOT/ui/$BUNDLE_ID.svg"
if [ ! -f "$ICON_SRC" ]; then
    echo "Error: expected icon at $ICON_SRC (not found)." >&2
    exit 1
fi
cp "$ICON_SRC" "$PKGROOT/usr/share/icons/hicolor/scalable/apps/$BUNDLE_ID.svg"

# -- permissions ------------------------------------------------

find "$PKGROOT" -type d -exec chmod 755 {} +
find "$PKGROOT" -type f -exec chmod 644 {} +
chmod 755 "$PKGROOT/DEBIAN/postinst" "$PKGROOT/DEBIAN/prerm" "$PKGROOT/usr/bin/$EXECUTABLE_NAME"

# -- build ------------------------------------------------
#
# dpkg-deb's own build process sorts data.tar's members strictly by
# path -- confirmed against Debian bug #719845, "dpkg-deb: Make file
# order within {data,control}.tar.gz deterministic", a deliberate,
# hardcoded sort baked into dpkg-deb's own C source since 2013 for
# reproducible builds, not something exposed via any CLI flag to
# override. That always puts usr/share/applications/ before
# usr/share/icons/ for any path starting with those two prefixes,
# regardless of file content -- confirmed directly, earlier, as the
# actual root cause of this app's icon not resolving on a fresh
# install: Cinnamon's own menu sees the .desktop file appear,
# mid-unpack, before the icon it references exists at all.
#
# data.tar is therefore built directly here instead of delegating to
# `dpkg-deb --build`, specifically to control that member order
# explicitly: every file goes in sorted, the same way dpkg-deb's own
# default does, for the same reproducibility reasons, EXCEPT this
# app's own .desktop entry, which goes in last -- guaranteed to unpack
# only once its own icon, and everything else in this package, already
# has. An earlier version of this same fix tried to guarantee that
# ordering from postinst instead, by shipping the .desktop file to a
# staging path and copying it into place after the icon was certain to
# already be unpacked -- confirmed working for the ordering itself,
# but it broke dpkg's own file tracking for that path (a real,
# reported regression: \`dpkg -S\` no longer recognized it, which
# turned out to also be what Cinnamon's own "uninstall from the menu"
# feature depends on, since dpkg no longer shipped it there directly).
# Controlling data.tar's own member order instead gets the same
# ordering guarantee while keeping the .desktop file a normal,
# directly-shipped, fully dpkg-tracked package file, exactly like
# every other file here.
CONTROL_TAR="$BUILD_DIR/control.tar"
DATA_TAR="$BUILD_DIR/data.tar"
rm -f "$CONTROL_TAR" "$CONTROL_TAR.zst" "$DATA_TAR" "$DATA_TAR.zst"

tar --create --format=gnu --owner=0 --group=0 --numeric-owner \
    -C "$PKGROOT/DEBIAN" --file="$CONTROL_TAR" .
zstd -q -f "$CONTROL_TAR" -o "$CONTROL_TAR.zst"

DESKTOP_REL="usr/share/applications/$BUNDLE_ID.desktop"
DATA_FILELIST="$BUILD_DIR/data-filelist.txt"
(
    cd "$PKGROOT"
    find . -mindepth 1 ! -path "./DEBIAN*" ! -path "./$DESKTOP_REL" | sort
    echo "./$DESKTOP_REL"
) > "$DATA_FILELIST"
tar --create --format=gnu --owner=0 --group=0 --numeric-owner --no-recursion \
    -C "$PKGROOT" --file="$DATA_TAR" --files-from="$DATA_FILELIST"
zstd -q -f "$DATA_TAR" -o "$DATA_TAR.zst"

echo "2.0" > "$BUILD_DIR/debian-binary"

rm -f "$DEB_FILE"
ar rc "$DEB_FILE" "$BUILD_DIR/debian-binary" "$CONTROL_TAR.zst" "$DATA_TAR.zst"

sign_file_gpg "$DEB_FILE"

echo
echo "Built: $DEB_FILE"
[ -f "$DEB_FILE.asc" ] && echo "Signature: $DEB_FILE.asc (verify with: gpg --verify $DEB_FILE.asc $DEB_FILE)"
echo "Install with:  sudo apt install $DEB_FILE"
echo "Run with:      $EXECUTABLE_NAME"
