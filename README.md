# PodcastSync

![Platform](https://img.shields.io/badge/platform-Docker%20%2F%20Linux-2496ED?style=flat-square&logo=docker)
![License](https://img.shields.io/badge/license-MIT-166534?style=flat-square)
![Status](https://img.shields.io/badge/status-active-9a3412?style=flat-square)
![Release](https://img.shields.io/github/v/release/shay2000/PodcastSync-private)

Turn YouTube channels and playlists into self-hosted podcast feeds.

PodcastSync is a self-hosted server you run in Docker on a Linux VPS (or any
Docker host). It monitors YouTube sources, downloads audio as MP3, and serves
podcast RSS feeds. Designed for private access over [Tailscale](https://tailscale.com):
the dashboard is reachable only from your Tailnet, and podcast clients on your
devices subscribe to the feed URL. An optional public HTTPS mode (Caddy)
exposes only the feed and audio paths if you want Overcast or other
cloud-based podcast clients to reach it.

## Features

- **Add YouTube channels or playlists** — paste a URL, the app handles the rest
- **Automatic polling** — checks for new videos on a configurable schedule (default: every 30 minutes)
- **Audio-only downloads** — extracts audio as MP3 at 192kbps with embedded cover art
- **Podcast RSS feeds** — one feed per source, valid for any podcast client
- **Web UI** — manage sources, trigger syncs, copy feed URLs from your browser
- **Private by default** — dashboard and API bind to loopback or a private Tailscale address; nothing is exposed to the public internet unless you opt in
- **One-command install** — a small install script sets up Docker Compose on any Linux host

## Requirements

- A Linux host with Docker and the Compose plugin (an Ubuntu VPS with Tailscale is the reference setup)
- (Optional) [YouTube Data API v3 key](https://console.cloud.google.com/apis/credentials) — enables full video history and handle resolution; without it, the app uses YouTube's public RSS feeds (~15 most recent videos)

## Quick install (Linux VPS)

With Docker already installed, fetch the compose files and start the server:

```bash
curl -fsSL https://raw.githubusercontent.com/shay2000/PodcastSync-private/main/deploy/linux/install.sh | bash
```

The script installs into `~/podcastsync`, creates a private `.env` (mode 600),
pulls the image from GHCR, and starts the container. The dashboard listens on
`127.0.0.1:8642`.

To reach the dashboard from other devices on your Tailnet, pass your server's
Tailscale IPv4:

```bash
curl -fsSL https://raw.githubusercontent.com/shay2000/PodcastSync-private/main/deploy/linux/install.sh \
  | bash -s -- --bind-ip 100.x.y.z
```

Then open `http://100.x.y.z:8642` from any device on the Tailnet. The install
script is idempotent — re-run it (with the same options) to update to a newer
release.

To install a specific release instead of `main`:

```bash
curl -fsSL https://raw.githubusercontent.com/shay2000/PodcastSync-private/v0.3.0/deploy/linux/install.sh \
  | bash -s -- --tag v0.3.0 --bind-ip 100.x.y.z
```

### Manual setup

```bash
git clone https://github.com/shay2000/PodcastSync-private.git
cd PodcastSync-private
cp .env.example .env
# Edit .env: set PODCASTSYNC_PUBLIC_URL to the URL clients will use,
# e.g. http://100.x.y.z:8642 (Tailscale) or https://podcast.example.com (public).
docker compose up -d
curl -fsS http://127.0.0.1:8642/api/status
```

Data (SQLite database + downloaded MP3s) persists in the `podcastsync-data`
Docker volume.

### Public HTTPS feeds (optional)

Cloud-based podcast clients (e.g. Overcast) cannot reach a Tailscale-only
feed. If you need that, run the optional Caddy profile with a public domain:

1. Point a DNS A record (e.g. `podcast.example.com`) at the server and open
   TCP 80/443 in the cloud firewall; leave 8642 closed.
2. In `.env`, set `PODCASTSYNC_DOMAIN=podcast.example.com` and
   `PODCASTSYNC_PUBLIC_URL=https://podcast.example.com`.
3. `docker compose --profile public up -d`

Caddy publishes only `/feed/*` and `/audio/*` over HTTPS. The dashboard and
`/api` stay private. Full runbook: [`docs/ORACLE_VPS_HANDOFF.md`](docs/ORACLE_VPS_HANDOFF.md).

## Usage

### Adding a source

1. Open the dashboard (`http://<host>:8642`)
2. Paste a YouTube URL into the "Add Source" form:
   - Channel: `https://www.youtube.com/@mkbhd` or `https://www.youtube.com/channel/UCBJycsmduvYEL83R_U4JriQ`
   - Playlist: `https://www.youtube.com/playlist?list=PLxxxxxxx`
3. Set a name (optional) and max backfill count
4. Click **Add**, then **Sync Now**

### Subscribing in a podcast app

1. In the web UI, click **Copy Feed URL** next to a source
2. In your podcast app:
   - **Apple Podcasts**: File → Subscribe to Show by URL → paste the URL
   - **Downcast**: Add → Feed URL → paste
3. The feed URL looks like `http://100.x.y.z:8642/feed/1.xml` (Tailscale) or
   `https://podcast.example.com/feed/1.xml` (public profile)

On iOS, grant the podcast app Local Network / VPN permission when subscribing
to a private feed.

### Setting up the YouTube API key

The API key is optional but recommended — it enables:
- Resolving `@handle` URLs to channel IDs
- Fetching full video history (not just the last ~15)
- Getting video duration metadata

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a project and enable the **YouTube Data API v3**
3. Create an API key (no OAuth required)
4. In the PodcastSync web UI, go to **Settings** and paste the key

### YouTube sign-in cookies (optional)

The API key is not a YouTube sign-in. If a video requires an account, place a
Netscape-format cookie file at `cookies.txt` beside the Compose file, keep it
mode 600, and start with the cookie override:

```bash
chmod 600 cookies.txt
docker compose -f docker-compose.yml -f docker-compose.cookies.yml up -d
```

Then set its path (`/data/cookies.txt` inside the container) under Settings →
Advanced: cookie file. Never bake cookies into the image or commit them.

## Development

```bash
git clone https://github.com/shay2000/PodcastSync-private.git
cd PodcastSync-private
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"

# Run the backend directly (expects ffmpeg on the host)
./scripts/dev.sh
# Open http://127.0.0.1:8642

# Tests (offline, no network)
python -m pytest tests/ -q
```

## How it works

1. **Fetcher layer** checks YouTube for new videos (API first, RSS fallback)
2. **Download manager** uses yt-dlp to extract audio as MP3 at 192kbps with embedded thumbnails
3. **RSS generator** creates valid podcast XML with `<enclosure>` tags pointing at the server
4. **HTTP server** (FastAPI on port 8642) serves the RSS feeds and audio files
5. **Scheduler** (APScheduler) runs the fetch→download cycle on a timer

Releases are Docker images on GHCR (`ghcr.io/shay2000/podcastsync`), built for
`linux/amd64` and `linux/arm64` by CI on every `v*` tag.

## File locations

| What | Where |
|------|-------|
| Audio files (in container) | `/data/PodcastMirror/<source-name>/` |
| Database (in container) | `/data/podcastsync.db` |
| Host data | Docker volume `podcastsync-data` |
| Dashboard | `http://<bind-ip>:8642` (loopback or Tailscale address) |

## Legal / ToS considerations

- YouTube Data API usage with an API key is within Google's Terms of Service
- YouTube's public RSS feeds are intended for consumption
- Audio downloading is performed by yt-dlp as a user-controlled action
- Downloaded content is served only on your private network and is not redistributed
- **This tool is for personal use only** — respect content creators' rights

## Known limitations

- Overcast needs the public HTTPS profile (it cannot reach Tailscale-only feeds)
- YouTube's RSS feeds return only ~15 most recent videos (use an API key for full history)
- Podcast clients may cache feeds aggressively (new episodes can take up to an hour to appear)
- The server must be running for podcast clients to fetch episodes
