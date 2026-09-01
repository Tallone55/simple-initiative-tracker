import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")  # matches the system theme (see cinnamon_theme.py)

from application import Application


if __name__ == "__main__":
    app = Application()
    try:
        sys.exit(app.run(sys.argv))
    except KeyboardInterrupt:
        print("Caught KeyboardInterrupt, signal 130")
        sys.exit(130)
