#!/usr/bin/env bash
# Builds a .deb package for Simple Initiative Tracker.
#
# Run from anywhere:
#     ./packaging/build_deb.sh
#
# Output: packaging/dist/initiative-tracker_<version>_all.deb

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMMON_DIR="$SCRIPT_DIR/common"

source "$COMMON_DIR/app_metadata.sh"
source "$COMMON_DIR/project_metadata.sh"

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
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0 (>= 4.10)
Maintainer: $MAINTAINER ($MAINTAINER_EMAIL)
Description: $APP_NAME
 $DESCRIPTION
 Tracks creature hitpoints, armor class, and turn order, with support
 for dice-notation and arithmetic expressions, CSV import/export, and
 undo/redo. Supports some (hacked-together) Cinnamon theming.
CONTROL

cat > "$PKGROOT/DEBIAN/postinst" << 'POSTINST'
#!/bin/sh
set -e

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi

exit 0
POSTINST

# -- application source ------------------------------------------------

cp "$PROJECT_ROOT"/bin/*.py "$PKGROOT/usr/lib/$PKG_NAME/bin/"
cp "$PROJECT_ROOT"/ui/*.ui "$PKGROOT/usr/lib/$PKG_NAME/ui/"

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
Exec=$EXECUTABLE_NAME
Icon=$BUNDLE_ID
Categories=Game;Utility;
Terminal=false
StartupNotify=true
DESKTOP

ICON_SRC="$SCRIPT_DIR/$BUNDLE_ID.svg"
if [ ! -f "$ICON_SRC" ]; then
    echo "Error: expected icon at $ICON_SRC (not found)." >&2
    exit 1
fi
cp "$ICON_SRC" "$PKGROOT/usr/share/icons/hicolor/scalable/apps/$BUNDLE_ID.svg"

# -- permissions ------------------------------------------------

find "$PKGROOT" -type d -exec chmod 755 {} +
find "$PKGROOT" -type f -exec chmod 644 {} +
chmod 755 "$PKGROOT/DEBIAN/postinst" "$PKGROOT/usr/bin/$EXECUTABLE_NAME"

# -- build ------------------------------------------------

dpkg-deb --build --root-owner-group "$PKGROOT" "$DEB_FILE"

echo
echo "Built: $DEB_FILE"
echo "Install with:  sudo apt install $DEB_FILE"
echo "Run with:      $EXECUTABLE_NAME"
