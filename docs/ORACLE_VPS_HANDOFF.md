# PodcastSync on an Oracle VPS

This is the handoff for giving PodcastSync to someone who is not comfortable
with servers. It is written for two people:

- The **owner** completes the short account, DNS, and network steps.
- Their **coding agent** completes the repeatable server work and verifies the
  result.

The recommended deployment runs the backend and Caddy in Docker. Caddy makes
only `/feed/...` and `/audio/...` public. The dashboard and every `/api/...`
endpoint remain private and are opened through an SSH tunnel. This matters
because the backend does not yet have user accounts.

## What the owner needs to provide

The owner should give the coding agent:

1. The VPS SSH address, SSH username, and the path to their SSH key. Give the
   key path, never the private-key contents.
2. A domain or subdomain they control, for example
   `podcast.example.com`.
3. The VPS public IPv4 address.
4. A YouTube Data API key only if they want full history and `@handle`
   resolution. It is optional; enter it into `.env` through a secure prompt,
   not into a chat message or a committed file.

The owner does not need to install Python, ffmpeg, or Docker on their Mac.

## Owner step 1: create the Oracle server

In the Oracle Cloud console, create an Ubuntu 22.04 or 24.04 VM in a region
with capacity. AMD64 and ARM64 are supported by the Docker images. Assign a
public IPv4 address, preferably a reserved one, so the DNS record does not
change after a restart.

In the VM's VCN security list, allow:

- TCP 22 from the owner's home/office IP if possible (SSH administration).
- TCP 80 from `0.0.0.0/0` (certificate issuance and HTTP-to-HTTPS redirect).
- TCP 443 from `0.0.0.0/0` (podcast clients).

Do **not** open TCP 8642 to the internet. The Docker Compose file binds that
port to loopback only.

Oracle's console labels may change; the important outcome is that 80 and 443
reach the VM and 8642 does not.

## Owner step 2: create the DNS record

At the registrar or DNS provider, create an **A** record:

| Field | Example |
|---|---|
| Type | A |
| Name/Host | `podcast` |
| Value | the VPS public IPv4 address |
| TTL | Auto or 300 seconds |

This creates `podcast.example.com`. If using the root domain, the host is
usually `@`. Do not point DNS at a private address such as `100.70.x.x`, and
do not use a CNAME unless the provider specifically supplies a stable hostname.

If Cloudflare is being used, start with **DNS only** while Caddy obtains its
certificate. The coding agent can switch to a proxy later after HTTPS has been
verified.

DNS can take a few minutes. The agent can check it with:

```bash
getent hosts podcast.example.com
```

The result should contain the VPS public IPv4 address.

## Coding-agent runbook

The agent should read `AGENTS.md`, `README.md`, and this file before changing
anything. The agent may automate the following steps:

1. Confirm the repository is present on the VPS and that the working tree is
   clean. Keep `.env`, database data, and any cookie file out of git.
2. Confirm the architecture, Docker, and Compose plugin:

   ```bash
   uname -m
   docker --version
   docker compose version
   ```

   If Docker is missing, explain the package installation and ask the owner to
   approve it. Do not pipe an unreviewed remote script into a shell.
3. Confirm DNS resolves to the VPS and that Oracle's ingress rules allow 80/443.
4. Copy `.env.example` to `.env` or run the idempotent helper from the repo root:

   ```bash
   ./deploy/oracle/install.sh --domain podcast.example.com
   ```

   The helper never overwrites an existing `.env` and does not alter DNS,
   firewall rules, or unrelated files. If an API key is needed, add it to the
   existing `.env` using a secret prompt and keep the file mode at `600`.
5. Start the stack:

   ```bash
   docker compose --profile public up -d --build
   docker compose ps
   docker compose logs --tail=100 podcastsync caddy
   ```

6. Verify the private backend from the host:

   ```bash
   curl -fsS http://127.0.0.1:8642/api/status
   ```

7. Verify the public boundary. The root and `/api` should not be used as public
   admin endpoints; a feed URL should return RSS after a source is added:

   ```bash
   curl -I https://podcast.example.com/
   curl -I https://podcast.example.com/api/status
   curl -I https://podcast.example.com/feed/1.xml
   ```

   Before source 1 exists, a 404 for `/feed/1.xml` is expected. The important
   checks are valid HTTPS and that the public root/API do not expose the
   dashboard. After adding a source, repeat the feed check and confirm the XML
   contains `https://podcast.example.com/audio/...` enclosures.
8. Give the owner the SSH tunnel command:

   ```bash
   ssh -N -L 8642:127.0.0.1:8642 <ssh-user>@<server-address>
   ```

   While that terminal remains open, the owner visits
   `http://127.0.0.1:8642` on their Mac. The dashboard's **Copy RSS** button
   should copy the public HTTPS feed, even though the dashboard itself is
   reached through the private tunnel.

The agent must not expose 8642, put API keys/cookies in git, print secrets in
logs, or make broad cleanup changes outside the repository's deployment files.

## Owner step 3: use the dashboard and Overcast

Through the SSH tunnel:

1. Open `http://127.0.0.1:8642`.
2. Choose **Add Source** and paste a YouTube channel or playlist URL.
3. Choose **Sync Now** and wait for at least one episode to show **completed**.
4. Select the source and copy its **RSS** URL.
5. In Overcast, choose **Add Podcast → Add URL**, paste the HTTPS RSS URL, and
   subscribe.

The feed is public by design so Overcast's servers can fetch it. The admin URL,
database, and source-management API are not public.

## YouTube API keys and YouTube sign-in are different

A Google/YouTube Data API key authorizes metadata requests. It does **not** log
yt-dlp into YouTube and cannot replace browser cookies. Most public channels do
not need cookies; if a particular video says “sign in,” use the YouTube
authentication section in Settings.

On a Mac installation, select a browser that is signed into YouTube and press
**Test Cookies**. On a Docker/Linux VPS there is no usable Mac browser profile,
so browser detection showing “No supported browsers found” is expected. Use a
Netscape-format cookie file instead.

After authentication succeeds, episodes that failed earlier remain marked
failed until the owner chooses **Re-download** for them. A successful cookie
test does not change old download rows automatically.

## Optional YouTube authentication on a headless VPS

If YouTube requires sign-in, export a Netscape-format `cookies.txt` on the
owner's own machine, then transfer it over SSH and protect it:

```bash
scp cookies.txt <ssh-user>@<server-address>:/path/to/PodcastSync-private/cookies.txt
chmod 600 cookies.txt
```

The agent should mount it read-only at `/data/cookies.txt`, set
`cookies_file_path` in the private dashboard's Settings, test it, and delete
any temporary transfer copy. Never commit it or paste its contents into chat.

## Routine maintenance

From the repository directory on the VPS:

```bash
# Logs and health
docker compose logs -f podcastsync
docker compose ps

# Update after reviewing the new commit/tag
git pull --ff-only
docker compose --profile public up -d --build
```

Before updates, back up the named `podcastsync-data` volume (database and audio).
The owner should also keep a second copy of important audio elsewhere; a VPS
volume is not a complete backup strategy.

If the public site stops working, check in this order: DNS resolves to the
current public IP, Oracle allows 80/443, Caddy logs show a certificate, and the
backend is healthy on `127.0.0.1:8642`. Do not “fix” it by opening 8642.
