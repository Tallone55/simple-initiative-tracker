"""Shared app identity/version metadata for use at runtime (About
dialog). Python counterpart to packaging/common/app_metadata.sh and
project_metadata.sh, which the build scripts use instead.

Reads version/maintainer/repository from pyproject.toml when
available (running from source); packaged/portable builds, which
don't ship pyproject.toml alongside bin/, fall back to the hardcoded
defaults below -- kept in sync with pyproject.toml by hand at
release time."""

from pathlib import Path

APP_NAME = "Simple Initiative Tracker"

_FALLBACK_VERSION = "1.0.0rc3"
_FALLBACK_MAINTAINER = "Thomas Hall"
_FALLBACK_MAINTAINER_EMAIL = "hall.thomas.010@gmail.com"
_FALLBACK_REPO_URL = "https://github.com/Tallone55/simple-initiative-tracker"


def _load_pyproject_project_table():
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        import tomllib
        with open(pyproject_path, "rb") as f:
            return tomllib.load(f).get("project", {})
    except (OSError, ValueError):
        return {}


_project = _load_pyproject_project_table()

VERSION = _project.get("version") or _FALLBACK_VERSION

_authors = _project.get("authors") or []
if _authors:
    MAINTAINER = _authors[0].get("name") or _FALLBACK_MAINTAINER
    MAINTAINER_EMAIL = _authors[0].get("email") or _FALLBACK_MAINTAINER_EMAIL
else:
    MAINTAINER = _FALLBACK_MAINTAINER
    MAINTAINER_EMAIL = _FALLBACK_MAINTAINER_EMAIL

REPO_URL = (_project.get("urls") or {}).get("Repository") or _FALLBACK_REPO_URL
