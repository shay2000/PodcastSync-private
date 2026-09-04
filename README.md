# PodcastSync

![Platform](https://img.shields.io/badge/platform-macOS%2013%2B-111827?style=flat-square)
![App Type](https://img.shields.io/badge/app-menu%20bar-0f766e?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-166534?style=flat-square)
![Status](https://img.shields.io/badge/status-active-9a3412?style=flat-square)
![Release](https://img.shields.io/github/v/release/shay2000/PodcastSync)
![Downloads](https://img.shields.io/github/downloads/shay2000/PodcastSync/total)

Turn YouTube channels and playlists into self-hosted podcast feeds.

PodcastSync is a macOS menu bar app that monitors YouTube sources, downloads audio as MP3, and serves podcast RSS feeds on your local network. Subscribe to the feeds in Apple Podcasts, Downcast, or another podcast client on your LAN.

## Features

- **Add YouTube channels or playlists** — paste a URL, the app handles the rest
- **Automatic polling** — checks for new videos on a configurable schedule (default: every 30 minutes)
- **Audio-only downloads** — extracts audio as MP3 at 192kbps with embedded cover art
- **Podcast RSS feeds** — one feed per source, valid for any podcast client
- **LAN accessible** — feed URLs work from any device on your network
- **Web UI** — manage sources, trigger syncs, copy feed URLs from your browser
- **Menu bar app** — runs quietly in the background, no Dock icon

## Requirements

- macOS 13 (Ventura) or later
- (Optional) [YouTube Data API v3 key](https://console.cloud.google.com/apis/credentials) — enables full video history and handle resolution; without it, the app uses YouTube's public RSS feeds (~15 most recent videos)

## Installation

### From DMG

1. Download the latest `PodcastSync.dmg` from the [GitHub Releases page](https://github.com/shay2000/PodcastSync/releases) or build it locally
2. Open the DMG and drag `PodcastSync.app` to Applications
3. Right-click the app → **Open** (required once, to bypass Gatekeeper for this ad-hoc signed app)
4. The app appears in your menu bar

The packaged DMG bundles the Python backend, `yt-dlp`, `ffmpeg`, and `ffprobe`, so end users do not need to install Homebrew, Python, or extra media tools first.

### Development mode

```bash
git clone https://github.com/shay2000/PodcastSync.git
cd PodcastSync

# Set up Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Development mode still expects ffmpeg on the local machine
brew install ffmpeg

# Run the backend directly
./scripts/dev.sh
# Open http://127.0.0.1:8642 in your browser
```

### Run on a server (Docker)

The Docker image runs the same backend as the macOS app, with SQLite and audio
stored in a persistent `podcastsync-data` volume. The default Compose file
publishes the backend only on `127.0.0.1:8642`; put a TLS-terminating reverse
proxy in front of it rather than publishing port 8642 to the internet.

1. Point a DNS A record such as `podcast.example.com` at the server.
2. Create a local `.env` file (never commit it) with the public origin and any
   optional settings:

   ```dotenv
   PODCASTSYNC_PUBLIC_URL=https://podcast.example.com
   YOUTUBE_API_KEY=
   PODCASTSYNC_POLL_INTERVAL=30
   ```

3. Start and check the service:

   ```bash
   docker compose up -d --build
   curl -fsS http://127.0.0.1:8642/api/status
   docker compose logs -f podcastsync
   ```

4. Configure `deploy/caddy/Caddyfile` with the real domain and configure TLS
   before public exposure. Caddy can obtain a certificate automatically once
   DNS and firewall rules for ports 80 and 443 are ready.

Do not expose this deployment publicly until the planned Host allow-list and
API-token hardening is enabled: the current backend has no user accounts or
authentication. On a headless server, use a Netscape-format cookie file only
when YouTube requires sign-in; mount it read-only at `/data/cookies.txt` and set
`cookies_file_path` through the settings API. Never bake a cookie file into the
image or commit it.

With `PODCASTSYNC_PUBLIC_URL` set, copied feeds and generated RSS enclosures
use the HTTPS public origin, for example
`https://podcast.example.com/feed/1.xml`. The macOS menu bar app continues to
manage a local bundled backend in v1; the Docker deployment is managed through
its web UI.

## Usage

### Adding a source

1. Click the menu bar icon → **Open Web UI**
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
3. The feed URL looks like `http://192.168.x.x:8642/feed/1.xml`

Overcast disclaimer:
Overcast's crawlers cannot reach a feed hosted only on your LAN. Use the Docker
server deployment above with a public HTTPS URL for Overcast. Apple Podcasts
and Downcast can use the LAN URL. On iOS 14+, grant the podcast app Local
Network permission when subscribing to a LAN feed.

### Setting up the YouTube API key

The API key is optional but recommended — it enables:
- Resolving `@handle` URLs to channel IDs
- Fetching full video history (not just the last ~15)
- Getting video duration metadata

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a project and enable the **YouTube Data API v3**
3. Create an API key (no OAuth required)
4. In the PodcastSync web UI, go to **Settings** and paste the key

## Building

```bash
# Install Python dependencies for the backend and the packager
pip install -r requirements.txt

# Ensure ffmpeg is available on the build machine so it can be bundled
brew install ffmpeg

# Build a fresh self-contained .app and .dmg
./scripts/build_app.sh

# Output: build/PodcastSync.dmg
```

## How it works

1. **Fetcher layer** checks YouTube for new videos (API first, RSS fallback)
2. **Download manager** uses yt-dlp to extract audio as MP3 at 192kbps with embedded thumbnails
3. **RSS generator** creates valid podcast XML with `<enclosure>` tags pointing to the local server
4. **HTTP server** (FastAPI on port 8642) serves the RSS feeds and audio files
5. **Scheduler** (APScheduler) runs the fetch→download cycle on a timer
6. **Menu bar app** (Swift) manages the Python backend process

## File locations

| What | Where |
|------|-------|
| Audio files | `~/PodcastMirror/<source-name>/` |
| Database | `~/.podcastsync/podcastsync.db` |
| Server | `http://127.0.0.1:8642` locally; use the host's LAN IP for other devices |

## Legal / ToS considerations

- YouTube Data API usage with an API key is within Google's Terms of Service
- YouTube's public RSS feeds are intended for consumption
- Audio downloading is performed by yt-dlp as a user-controlled action
- Downloaded content is served only on your local network and is not redistributed
- **This tool is for personal use only** — respect content creators' rights

## Known limitations

- The app is ad-hoc signed, not notarized, so Gatekeeper will prompt on first launch
- Building the DMG still requires `ffmpeg` on the machine doing the build; the finished DMG bundles it for end users
- Overcast is known to not work reliably with PodcastSync feeds
- YouTube's RSS feeds return only ~15 most recent videos (use an API key for full history)
- Podcast clients may cache feeds aggressively (new episodes can take up to an hour to appear)
- The server must be running for podcast clients to fetch episodes
