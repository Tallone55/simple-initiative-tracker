"""Shared app identity/version metadata for use at runtime (About
dialog). Python counterpart to packaging/common/app_metadata.sh and
project_metadata.sh, which the build scripts use instead.

Reads version/maintainer/repository from pyproject.toml when it's
actually present -- true when running from source, since pyproject.
toml sits right alongside bin/'s own parent directory there. Packaged
builds don't ship pyproject.toml at all (deliberately: shipping a
whole extra file and parsing TOML at runtime just to read four
strings is more machinery than the problem needs), so that read
always fails for them -- but every build script now stamps the
_FALLBACK_* constants below with the real values via sed, as a build
step, before packaging bin/ up. That stamping is what makes the
fallback path actually correct for a packaged build rather than a
guess frozen at whatever this file happened to say when it was
written -- confirmed necessary the hard way, when the fallback
version drifted several point releases stale across builds because
nothing was updating it at build time yet."""

from pathlib import Path

APP_NAME = "Simple Initiative Tracker"

_FALLBACK_VERSION = "1.0.0rc10"
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
