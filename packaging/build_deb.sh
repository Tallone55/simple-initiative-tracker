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

# rsvg-convert rasterizes a pixmaps fallback icon -- see the comment
# near ICON_SRC below for why this exists. Needs librsvg2-bin
# installed on the build machine.
if ! command -v rsvg-convert >/dev/null 2>&1; then
    echo "Error: rsvg-convert not found -- needed to rasterize a pixmaps fallback icon (see build_deb.sh's own comment near ICON_SRC for why this exists). Install librsvg2-bin." >&2
    exit 1
fi

rm -rf "$PKGROOT"
mkdir -p \
    "$PKGROOT/DEBIAN" \
    "$PKGROOT/usr/lib/$PKG_NAME/bin" \
    "$PKGROOT/usr/lib/$PKG_NAME/ui" \
    "$PKGROOT/usr/bin" \
    "$PKGROOT/usr/share/applications" \
    "$PKGROOT/usr/share/icons/hicolor/scalable/apps" \
    "$PKGROOT/usr/share/pixmaps" \
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

# GTK's icon cache staleness check wants the icon's own parent
# directory to have a newer mtime than the cache file -- confirmed
# against a real Debian bug report (#369755) that this doesn't always
# happen "for free" just from a file landing in an existing directory,
# depending on how it got there. Touched explicitly, before rebuilding
# the cache below, so that check can't be fooled by a directory mtime
# dpkg's own extraction happened not to bump on some particular
# dpkg/filesystem combination.
touch /usr/share/icons/hicolor/scalable/apps 2>/dev/null || true

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi

# Cinnamon's own menu watches .desktop files for changes (via GIO's
# GAppInfoMonitor, inotify-based) and only re-resolves an app's icon
# when one actually changes -- it does NOT re-check on its own just
# because the icon cache file above was rebuilt. Two different fixes
# for this were tried directly against real installs and real
# reinstalls -- a plain \`touch\` of the .desktop file, then a fuller
# copy-then-rename specifically reproducing the richer file-change
# event a real reinstall's own file replacement produces (confirmed
# via inotifywait that touch alone only generates a bare ATTRIB event,
# versus copy-then-rename's CREATE/MODIFY/CLOSE_WRITE/MOVED_FROM/
# MOVED_TO sequence) -- and neither fixed a genuinely fresh install
# (only ever working on a reinstall over one already in place, which
# doesn't need fixing to begin with). That points to the gap being
# specifically in how Cinnamon's own already-running app-system object
# gets constructed the first time it sees this app's ID, not in
# anything about how the .desktop file itself changes -- a boundary no
# postinst-side file trick can reach into after the fact. Verified
# directly, across both attempts, that the underlying icon-theme.cache
# file itself is correctly and promptly rebuilt with the right content
# by the two steps above, in both a fresh install and an upgrade over
# an existing one, so this genuinely isn't about anything wrong with
# the on-disk cache this script controls.
#
# Given that, this doesn't try a third .desktop-file trick. The
# pixmaps fallback icon below (see the comment near ICON_SRC)
# addresses the same symptom a different way -- sidestepping
# hicolor/Cinnamon's own live-refresh behavior entirely, rather than
# depending on it.

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

cat > "$PKGROOT/usr/share/applications/$BUNDLE_ID.desktop" << DESKTOP
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=Track combat initiative order for tabletop games
Exec=$EXECUTABLE_NAME %f
Icon=$BUNDLE_ID
Categories=Game;Utility;
MimeType=text/csv;
Terminal=false
StartupNotify=true
DESKTOP

ICON_SRC="$PROJECT_ROOT/ui/$BUNDLE_ID.svg"
if [ ! -f "$ICON_SRC" ]; then
    echo "Error: expected icon at $ICON_SRC (not found)." >&2
    exit 1
fi
cp "$ICON_SRC" "$PKGROOT/usr/share/icons/hicolor/scalable/apps/$BUNDLE_ID.svg"

# Also rasterized to a plain, single-resolution PNG in
# /usr/share/pixmaps/. A real .deb from a large, professionally
# packaged application (Discord) was inspected directly and found to
# rely on pixmaps as its *only* icon delivery mechanism, specifically
# because it isn't backed by hicolor's own cached icon-theme.cache
# index at all -- a bare Icon=$BUNDLE_ID reference in the .desktop
# file above resolves through hicolor first when that succeeds,
# falling back to pixmaps -- a plain, uncached file lookup -- when it
# doesn't. This exists alongside the scalable SVG above, not instead
# of it, specifically to keep crisp vector rendering wherever hicolor
# does resolve correctly (confirmed directly: the taskbar icon, which
# goes through this same hicolor lookup, already renders correctly
# from the SVG on a fresh install), while giving Cinnamon's menu
# applet specifically a cache-independent fallback for the one case
# confirmed NOT to resolve promptly there -- a genuinely fresh
# install, before that app has ever been seen by Cinnamon's own
# already-running app-system object. Two different postinst-side
# fixes aimed at that gap (see the comment above, near the .desktop
# GAppInfoMonitor discussion) were tried and confirmed, on real
# installs, not to close it -- this sidesteps it instead of depending
# on it. 256px chosen to match Discord's own real, shipped size for
# the same purpose.
rsvg-convert -w 256 -h 256 "$ICON_SRC" -o "$PKGROOT/usr/share/pixmaps/$BUNDLE_ID.png"

# -- permissions ------------------------------------------------

find "$PKGROOT" -type d -exec chmod 755 {} +
find "$PKGROOT" -type f -exec chmod 644 {} +
chmod 755 "$PKGROOT/DEBIAN/postinst" "$PKGROOT/DEBIAN/prerm" "$PKGROOT/usr/bin/$EXECUTABLE_NAME"

# -- build ------------------------------------------------

dpkg-deb --build --root-owner-group "$PKGROOT" "$DEB_FILE"
sign_file_gpg "$DEB_FILE"

echo
echo "Built: $DEB_FILE"
[ -f "$DEB_FILE.asc" ] && echo "Signature: $DEB_FILE.asc (verify with: gpg --verify $DEB_FILE.asc $DEB_FILE)"
echo "Install with:  sudo apt install $DEB_FILE"
echo "Run with:      $EXECUTABLE_NAME"
