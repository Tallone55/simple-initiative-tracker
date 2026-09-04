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
source "$COMMON_DIR/version.sh"

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

sed "s/^Version:.*/Version: $VERSION/" "$SCRIPT_DIR/debian/control" > "$PKGROOT/DEBIAN/control"
cp "$SCRIPT_DIR/debian/postinst" "$PKGROOT/DEBIAN/postinst"

# -- application source ------------------------------------------------

cp "$PROJECT_ROOT"/bin/*.py "$PKGROOT/usr/lib/$PKG_NAME/bin/"
cp "$PROJECT_ROOT"/ui/*.ui "$PKGROOT/usr/lib/$PKG_NAME/ui/"

# -- launcher ------------------------------------------------

cat > "$PKGROOT/usr/bin/$EXECUTABLE_NAME" << LAUNCHER
#!/bin/sh
exec python3 /usr/lib/$PKG_NAME/bin/sit.py "\$@"
LAUNCHER

# -- desktop entry + icon ------------------------------------------------

cp "$SCRIPT_DIR/debian/sit.desktop" "$PKGROOT/usr/share/applications/$BUNDLE_ID.desktop"

ICON_SRC="$SCRIPT_DIR/debian/$BUNDLE_ID.svg"
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
