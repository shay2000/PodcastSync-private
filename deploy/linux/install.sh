#!/usr/bin/env bash
# PodcastSync — one-command Linux install for Docker deployments.
#
# Downloads docker-compose.yml, the Caddy config, and .env.example from the
# repository at a chosen release, creates a private .env, and starts the
# backend. The dashboard stays private to the machine (loopback) or a private
# Tailscale address; the optional `public` profile (Caddy, HTTPS feeds) can be
# enabled later — see the README.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/shay2000/PodcastSync-private/<ref>/deploy/linux/install.sh | bash -s -- [--bind-ip <ip>] [--tag vX.Y.Z]
#
# Or run it from a clone of the repository.
set -Eeuo pipefail

REPO="shay2000/PodcastSync-private"
DEFAULT_REF="main"

say()  { printf '%s\n' "$*"; }
die()  { printf 'Error: %s\n' "$1" >&2; exit 1; }

bind_ip="127.0.0.1"
ref="$DEFAULT_REF"

while (($# > 0)); do
    case "$1" in
        --bind-ip)
            (($# >= 2)) || die "--bind-ip needs a value"
            bind_ip="$2"
            shift 2
            ;;
        --tag)
            (($# >= 2)) || die "--tag needs a value (e.g. v0.3.0)"
            ref="$2"
            shift 2
            ;;
        -h|--help)
            sed -n '2,12p' "$0" 2>/dev/null || true
            exit 0
            ;;
        *)
            die "unknown argument: $1"
            ;;
    esac
done

command -v docker >/dev/null 2>&1 \
    || die "Docker is not installed. Install it first: https://docs.docker.com/engine/install/"
docker compose version >/dev/null 2>&1 \
    || die "the Docker Compose plugin is not available"
docker info >/dev/null 2>&1 \
    || die "Docker is not running or this user cannot access it (try: sudo usermod -aG docker \$USER, then log in again)"

install_dir="${PODCASTSYNC_INSTALL_DIR:-$HOME/podcastsync}"
mkdir -p "$install_dir"
cd "$install_dir"

if [[ -f docker-compose.yml ]]; then
    say "-> Existing deployment found in $install_dir; it will be updated in place."
else
    say "-> Installing PodcastSync into $install_dir"
fi

base="https://raw.githubusercontent.com/${REPO}/${ref}"
for f in docker-compose.yml docker-compose.cookies.yml .env.example deploy/caddy/Caddyfile.docker; do
    dest="$install_dir/$f"
    mkdir -p "$(dirname "$dest")"
    if curl -fsSL "$base/$f" -o "$dest"; then
        say "   fetched $f"
    elif [[ "$f" == "docker-compose.cookies.yml" ]]; then
        say "   skipped optional $f"
        rm -f "$dest"
    else
        die "could not download $f from $base"
    fi
done

if [[ ! -f .env ]]; then
    umask 077
    {
        printf 'PODCASTSYNC_BIND_IP=%s\n' "$bind_ip"
        printf 'PODCASTSYNC_PUBLIC_URL=%s\n' "${PODCASTSYNC_PUBLIC_URL:-http://${bind_ip}:8642}"
        printf 'YOUTUBE_API_KEY=%s\n' "${YOUTUBE_API_KEY:-}"
        printf 'PODCASTSYNC_POLL_INTERVAL=%s\n' "${PODCASTSYNC_POLL_INTERVAL:-30}"
    } > .env
    say "-> Created .env (mode 600)."
    say "   The dashboard will be reachable at http://${bind_ip}:8642"
    say "   Edit ${install_dir}/.env to add a YOUTUBE_API_KEY (optional) or change the poll interval."
else
    say "-> .env already exists; leaving it unchanged."
fi

say "-> Pulling the latest image and starting PodcastSync"
docker compose pull
docker compose up -d

say "-> Waiting for the health check"
for _ in $(seq 1 30); do
    if docker compose ps --format json 2>/dev/null \
        | grep -q '"Health":"healthy"'; then
        break
    fi
    sleep 2
done

if docker compose ps --format json 2>/dev/null | grep -q '"Health":"healthy"'; then
    say "PodcastSync is running and healthy."
else
    die "the container did not become healthy in time; inspect it with: docker compose logs"
fi

say ""
say "Dashboard:  http://${bind_ip}:8642   (private — this machine / Tailnet only)"
say "Data:       docker volume podcastsync-data (SQLite DB + downloaded MP3s)"
say "Manage:     cd $install_dir && docker compose [logs|restart|down]"
say "Update:     re-run this installer with the same --tag or --bind-ip options"
say ""
say "If you bound to a Tailscale address, make sure port 8642 is reachable on"
say "that interface (it usually is on a Tailnet) and open the dashboard from a"
say "device on the same Tailnet."
