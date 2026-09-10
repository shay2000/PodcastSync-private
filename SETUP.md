# PodcastSync — Agent Setup Instructions

You are setting up **PodcastSync** for its owner: a self-hosted server that
turns YouTube channels into podcast RSS feeds. This file is your runbook.
Follow it in order. The owner is not technical — keep them informed in plain
language and never overwhelm them with jargon.

## Hard rules (always)

- Never expose port 8642 to the public internet. The dashboard and API have
  no authentication; they stay on loopback or a private Tailscale address.
- Never print, copy, or commit secrets (SSH keys, YouTube API keys, cookie
  files, passwords). Ask the owner to enter secrets themselves whenever a
  secret must be set.
- If a step fails or the owner says something that contradicts this file:
  stop, explain, and ask how to proceed. Do not invent fixes.
- Only public podcast feed (`/feed/*`) and audio (`/audio/*`) paths may ever
  be exposed to the internet, and only via the Caddy `public` profile.

## Step 0 — Find the code and read the ground truth

1. Find the PodcastSync repository on this machine (a folder containing this
   file, `AGENTS.md`, and `deploy/`), or clone it from
   `https://github.com/shay2000/PodcastSync-VPS`.
2. Read `AGENTS.md` and `README.md` in that folder — they are the source of
   truth for architecture and deployment rules.

## Step 1 — Figure out where you are

- If `tailscale ip -4` and `docker info` work on this machine and the repo is
  here, you are **on the server** — run server commands locally.
- Otherwise the server is remote: ask the owner for the SSH login
  (`user@host`) and the **path** to their SSH key (never the key's contents).
  Test the login with a harmless command before doing anything else.

## Step 2 — Ask the owner, one question at a time

Only ask when you need the answer. You will need:

- The server's **Tailscale IPv4** (read it yourself with `tailscale ip -4` if
  you are on the server).
- Whether they have a **YouTube API key** (optional; enables full channel
  history — without it only ~15 recent videos per channel).
- Whether they use **Overcast** or another cloud podcast app that fetches
  feeds from the public internet (this adds the optional public-feeds phase;
  see Step 5).

## Step 3 — Install and start

Run the repository's installer on the server:

```bash
deploy/linux/install.sh --bind-ip <server-tailscale-ipv4>
```

(Use the plain `deploy/linux/install.sh` for a loopback-only install, or add
`--tag vX.Y.Z` to pin a release.)

The installer refuses public bind addresses, creates a private `.env`, pulls
the image from GHCR, starts the container, and verifies the health check.

## Step 4 — Verify

1. Health: `curl -fsS http://127.0.0.1:8642/api/status` on the server must
   return JSON.
2. Binding: `docker compose port podcastsync 8642` must show the Tailscale
   address — never `0.0.0.0`.
3. Dashboard: the owner opens `http://<tailscale-ip>:8642` from a device on
   the same Tailnet, adds one YouTube channel, presses **Sync Now**, and
   waits for one episode to show **completed**.
4. Have them copy the feed URL and subscribe in their podcast app
   (Apple Podcasts: File → Subscribe to Show by URL).

## Step 5 (optional) — Public feeds for cloud podcast apps (Overcast)

Only if the owner asked for it. Follow `docs/ORACLE_VPS_HANDOFF.md`; the
short version:

1. The owner needs a hostname pointing at the server's public IPv4:
   an owned subdomain, **or** a free DuckDNS name
   (`https://www.duckdns.org` — create e.g. `my-podcasts.duckdns.org`).
2. If you have a browser-control tool (BrowserOS, Playwright, or a similar
   MCP integration), offer to do the DuckDNS browser work: navigate, suggest
   a random-ish name, fill in the server's public IP (read it from the
   server with `curl -s https://api.ipify.org`). Boundaries: ask before
   driving their browser; the owner does the sign-in and any 2FA/captcha
   themselves; you never touch passwords or one-time codes.
3. Open TCP 80 and 443 in the server's cloud firewall; leave 8642 closed.
4. Set `PODCASTSYNC_DOMAIN` and `PODCASTSYNC_PUBLIC_URL` in the server's
   `.env`, then `docker compose --profile public up -d`.
5. Verify: `https://<hostname>/feed/…` loads with a valid certificate.

## Step 6 — Report back to the owner

Tell them, in plain language:

- The dashboard address to bookmark.
- What to subscribe to in their podcast app (and that Overcast uses the
  public HTTPS feed URL).
- How to update later: ask you to re-run the installer, or re-run the
  install command from the README. Their channels and saved episodes are
  kept across updates.
- Where to get help: `README.md` (everyday use) and `HANDOFF.md` (technical).
