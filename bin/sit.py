import sys

import gi

gi.require_version("Gtk", "4.0")
# libadwaita is a required dependency (see packaging/debian/control) --
# it's what makes the app's theming match the real, system-provided
# palette (including Linux Mint's patched build) rather than an
# approximation we'd otherwise have to maintain ourselves.
gi.require_version("Adw", "1")

from application import Application


# Main process loop
if __name__ == "__main__":
    app = Application()
    try:
        sys.exit(app.run(sys.argv))
    except KeyboardInterrupt:
        print("Caught KeyboardInterrupt, signal 130")
        sys.exit(130)  # standard exit code for SIGINT
