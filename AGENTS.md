# AGENTS.md

Guidance for AI agents and developers working in the PodcastSync repository. Read `README.md` (user-facing features) and `HANDOFF.md` (release/ops state) alongside this file.

## What this project is

PodcastSync is a self-hosted **Docker/Linux server** that turns YouTube channels/playlists into podcast RSS feeds. A Python backend (FastAPI) monitors sources, downloads audio as MP3 via yt-dlp, and serves podcast RSS + audio over HTTP on port 8642. The reference deployment is an Ubuntu VPS: the dashboard binds to loopback or a private Tailscale address; an optional Caddy `public` profile exposes only `/feed/*` and `/audio/*` over HTTPS. The former macOS menu bar app and PyInstaller/DMG packaging have been removed.

Key product facts:
- One RSS feed per source at `/feed/{source_id}.xml`; audio at `/audio/{source_id}/{video_id}.mp3`.
- The backend has no user accounts or API auth. The Docker `public` profile
  keeps the admin surface private and exposes only feed/audio paths through
  Caddy; never publish port 8642 directly to the internet.
- Without a YouTube Data API key it falls back to YouTube public RSS (only ~15 most-recent videos, no durations). API key enables handle resolution, full history, durations.
- In the container, audio files live under `/data/PodcastMirror/<sanitized-source-name>/<video_id>.mp3` and the SQLite DB at `/data/podcastsync.db` (both in the `podcastsync-data` volume). On a dev machine they default to `~/PodcastMirror` and `~/.podcastsync/podcastsync.db`.

## Repository layout

```
backend/                  Python FastAPI backend (the real product logic)
  main.py                 Composition root: FastAPI app, lifespan, router/static mounts
  config.py               Settings dataclass (env vars + DB-stored overrides)
  database.py             Raw sqlite3 access + migration runner
  models.py               Pydantic request/response models
  scheduler.py            APScheduler wrapper
  rss_generator.py        Podcast RSS/XML generation (feedgen)
  _resources.py           Dev resource path resolution
  migrations/*.sql        Numbered schema migrations (001, 002, 003)
  routes/                 Thin HTTP layer. api.py aggregates /api/*; feeds.py & audio.py
                          are mounted at root in main.py (NOT under /api)
  services/               Business logic: sources, sync, paths, cookies
  fetcher/                YouTube metadata: url_parser, rss_fetcher, api_fetcher, orchestrator
  downloader/             DownloadManager (yt-dlp), ffmpeg discovery, MP3 artwork
  static/                 Vanilla-JS web UI + CSS (no framework, no bundler)
  test_fetch.py           Manual CLI harness — NOT a pytest module (excluded by testpaths)
tests/                    Hermetic offline characterization suite (pytest + httpx)
Dockerfile                Runtime image (python:3.12-slim + ffmpeg + Node 22 for yt-dlp-ejs)
docker-compose.yml        Private-by-default compose (loopback/Tailscale bind)
docker-compose.cookies.yml Optional read-only cookie-file mount
deploy/linux/install.sh   One-command Linux installer (curl | bash)
deploy/oracle/install.sh  Domain-based Oracle VPS installer (public profile)
deploy/caddy/             Caddyfile for the host-level and Docker public profiles
scripts/                  dev.sh (dev server), check_version.sh (release guard)
docs/                     Deployment runbooks and implementation history
.github/workflows/        ci.yml (lint+tests), build-release.yml (Docker image → GHCR + release)
```

## Commands

Run from repo root. The repo path contains spaces; always quote it.

```bash
# Dev server (backend + web UI at http://127.0.0.1:8642, --reload enabled)
# Requires ffmpeg on PATH (apt install ffmpeg / brew install ffmpeg)
./scripts/dev.sh

# Manual fetcher CLI (requires a real YouTube URL; hits live network/DB)
./scripts/dev.sh test-fetch "<youtube-url>"     # same as: python -m backend.test_fetch <url>

# Tests (need a venv with Python >= 3.10; system python is 3.9 — create one first)
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"
python -m pytest tests/ -q
ruff check backend tests && ruff format --check backend tests

# Docker (the shipped artifact)
docker compose up -d            # runs ghcr.io/shay2000/podcastsync:latest
docker compose up -d --build    # build locally from the repo instead
```

### Environment variables

Backend `Settings` (env-first, then DB-stored overrides for the starred ones):
- `YOUTUBE_API_KEY` — Google Data API v3 key (optional; enables full fetcher)
- `PODCASTSYNC_STORAGE` — default `~/PodcastMirror` (`/data/PodcastMirror` in the image)
- `PODCASTSYNC_DB` — default `~/.podcastsync/podcastsync.db` (`/data/podcastsync.db` in the image)
- `PODCASTSYNC_PORT` — default `8642`
- `PODCASTSYNC_POLL_INTERVAL` — minutes, default `30`
- `PODCASTSYNC_MAX_DOWNLOADS` — default `2`
- `PODCASTSYNC_FFMPEG` — explicit ffmpeg path override; else discovered from PATH
- `PODCASTSYNC_PUBLIC_URL` — origin used in generated feed/audio URLs (required in Compose)

DB-stored settings that override env at startup (via `settings` table): `youtube_api_key`, `poll_interval_minutes`, `server_port`, `storage_path`, `max_concurrent_downloads`, `cookies_from_browser`, `cookies_file_path`.

## Backend architecture

### Startup flow (`backend/main.py`)

`lifespan()` builds everything and hangs it off `app.state`: `settings`, `db`, `orchestrator`, `download_manager`, `scheduler`. Routes pull collaborators from `request.app.state.*` per request — **never** from module globals or a DI container. This indirection is a hard contract: the test suite stubs fetcher/downloader by replacing `app.state.orchestrator` / `app.state.download_manager` after lifespan startup (see Testing). Preserve it when refactoring.

Router mounting order matters: `/api` aggregate, feeds, audio, then **StaticFiles at `/` LAST** (it would shadow later routes).

### Layering

- `routes/` — HTTP only. Handlers are `async def`, no `Depends()`; deps come from `request.app.state`. `backend/routes/api.py` owns `prefix="/api"` and includes sources, videos, sync, status, settings, cookies. `feeds.py` and `audio.py` are included directly in `main.py` (no `/api` prefix) because they serve XML/files.
- `services/` — orchestration + DTOs. `create_source` (URL parse → resolve handles → enrich channel metadata → insert), `sync_source`/`sync_all_sources` (fetch metadata → dedupe insert videos → process pending downloads), `paths` (sanitize filename, output dirs, audio path resolution), `cookies` (yt-dlp cookie probing/testing).
- `fetcher/` — `url_parser` (channel/@handle/custom/user/playlist shapes; single `/watch` and `/shorts` deliberately rejected), `rss_fetcher` (public feeds, ~15 items, no durations), `api_fetcher` (YouTube Data API, paginated, batch durations, resolves handles), `orchestrator` (API first, falls back to RSS on any failure incl. quota; returns `[]` if both fail).
- `downloader/` — `DownloadManager` runs yt-dlp in a thread (`run_in_executor`), `bestaudio` → MP3 192k via `FFmpegExtractAudio`, file named `<video_id>.mp3` in the per-source dir, optional channel-icon embedding (mutagen APIC), cooperative cancel, `asyncio.Semaphore` concurrency, rolling delete of old episodes.

### Database

Raw `sqlite3` (no ORM), single shared connection (`check_same_thread=False`, WAL). Migration runner applies `migrations/NNN_*.sql` in lexical order, each inside an explicit transaction with its schema-version bump; version stored in `settings` table (`schema_version`). Tables: `sources`, `videos` (`UNIQUE(source_id, video_id)`), `settings` (key/value). All helpers commit per statement. `update_source`/`update_video_status` validate field names against allowlists (`SOURCE_UPDATE_COLUMNS`/`VIDEO_UPDATE_COLUMNS`) before building SQL. Video `download_status` ∈ pending|downloading|completed|failed|skipped|deleted.

### API surface

```
GET/POST   /api/sources                    POST returns 201
GET/PATCH/DELETE /api/sources/{source_id}  DELETE 204; PATCH partial via model_dump(exclude_unset=True)
GET        /api/sources/{source_id}/videos             newest first, DB row shape (no file_path)
DELETE     /api/sources/{source_id}/videos/{video_db_id}        → status 'skipped' (204)
DELETE     /api/sources/{source_id}/videos/{video_db_id}/file   removes file + sets 'deleted' (204)
POST       /api/sources/{source_id}/videos/{video_db_id}/requeue → 'pending' (204)
POST       /api/sources/{source_id}/sync    202 — background task
POST       /api/sync-all                    202
POST       /api/downloads/cancel-all
GET        /api/downloads/progress          keyed by video DB id
GET        /api/status
GET/PATCH  /api/settings                    GET never returns the API key, only youtube_api_key_set
GET        /api/cookies/detect
POST       /api/cookies/test
GET        /feed/{source_id}.xml            RSS (completed videos only), Cache-Control max-age=300
GET        /feeds                           feed metadata list
GET        /audio/{source_id}/{filename}    path-traversal guarded (403 outside storage root)
GET        /                                static web UI
```

Route conventions: `source_id` = DB row id; `video_id` = YouTube string; `video_db_id` = DB row id of a video; `{filename}` = `<youtube_id>.mp3`. Errors: `HTTPException(404/403/400)` with `detail`, no global handler. Success JSON is ad-hoc dicts; typed routes set `response_model`.

## Frontend (backend/static)

Vanilla ES modules, no framework/bundler/package.json. `index.html` loads
`js/main.js?v=12` and `/css/main.css?v=11`; all JS/CSS cache-busting is
**manual** — bump it when changing assets.

- `js/store.js` — single mutable state singleton + subscribe/notify pub/sub.
- `js/api.js` — `api(method, path, body)` fetch wrapper; throws `Error(error.detail)` on non-2xx.
- `js/poll.js` — polling timers (status/sources every 5s, download progress every 1s), reload helpers.
- `js/render/*` — pure innerHTML template-literal renderers.
- `js/actions/*` — imperative handlers for data-action dispatch; `js/ui/*` — modals, toasts.
- `js/main.js` — composition root: one delegated `click` listener switches on `event.target.closest("[data-action]")`; ids via `data-source-id` / `data-video-id`; a delegated `change` listener handles enabled toggles. New interactive elements must follow the `data-action` convention.

CSS: `css/main.css` is a `@import` manifest. `css/overrides.css` retains the
legacy `style.css` compatibility layer, while newer dashboard-only surfaces
live in `css/components/dashboard.css` and load last. If an older visual
change "does nothing", the rule you need probably lives in `style.css`.
Frontend text and attribute values use `esc()`; preserve that rule whenever
adding user-controlled strings to HTML templates.

## Docker / VPS deployment

The shipped artifact is the Docker image `ghcr.io/shay2000/podcastsync`
(built by CI on `v*` tags, linux/amd64 + linux/arm64). `docker-compose.yml`
defaults to that image and binds `127.0.0.1:8642` (override with
`PODCASTSYNC_BIND_IP`, e.g. a Tailscale address).

When asked to deploy PodcastSync:

- **Private Tailscale-only deployment** (dashboard at
  `http://<vps-tailscale-ip>:8642` from a Mac on the same Tailnet): paste
  `docs/HERMES_VPS_ONBOARD_PROMPT.md` into the agent as its first message. It
  handles the whole install gate-by-gate and asks the owner for facts as
  needed. The quick path is `deploy/linux/install.sh --bind-ip <ts-ip>`.
- **Public-domain deployment** (HTTPS feeds via Caddy): read
  `docs/ORACLE_VPS_HANDOFF.md` before acting, or use
  `deploy/oracle/install.sh --domain <domain>`. Verify DNS and cloud ingress
  before changing services.

Agent deployment rules:

- Keep `.env`, the SQLite volume, and cookie files out of git; preserve an
  existing `.env` and back up the `podcastsync-data` volume before updates.
- Do not expose 8642 beyond loopback/a private Tailscale address, expose
  `/api` through Caddy, or install unreviewed remote scripts.
- A YouTube Data API key is for metadata and history, not YouTube sign-in. A
  headless Docker deployment needs a read-only Netscape cookie file only when a
  download actually requires authentication.

## Packaging

The only packaging path is the Docker image:

- `Dockerfile` — python:3.12-slim, apt installs only `ffmpeg` +
  `ca-certificates`, `pip install -r requirements.txt`, copies only `backend/`,
  runs as non-root `podcastsync` (uid 10001), healthcheck via Python urllib,
  CMD `python -m uvicorn backend.main:app --host 0.0.0.0 --port 8642
  --proxy-headers --forwarded-allow-ips 127.0.0.1`. A Node 22 binary is copied
  in for yt-dlp-ejs (YouTube extraction needs a JS runtime).
- CI (`.github/workflows/build-release.yml`) runs on `ubuntu-latest`: lint,
  tests, buildx multi-arch build → GHCR, container smoke test, and attaches
  `install.sh` + a compose tarball to the GitHub release.
- Version is single-sourced from `pyproject.toml`; release tags must match
  (`scripts/check_version.sh`). `tests/test_docker_contract.py` and
  `tests/test_release_contract.py` pin the Dockerfile/compose/workflow
  contracts — update them in lockstep with any packaging change.

## Code conventions

- Imports: absolute `backend.`-prefixed everywhere (no relative imports). `from __future__ import annotations` first statement in nearly every module.
- Heavy deps are imported lazily inside functions to keep startup fast: `yt_dlp` (~60s import), `googleapiclient`, `feedgen`/lxml. Do not move them to module scope.
- DB rows are `sqlite3.Row`; services convert to DTO dicts (`*_dto` naming) validated by Pydantic at the route boundary. Internally collaborators are typed loosely (`Any`) for testability.
- Error handling: catch narrowly + `logger.exception` where tracebacks are useful; background sync failures are logged and swallowed per-source; routes raise HTTPException. Non-fatal enrichment (channel icon, uploads playlist) is intentionally fail-open.
- Python floor is 3.10 (uses modern builtin generics). Style follows the existing flat snake_case modules; ruff (check + format) is enforced in CI — run both locally.

## Testing

Hermetic offline characterization suite. Run: `python -m pytest tests/ -q` (config in `pyproject.toml`: `asyncio_mode=auto`, `testpaths=["tests"]`).

- `tests/conftest.py` sets `PODCASTSYNC_DB`/`PODCASTSYNC_STORAGE` to per-test `tmp_path`, `PODCASTSYNC_POLL_INTERVAL=1440`, `YOUTUBE_API_KEY=""`, then imports `backend.main`.
- httpx `AsyncClient` over `ASGITransport` (lifespan NOT auto-run): the `api` fixture drives `app.router.lifespan_context(app)` for real migrations + startup, then **swaps `app.state.orchestrator`/`app.state.download_manager` for `StubOrchestrator`/`StubDownloadManager`** that record calls. This works only because routes read `request.app.state` per request.
- New tests must follow the same pattern — never hit the network, never construct real fetchers/downloaders, fake MP3 bytes on disk via the `seeded` fixture, keep fixtures function-scoped.
- If you change call signatures of `fetch_videos`/`resolve_to_channel_id`/`process_pending_downloads`/`cancel_all`/etc., update the stubs in lockstep (tests assert recorded call tuples).
- `tests/test_docker_contract.py` and `tests/test_release_contract.py` read packaging files as static text — extend them when changing the Dockerfile, compose files, install scripts, or workflows.

## Known gotchas & risks

- **Rolling delete (`max_keep_episodes`) looks inverted**: `get_overflow_completed_videos` orders by `publish_date ASC … OFFSET max_keep`, and downloads proceed oldest-first, so a keep-N source may delete freshly-downloaded episodes and keep the oldest N. Verify semantics before relying on this feature (untested).
- Migration 003 does a full `videos` table rebuild that depends on exact column order. The runner now wraps each migration in a transaction, but a bad migration file still fails startup loudly.
- `Settings.load_from_db` parses DB values with bare `int()`/`Path()` — a corrupt `settings` row can crash startup. `Settings.from_env()` also has eager side effects (mkdir of `~/.podcastsync`).
- Shared single sqlite connection + synchronous DB calls inside async handlers is fine under single-worker uvicorn but blocks the event loop on heavy queries; do not add multi-worker/multi-thread concurrency without revisiting.
- Keep `requirements.txt` and `pyproject.toml` dependency floors aligned (pinned by `test_release_contract.py`).
- Feed `guid` is a bare YouTube ID (not a URL) and `base_url` in settings (LAN IP) differs from the request-derived base used for feed/audio URLs; always set `PODCASTSYNC_PUBLIC_URL` in Docker so enclosure URLs are correct.
- Overcast is an unsupported podcast client (needs the public HTTPS profile); Apple Podcasts/Downcast are the reference clients.
- No auth on any HTTP endpoint (private network only). Audio route's only guard is path containment. The dashboard bind must stay loopback/Tailscale.
- Frontend: legacy `style.css` shadows the modular CSS (above); no frontend tests; cache-buster `?v=` must be bumped; keep `data-action` names in sync between HTML/JS.
