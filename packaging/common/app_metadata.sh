# Shared app identity constants, so the four platform build scripts
# can't drift from each other on naming the way debian/control's
# version once drifted from pyproject.toml.
#
# Meant to be sourced, not executed, after PROJECT_ROOT is set.

APP_NAME="Simple Initiative Tracker"       # display name
PKG_NAME="initiative-tracker"              # filesystem-safe package/dir name
EXECUTABLE_NAME="sit"                      # launcher command name
BUNDLE_ID="net.mystive.sit"                # reverse-DNS id: desktop file, macOS bundle id, Windows AppUserModelID
