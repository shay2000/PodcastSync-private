# PodcastSync backend container image (Phase 6 V3).
#
# Runs the FastAPI backend (backend.main:app) as an unprivileged user.
# ffmpeg is required by yt-dlp for MP3 extraction; ca-certificates keeps HTTPS
# working. Nothing else is apt-installed on purpose, and the container
# healthcheck uses the Python standard library so no extra tool is required.
# Proxy headers (X-Forwarded-*) are honoured only when they come from
# 127.0.0.1. In the shipped host-level Caddy topology, Docker NAT changes the
# peer address, so PODCASTSYNC_PUBLIC_URL is required for public feed links.
# Do not widen this allowlist without a deliberately trusted private network.

FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
# requirements.txt also serves the macOS PyInstaller build. Keep that
# build-only dependency out of the runtime image.
RUN grep -viE '^pyinstaller([<=>!~]|$)' requirements.txt \
    > /tmp/requirements-runtime.txt \
    && pip install --no-cache-dir -r /tmp/requirements-runtime.txt \
    && rm /tmp/requirements-runtime.txt

COPY backend ./backend

ENV PODCASTSYNC_DB=/data/podcastsync.db \
    PODCASTSYNC_STORAGE=/data/PodcastMirror \
    PODCASTSYNC_PORT=8642

# Non-root runtime user. /data holds the SQLite DB and the PodcastMirror
# audio library and is writable by the app user.
RUN useradd --create-home --uid 10001 podcastsync \
    && mkdir -p /data \
    && chown -R podcastsync:podcastsync /data /app

USER podcastsync

EXPOSE 8642

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8642/api/status', timeout=3).status==200 else 1)"

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8642", "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"]
