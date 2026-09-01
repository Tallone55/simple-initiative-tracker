"""Remembers the last CSV file opened/saved, so the app can reopen it
automatically on the next launch. Stored as a plain-text file in the
OS temp directory -- a fixed location shared across users on a
multi-user machine, which is a non-issue on a typical single-user
desktop."""

import tempfile
from pathlib import Path

CACHE_FILE_NAME = ".sit_last_file.txt"


def cache_path() -> Path:
    return Path(tempfile.gettempdir()) / CACHE_FILE_NAME


def read_last_file_path():
    """Returns the cached path, or None if there's no cache file, it's
    empty, or it can't be read."""
    try:
        text = cache_path().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def write_last_file_path(csv_path):
    """Best-effort write -- errors are swallowed so a read-only temp
    dir doesn't interrupt the export/import the user actually asked
    for."""
    try:
        cache_path().write_text(str(csv_path), encoding="utf-8")
    except OSError:
        pass
