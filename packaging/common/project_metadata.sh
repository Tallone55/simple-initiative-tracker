# Resolves the app's version, package name, description, and
# maintainer from pyproject.toml's [project] table -- the single
# source of truth, so packaging output can't drift from it or from
# each other. Meant to be sourced after PROJECT_ROOT is set. Defines
# $VERSION, $PKG_NAME, $DESCRIPTION, $MAINTAINER, $MAINTAINER_EMAIL.

_read_pyproject_field() {
    python3 -c '
import sys, tomllib
with open(sys.argv[1], "rb") as f:
    project = tomllib.load(f).get("project", {})
authors = project.get("authors") or [{}]
fields = {
    "version": project.get("version", ""),
    "name": project.get("name", ""),
    "description": project.get("description", ""),
    "maintainer": authors[0].get("name", ""),
    "maintainer_email": authors[0].get("email", ""),
}
print(fields[sys.argv[2]])
' "$1" "$2"
}

PYPROJECT_TOML="$PROJECT_ROOT/pyproject.toml"
VERSION="$(_read_pyproject_field "$PYPROJECT_TOML" version)"
PKG_NAME="$(_read_pyproject_field "$PYPROJECT_TOML" name)"
DESCRIPTION="$(_read_pyproject_field "$PYPROJECT_TOML" description)"
MAINTAINER="$(_read_pyproject_field "$PYPROJECT_TOML" maintainer)"
MAINTAINER_EMAIL="$(_read_pyproject_field "$PYPROJECT_TOML" maintainer_email)"

if [ -z "$VERSION" ]; then
    echo "Error: could not read [project] version from $PYPROJECT_TOML" >&2
    exit 1
fi
