# HANDOFF.md

## Overview
PodcastSync is a self-hosted server that turns YouTube channels and playlists
into podcast RSS feeds. The deployment target is a Linux VPS running Docker,
with the dashboard reached privately over Tailscale (or an SSH tunnel); an
optional public Caddy profile exposes only HTTPS feed/audio paths.

It has:

- a Python backend built with FastAPI (the whole product)
- a Docker image published to GHCR on every release tag
- a one-command Linux install script for Docker hosts

Current packaged output:

- `ghcr.io/shay2000/podcastsync:<version>` (linux/amd64 + linux/arm64)
- release assets: `install.sh` + a tarball of the compose files

## Current state
Recent work completed:

- major frontend redesign (dashboard overview, per-source progress, feed details)
- Docker packaging hardened by contract tests (loopback-only publish, non-root
  user, Python healthcheck, no secrets in compose)
- optional Caddy `public` profile that publishes only `/feed/*` and `/audio/*`
- optional read-only cookie-file mount for yt-dlp sign-in downloads
- macOS menu bar app and PyInstaller/DMG packaging removed — the product is
  Docker-on-Linux only now
- release pipeline builds the image on GHCR and smoke-tests the container

## Stack
- Python 3.10+ (3.12 in the image)
- FastAPI + uvicorn
- yt-dlp (+ yt-dlp-ejs and a Node 22 runtime for YouTube extraction)
- feedgen, APScheduler, SQLite
- Docker + Compose; Caddy 2 for the optional public profile

## Key files
- `backend/main.py`: FastAPI entrypoint
- `backend/services/`: source creation, sync orchestration, cookie probing, and path helpers
- `backend/downloader/`: download manager, ffmpeg discovery, and MP3 artwork helpers
- `backend/routes/`: thin HTTP layer (`api.py` aggregates `/api/*`; feeds and audio mount at root)
- `backend/static/`: vanilla-JS web UI (no framework, no bundler)
- `Dockerfile` / `docker-compose.yml` / `docker-compose.cookies.yml`: container packaging
- `deploy/linux/install.sh`: one-command Linux installer (curl | bash)
- `deploy/caddy/Caddyfile.docker`: public HTTPS feed proxy for the `public` profile
- `deploy/oracle/install.sh`: domain-based Oracle VPS installer (public profile)
- `scripts/dev.sh`: local dev run
- `scripts/check_version.sh`: release tag ↔ pyproject version guard
- `.github/workflows/build-release.yml`: Docker image build + release publishing
- `docs/ORACLE_VPS_HANDOFF.md`: owner and coding-agent deployment runbook
- `docs/HERMES_VPS_ONBOARD_PROMPT.md`: Tailscale-only deployment prompt for coding agents

## Run locally (dev)
```bash
cd "<repo root>"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# ffmpeg must be on PATH (apt install ffmpeg / brew install ffmpeg)
./scripts/dev.sh
```

Then open http://127.0.0.1:8642

## Running tests

Install the optional development dependencies into the project environment, then run:

```bash
source venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest tests/ -q
ruff check backend tests && ruff format --check backend tests
```

The characterization suite is offline: it uses temporary SQLite/storage paths and
replaces the YouTube fetcher and download manager after application startup.

## Deployment

Private (Tailscale-only) — the default:

```bash
curl -fsSL https://raw.githubusercontent.com/shay2000/PodcastSync-private/main/deploy/linux/install.sh \
  | bash -s -- --bind-ip <tailscale-ipv4>
```

Dashboard: `http://<tailscale-ipv4>:8642`, reachable only from the Tailnet.
See `docs/HERMES_VPS_ONBOARD_PROMPT.md` for the full gate-by-gate runbook.

Public feeds (optional — needed only for cloud-based clients like Overcast):

```bash
cp .env.example .env
# Set PODCASTSYNC_DOMAIN and PODCASTSYNC_PUBLIC_URL in .env.
# The hostname can be an owned subdomain (podcast.example.com) or a free
# DuckDNS name (my-podcasts.duckdns.org) pointing at the VPS public IP —
# Caddy obtains HTTPS certificates for either automatically.
docker compose --profile public up -d
```

Read `docs/ORACLE_VPS_HANDOFF.md` before enabling the public profile (DNS,
Oracle VCN, HTTPS, cookies, maintenance).

## Release process

1. Bump `version` in `pyproject.toml`
2. Tag `vX.Y.Z` and push the tag
3. CI (`build-release.yml`) runs tests, builds and pushes
   `ghcr.io/shay2000/podcastsync` (version + latest tags), smoke-tests the
   container, and attaches `install.sh` + the compose tarball to the GitHub
   release
4. Servers update by re-running the install script (it pulls the new image
   and re-creates the container; data persists in the `podcastsync-data` volume)

## Known limitations
- Overcast requires the public HTTPS profile; Apple Podcasts and Downcast work
  with private/Tailscale URLs.
- A YouTube Data API key is not a YouTube sign-in; downloads that require an
  account need a Netscape-format cookie file.
- Without a YouTube API key, RSS fallback only exposes roughly the latest 15 videos.
- Podcast clients cache feeds aggressively.
- The server must be running for clients to fetch feeds and audio.
