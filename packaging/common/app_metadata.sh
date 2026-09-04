# Packaging-specific identity constants with no pyproject.toml
# equivalent (PKG_NAME comes from there instead -- see
# project_metadata.sh). Meant to be sourced after PROJECT_ROOT is
# set.

APP_NAME="Simple Initiative Tracker"       # display name
EXECUTABLE_NAME="sit"                      # launcher command name
BUNDLE_ID="net.mystive.sit"                # reverse-DNS id: desktop file, macOS bundle id, Windows AppUserModelID
