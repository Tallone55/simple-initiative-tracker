# Resolves the single source of truth for the app's version --
# pyproject.toml's [project] version -- so packaging/debian/control,
# the Windows installer, the macOS bundle, and the Linux portable
# archive can never drift out of sync from each other (or from
# pyproject.toml itself) the way debian/control's own hardcoded
# "Version:" field once did.
#
# Meant to be sourced, not executed: `source "$COMMON_DIR/version.sh"`
# after PROJECT_ROOT is already set. Defines $VERSION.

VERSION="$(grep -m1 -oP '^version\s*=\s*"\K[^"]+' "$PROJECT_ROOT/pyproject.toml")"

if [ -z "$VERSION" ]; then
    echo "Error: could not read [project] version from $PROJECT_ROOT/pyproject.toml" >&2
    exit 1
fi
