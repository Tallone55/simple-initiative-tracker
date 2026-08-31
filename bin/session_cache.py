"""Remembers the last CSV file opened/saved, so the app can reopen it
automatically on the next launch.

Stored as a single plain-text file in the OS's own temp directory
(tempfile.gettempdir() -- /tmp on Linux/macOS, %TEMP% on Windows), a
fixed, predictable location regardless of where the app happens to be
launched from. No manual per-platform branching needed: gettempdir()
already resolves correctly everywhere on its own.

Worth knowing: this directory is typically shared across every user on
the system, not scoped per-user. On a single-user desktop this is a
non-issue; on a shared multi-user machine, two accounts running this
app would clobber each other's "last file" cache.
"""

import tempfile
from pathlib import Path

CACHE_FILE_NAME = ".sit_last_file.txt"


def cache_path() -> Path:
    """Where the cache file lives -- see module docstring."""
    return Path(tempfile.gettempdir()) / CACHE_FILE_NAME


def read_last_file_path():
    """Returns the cached path as a string, or None if there's no cache
    file, it's empty, or it can't be read."""
    try:
        text = cache_path().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def write_last_file_path(csv_path):
    """Best-effort write -- a failure here (e.g. read-only working
    directory) shouldn't interrupt the export/import the user actually
    asked for, so errors are swallowed rather than raised."""
    try:
        cache_path().write_text(str(csv_path), encoding="utf-8")
    except OSError:
        pass
