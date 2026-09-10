"""Shared app identity/version metadata for use at runtime (About
dialog). Python counterpart to packaging/common/app_metadata.sh and
project_metadata.sh, which the build scripts use instead.

Reads version/maintainer/repository/version-date from pyproject.toml
when it's actually present -- true when running from source, since
pyproject.toml sits right alongside bin/'s own parent directory there.
Packaged builds don't ship pyproject.toml at all (deliberately:
shipping a whole extra file and parsing TOML at runtime just to read a
few strings is more machinery than the problem needs), so that read
always fails for them -- but every build script now stamps the
_FALLBACK_* constants below with the real values via sed, as a build
step, before packaging bin/ up. That stamping is what makes the
fallback path actually correct for a packaged build rather than a
guess frozen at whatever this file happened to say when it was
written -- confirmed necessary the hard way, when the fallback
version drifted several point releases stale across builds because
nothing was updating it at build time yet."""

from datetime import date
from pathlib import Path

APP_NAME = "Simple Initiative Tracker"

_FALLBACK_VERSION = "1.0.0rc10"
_FALLBACK_MAINTAINER = "Thomas Hall"
_FALLBACK_MAINTAINER_EMAIL = "hall.thomas.010@gmail.com"
_FALLBACK_REPO_URL = "https://github.com/Tallone55/simple-initiative-tracker"
_FALLBACK_VERSION_DATE = "2026-01-01"

_PYPROJECT_PATH = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _load_pyproject_project_table():
    try:
        import tomllib
        with open(_PYPROJECT_PATH, "rb") as f:
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


def _load_version_date():
    """YYYY-MM-DD the version above was last changed. Read from
    pyproject.toml's own filesystem mtime when running from source
    (true whenever _project above was actually loaded, since that
    only succeeds if the same file was readable) -- the simplest
    thing that's actually correct there, and consistent with this
    file's own no-external-tool-dependency approach elsewhere (no
    shelling out to git just to show a date in the About dialog).
    _FALLBACK_VERSION_DATE, like every other _FALLBACK_* constant, is
    what a packaged build actually uses instead, stamped at build
    time -- there computed from `git log`, not mtime, since a build
    machine's own checkout step commonly resets every file's mtime to
    the checkout time rather than preserving when it was actually last
    committed (see project_metadata.sh's own comment on this)."""
    if not _project:
        return _FALLBACK_VERSION_DATE
    try:
        return date.fromtimestamp(_PYPROJECT_PATH.stat().st_mtime).isoformat()
    except OSError:
        return _FALLBACK_VERSION_DATE


VERSION_DATE = _load_version_date()
