"""Remembers the last CSV file opened/saved, so the app can reopen it
on next launch. Stored as a plain-text file in the OS temp dir."""

import tempfile
from pathlib import Path

CACHE_FILE_NAME = ".sit_last_file.txt"


def cache_path() -> Path:
    return Path(tempfile.gettempdir()) / CACHE_FILE_NAME


def read_last_file_path():
    try:
        text = cache_path().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def write_last_file_path(csv_path):
    try:
        cache_path().write_text(str(csv_path), encoding="utf-8")
    except OSError:
        pass
