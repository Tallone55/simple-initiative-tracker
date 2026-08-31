#!/usr/bin/env bash
# Builds a .deb package for Simple Initiative Tracker.
#
# Assumes this script lives in packaging/, as a sibling of bin/ and
# ui/ at the project root (the same layout ui_paths.py's unfrozen
# branch already expects). Run from anywhere:
#
#     ./packaging/build_deb.sh
#
# Output: packaging/build/initiative-tracker_<version>_all.deb
#
# Package layout on the target system:
#   /usr/lib/initiative-tracker/bin/*.py   -- application source
#   /usr/lib/initiative-tracker/ui/*.ui    -- .ui files (sibling of
#                                              bin/, exactly matching
#                                              the layout ui_paths.py's
#                                              __file__-relative
#                                              resolution expects)
#   /usr/bin/sit                           -- launcher script
#   /usr/share/applications/net.mystive.sit.desktop
#   /usr/share/icons/hicolor/scalable/apps/net.mystive.sit.svg

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PKG_NAME="initiative-tracker"
ICON_NAME="net.mystive.sit"
BUILD_DIR="$SCRIPT_DIR/build"
PKGROOT="$BUILD_DIR/pkgroot"

VERSION="$(grep -oP '^Version:\s*\K.+' "$SCRIPT_DIR/debian/control")"
ARCH="all"
DEB_FILE="$BUILD_DIR/${PKG_NAME}_${VERSION}_${ARCH}.deb"

echo "Building ${PKG_NAME} ${VERSION}..."

rm -rf "$PKGROOT"
mkdir -p \
    "$PKGROOT/DEBIAN" \
    "$PKGROOT/usr/lib/$PKG_NAME/bin" \
    "$PKGROOT/usr/lib/$PKG_NAME/ui" \
    "$PKGROOT/usr/bin" \
    "$PKGROOT/usr/share/applications" \
    "$PKGROOT/usr/share/icons/hicolor/scalable/apps"

# -- control files ------------------------------------------------

cp "$SCRIPT_DIR/debian/control" "$PKGROOT/DEBIAN/control"
cp "$SCRIPT_DIR/debian/postinst" "$PKGROOT/DEBIAN/postinst"

# -- application source ------------------------------------------------

cp "$PROJECT_ROOT"/bin/*.py "$PKGROOT/usr/lib/$PKG_NAME/bin/"
cp "$PROJECT_ROOT"/ui/*.ui "$PKGROOT/usr/lib/$PKG_NAME/ui/"

# -- launcher ------------------------------------------------

cat > "$PKGROOT/usr/bin/sit" << LAUNCHER
#!/bin/sh
exec python3 /usr/lib/$PKG_NAME/bin/sit.py "\$@"
LAUNCHER

# -- desktop entry + icon ------------------------------------------------

cp "$SCRIPT_DIR/debian/sit.desktop" "$PKGROOT/usr/share/applications/net.mystive.sit.desktop"

ICON_SRC="$SCRIPT_DIR/debian/$ICON_NAME.svg"
if [ ! -f "$ICON_SRC" ]; then
    echo "Error: expected icon at $ICON_SRC (not found)." >&2
    exit 1
fi
cp "$ICON_SRC" "$PKGROOT/usr/share/icons/hicolor/scalable/apps/$ICON_NAME.svg"

# -- permissions ------------------------------------------------
# Bulk defaults first (directories 755, files 644), then explicitly
# re-mark the specific files that need to be executable -- doing this
# in the opposite order would have the bulk file pass silently
# overwrite the executable bit right back off.

find "$PKGROOT" -type d -exec chmod 755 {} +
find "$PKGROOT" -type f -exec chmod 644 {} +
chmod 755 "$PKGROOT/DEBIAN/postinst" "$PKGROOT/usr/bin/sit"

# -- build ------------------------------------------------

dpkg-deb --build --root-owner-group "$PKGROOT" "$DEB_FILE"

echo
echo "Built: $DEB_FILE"
echo "Install with:  sudo apt install $DEB_FILE"
echo "Run with:      sit"
