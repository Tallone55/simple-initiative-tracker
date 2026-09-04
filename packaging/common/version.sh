# Resolves the app's version from pyproject.toml's [project] version,
# the single source of truth. Meant to be sourced after PROJECT_ROOT
# is set. Defines $VERSION.
#
# sed, not grep -P: -P is a GNU extension BSD grep (macOS's default)
# doesn't support.

VERSION="$(sed -n 's/^version[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$PROJECT_ROOT/pyproject.toml" | head -n1)"

if [ -z "$VERSION" ]; then
    echo "Error: could not read [project] version from $PROJECT_ROOT/pyproject.toml" >&2
    exit 1
fi
