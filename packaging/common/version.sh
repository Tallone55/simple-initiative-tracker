# Resolves the single source of truth for the app's version --
# pyproject.toml's [project] version -- so packaging/debian/control,
# the Windows installer, the macOS bundle, and the Linux portable
# archive can never drift out of sync from each other (or from
# pyproject.toml itself) the way debian/control's own hardcoded
# "Version:" field once did.
#
# Meant to be sourced, not executed: `source "$COMMON_DIR/version.sh"`
# after PROJECT_ROOT is already set. Defines $VERSION.
#
# Uses sed with a plain POSIX basic-regex capture group (portable
# across GNU sed on Linux and BSD sed on macOS) rather than grep -P:
# -P is a GNU extension BSD grep doesn't support at all, and macOS
# ships BSD grep as /usr/bin/grep with no GNU grep available unless
# a user separately installs one -- confirmed the hard way, as this
# broke build_macos.sh's very first line on a real macOS runner.

VERSION="$(sed -n 's/^version[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$PROJECT_ROOT/pyproject.toml" | head -n1)"

if [ -z "$VERSION" ]; then
    echo "Error: could not read [project] version from $PROJECT_ROOT/pyproject.toml" >&2
    exit 1
fi
