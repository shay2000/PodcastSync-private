"""ffmpeg discovery for Docker and dev environments."""

from __future__ import annotations

import os
import shutil

_FFMPEG_SEARCH_PATHS = ["/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"]


def find_ffmpeg() -> str | None:
    """Locate the ffmpeg binary (required by yt-dlp for MP3 extraction)."""
    # Explicit override wins (e.g. a custom bind mount in Docker).
    override = os.getenv("PODCASTSYNC_FFMPEG", "").strip()
    if override and os.path.isfile(override) and os.access(override, os.X_OK):
        return override
    path = shutil.which("ffmpeg")
    if path:
        return path
    for candidate in _FFMPEG_SEARCH_PATHS:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None
