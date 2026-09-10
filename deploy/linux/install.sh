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
#   curl -fsSL https://raw.githubusercontent.com/shay2000/PodcastSync-VPS/<ref>/deploy/linux/install.sh | bash -s -- [--bind-ip <ip>] [--tag vX.Y.Z]
#
# Or run it from a clone of the repository.
set -Eeuo pipefail

REPO="shay2000/PodcastSync-VPS"
DEFAULT_REF="main"

say()  { printf '%s\n' "$*"; }
die()  { printf 'Error: %s\n' "$1" >&2; exit 1; }

bind_ip="127.0.0.1"
ref="$DEFAULT_REF"
image=""

# The dashboard and API have no authentication: the bind address must stay a
# loopback, private-network, or Tailscale (CGNAT 100.64.0.0/10) address.
# Anything else (0.0.0.0, a public IP) would expose the admin surface.
is_private_ip() {
    local ip="$1"
    [[ "$ip" =~ ^127\.[0-9]+\.[0-9]+\.[0-9]+$ ]] && return 0
    [[ "$ip" =~ ^10\.[0-9]+\.[0-9]+\.[0-9]+$ ]] && return 0
    [[ "$ip" =~ ^192\.168\.[0-9]+\.[0-9]+$ ]] && return 0
    [[ "$ip" =~ ^172\.(1[6-9]|2[0-9]|3[01])\.[0-9]+\.[0-9]+$ ]] && return 0
    [[ "$ip" =~ ^100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]+\.[0-9]+$ ]] && return 0
    return 1
}

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
            image="ghcr.io/shay2000/podcastsync:${ref#v}"
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

if [[ "$bind_ip" == "0.0.0.0" ]] || [[ "$bind_ip" == "::" ]]; then
    die "refusing to bind 0.0.0.0: the dashboard has no authentication. Use a loopback or private Tailscale address (e.g. --bind-ip 100.x.y.z)"
fi
is_private_ip "$bind_ip" || die "refusing to bind public address '$bind_ip': the dashboard has no authentication. Use a loopback (127.0.0.1) or private Tailscale address."

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
# Fetch deployment files. On an existing deployment, never clobber local
# customizations (external volume mappings, cookie mounts, edited compose):
# download to a side-by-side file and only replace the live one when the
# operator has not modified it. Compose files are user-owned config, not
# installer-owned state.
existing_deployment=0
[[ -f docker-compose.yml ]] && existing_deployment=1

for f in docker-compose.yml docker-compose.cookies.yml .env.example deploy/caddy/Caddyfile.docker; do
    dest="$install_dir/$f"
    mkdir -p "$(dirname "$dest")"
    tmp="${dest}.installer-new"
    if curl -fsSL "$base/$f" -o "$tmp"; then
        if [[ "$existing_deployment" -eq 1 && -f "$dest" ]]; then
            if cmp -s "$tmp" "$dest"; then
                rm -f "$tmp"
                say "   $f unchanged"
            else
                # The live file differs from the repo version. Replace only
                # if the live file still matches the repo version this
                # deployment was last installed from; otherwise keep the
                # local edits and leave the update beside it for review.
                if [[ -f "${dest}.installer-base" ]] && cmp -s "$dest" "${dest}.installer-base"; then
                    mv "$tmp" "$dest"
                    mv "$dest" "${dest}.installer-base" 2>/dev/null || true
                    cp "$dest" "${dest}.installer-base"
                    say "   updated $f"
                else
                    mv "$tmp" "${dest}.NEW"
                    say "   kept local $f (modified); new version saved as ${f}.NEW for review"
                fi
            fi
        else
            mv "$tmp" "$dest"
            cp "$dest" "${dest}.installer-base"
            say "   fetched $f"
        fi
    elif [[ "$f" == "docker-compose.cookies.yml" ]]; then
        rm -f "$tmp"
        if [[ "$existing_deployment" -eq 0 ]]; then
            say "   skipped optional $f"
        fi
    else
        rm -f "$tmp"
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
        [[ -n "$image" ]] && printf 'PODCASTSYNC_IMAGE=%s\n' "$image"
    } > .env
    say "-> Created .env (mode 600)."
    say "   The dashboard will be reachable at http://${bind_ip}:8642"
    say "   Edit ${install_dir}/.env to add a YOUTUBE_API_KEY (optional) or change the poll interval."
else
    say "-> .env already exists; leaving it unchanged."
fi

# Update a KEY=VALUE line in .env in place (portable across GNU/BSD sed).
set_env_value() {
    local key="$1" value="$2"
    if grep -q "^${key}=" .env 2>/dev/null; then
        sed -i.bak "s|^${key}=.*|${key}=${value}|" .env && rm -f .env.bak
    else
        printf '%s=%s\n' "$key" "$value" >> .env
    fi
}

# A --tag install is a pinned install: make sure the running image matches the
# fetched deployment files, updating the pin when the operator changes --tag.
if [[ -n "$image" ]]; then
    current_image="$(sed -n 's/^PODCASTSYNC_IMAGE=//p' .env | head -n 1)"
    if [[ "$current_image" != "$image" ]]; then
        set_env_value PODCASTSYNC_IMAGE "$image"
        say "-> Pinned PODCASTSYNC_IMAGE=${image} (--tag ${ref})"
    fi
fi

# Keep the bind address in .env in sync with this run's --bind-ip. Without
# this, re-running the installer with a different address leaves the old one
# active while the success message claims the new one.
if [[ -f .env ]]; then
    current_bind="$(sed -n 's/^PODCASTSYNC_BIND_IP=//p' .env | head -n 1)"
    if [[ -n "$current_bind" && "$current_bind" != "$bind_ip" ]]; then
        set_env_value PODCASTSYNC_BIND_IP "$bind_ip"
        say "-> Updated PODCASTSYNC_BIND_IP=${bind_ip} (was ${current_bind})"
        # The default public URL tracks the bind address unless the operator
        # set a custom one (public HTTPS profile).
        current_url="$(sed -n 's/^PODCASTSYNC_PUBLIC_URL=//p' .env | head -n 1)"
        if [[ "$current_url" == "http://${current_bind}:8642" ]]; then
            set_env_value PODCASTSYNC_PUBLIC_URL "http://${bind_ip}:8642"
            say "-> Updated PODCASTSYNC_PUBLIC_URL=http://${bind_ip}:8642"
        fi
    fi
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
