"""Single source of truth for the app version: the VERSION file at the repo root."""
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _read_version() -> str:
    for path in (os.path.join(_HERE, "..", "VERSION"), "/app/VERSION"):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            continue
    return "unknown"


__version__ = _read_version()
