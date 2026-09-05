#!/usr/bin/env bash

set -Eeuo pipefail

usage() {
    cat <<'EOF'
Usage: ./deploy/oracle/install.sh --domain podcast.example.com

Run from the PodcastSync repository root on an Ubuntu Oracle VPS. The script
creates .env only when it does not already exist, validates the Compose model,
builds the backend, and starts the private dashboard plus public Caddy profile.
It does not change DNS, Oracle VCN rules, UFW, or an existing .env file.
EOF
}

die() {
    printf 'Error: %s\n' "$1" >&2
    exit 1
}

domain=""

while (($# > 0)); do
    case "$1" in
        --domain)
            (($# >= 2)) || die "--domain needs a value"
            domain="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "unknown argument: $1"
            ;;
    esac
done

[[ -n "$domain" ]] || die "provide a domain with --domain"
[[ "$domain" =~ ^[A-Za-z0-9.-]+$ ]] || die "domain contains unexpected characters"
[[ -f docker-compose.yml ]] || die "run this script from the repository root"
command -v docker >/dev/null 2>&1 || die "Docker is not installed or is not on PATH"
docker compose version >/dev/null 2>&1 || die "the Docker Compose plugin is not available"
docker info >/dev/null 2>&1 || die "Docker is not running or this user cannot access it"

if [[ ! -f .env ]]; then
    umask 077
    {
        printf 'PODCASTSYNC_DOMAIN=%s\n' "$domain"
        printf 'PODCASTSYNC_PUBLIC_URL=https://%s\n' "$domain"
        printf 'YOUTUBE_API_KEY=%s\n' "${YOUTUBE_API_KEY:-}"
        printf 'PODCASTSYNC_POLL_INTERVAL=%s\n' "${PODCASTSYNC_POLL_INTERVAL:-30}"
    } > .env
    printf 'Created .env with mode 600. Add an API key there only if you want full YouTube history.\n'
else
    printf '.env already exists; leaving it unchanged.\n'
fi

configured_domain="$(sed -n 's/^PODCASTSYNC_DOMAIN=//p' .env | head -n 1)"
configured_url="$(sed -n 's/^PODCASTSYNC_PUBLIC_URL=//p' .env | head -n 1)"
[[ "$configured_domain" == "$domain" ]] || die "existing .env uses domain '$configured_domain', not '$domain'"
[[ "$configured_url" == "https://${domain}" ]] || die "PODCASTSYNC_PUBLIC_URL must be https://${domain}"

docker compose --profile public config --quiet
docker compose --profile public up -d --build

docker compose exec -T podcastsync python -c \
    'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8642/api/status", timeout=5)'

printf '\nPodcastSync is running.\n'
printf '%s\n' "Public feed origin: https://${domain}"
printf '%s\n' 'Private dashboard tunnel:'
printf '%s\n' "  ssh -N -L 8642:127.0.0.1:8642 <ssh-user>@<server-address>"
printf '%s\n' 'Then open http://127.0.0.1:8642 on your own Mac.'
