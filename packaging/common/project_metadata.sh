# Resolves the app's version, package name, description, maintainer,
# and repository URL from pyproject.toml's [project] table -- the
# single source of truth, so packaging output can't drift from it or
# from each other. Meant to be sourced after PROJECT_ROOT is set.
# Defines $VERSION, $PKG_NAME, $DESCRIPTION, $MAINTAINER,
# $MAINTAINER_EMAIL, $REPO_URL.

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
    "repo_url": (project.get("urls") or {}).get("Repository", ""),
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
REPO_URL="$(_read_pyproject_field "$PYPROJECT_TOML" repo_url)"

if [ -z "$VERSION" ]; then
    echo "Error: could not read [project] version from $PYPROJECT_TOML" >&2
    exit 1
fi

# Stamps VERSION/MAINTAINER/MAINTAINER_EMAIL/REPO_URL as literal
# constants into a build's own copy of bin/app_metadata.py, in place
# of that file's own _FALLBACK_* defaults -- so a packaged build
# doesn't need to ship pyproject.toml at all just to know its own
# version, and isn't relying on those defaults having been kept
# up to date by hand (they weren't: the fallback version had drifted
# several point releases behind before this was added, since nothing
# was resolving it a build-time). Call with the path to the *copied*
# app_metadata.py inside a build's own output tree, after that copy
# has been made. | as the sed delimiter, not the more common /, since
# REPO_URL is a URL and would otherwise conflict with it.
_stamp_app_metadata() {
    local target="$1"
    # -i.bak, not bare -i: BSD sed (macOS) requires an explicit
    # backup-suffix argument to -i, while GNU sed (Linux) treats a
    # missing one as "no backup" -- ".bak" satisfies both, and is
    # removed immediately after so it doesn't end up in any build's
    # own output.
    sed -i.bak \
        -e "s|_FALLBACK_VERSION = \".*\"|_FALLBACK_VERSION = \"$VERSION\"|" \
        -e "s|_FALLBACK_MAINTAINER = \".*\"|_FALLBACK_MAINTAINER = \"$MAINTAINER\"|" \
        -e "s|_FALLBACK_MAINTAINER_EMAIL = \".*\"|_FALLBACK_MAINTAINER_EMAIL = \"$MAINTAINER_EMAIL\"|" \
        -e "s|_FALLBACK_REPO_URL = \".*\"|_FALLBACK_REPO_URL = \"$REPO_URL\"|" \
        "$target"
    rm -f "$target.bak"
}
