"""Resource path resolution for files shipped inside the backend package.

Files like `backend/static/` and `backend/migrations/` live next to the
`backend` package on disk (dev checkout and the Docker image alike), so
`Path(__file__).parent` is always correct.
"""

from __future__ import annotations

from pathlib import Path


def resource_path(relative: str) -> Path:
    """Return the absolute path to a packaged resource (e.g. 'static', 'migrations').

    `relative` is the path *within* the backend package (e.g. 'static').
    """
    return Path(__file__).resolve().parent / relative
