"""Remembers the last CSV file opened/saved, so the app can reopen it
automatically on the next launch.

Stored as a single plain-text file. On POSIX systems (Linux, macOS,
etc.) this lives in /tmp -- a fixed, predictable location regardless of
where the app happens to be launched from. Non-POSIX systems (Windows)
fall back to the current working directory, since /tmp isn't a
meaningful path there.

Worth knowing: /tmp is shared across every user on the system, not
scoped per-user. On a single-user desktop this is a non-issue; on a
shared multi-user machine, two accounts running this app would clobber
each other's "last file" cache.
"""

import os
from pathlib import Path

CACHE_FILE_NAME = ".sit_last_file.txt"


def cache_path() -> Path:
    """Where the cache file lives -- see module docstring for the
    POSIX vs. non-POSIX distinction."""
    if os.name == "posix":
        return Path("/tmp") / CACHE_FILE_NAME
    return Path.cwd() / CACHE_FILE_NAME


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
