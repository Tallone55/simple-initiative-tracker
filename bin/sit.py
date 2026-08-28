import sys

import gi

gi.require_version("Gtk", "4.0")

from application import Application


# Main process loop
if __name__ == "__main__":
    app = Application()
    try:
        sys.exit(app.run(sys.argv))
    except KeyboardInterrupt:
        print("Caught KeyboardInterrupt, signal 130")
        sys.exit(130)  # standard exit code for SIGINT
