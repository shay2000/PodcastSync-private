<!--
  Paste the ENTIRE contents of this file (from the heading below) into Hermes
  as its first message. It deploys the PodcastSync backend to a Linux VPS and
  makes the web dashboard reachable from a Mac over Tailscale, asking the owner
  for information as it goes.
-->

# Set up PodcastSync on a VPS for me, over Tailscale

You are helping the person you are talking to deploy the **PodcastSync**
backend to a Linux VPS and access its web dashboard from a Mac. Tailscale is
already installed, logged in, and connected on **both** the VPS and the Mac —
verify that yourself, do not just take it on faith. Unless the owner asks for
public podcast feeds, the whole installation stays private to their Tailnet;
nothing needs to be exposed to the public internet.

This is a step-by-step installation. Work **gate by gate**: do what one gate
asks, verify it, tell the owner in plain language (1–3 short sentences) what
just happened and what is next, then move on. Never skip a verification. If a
check fails or the owner says something that contradicts an instruction, stop,
explain, and ask how to proceed — do not paper over the problem.

## Before you run anything

1. If a repository directory for PodcastSync already exists on this machine
   (look for `AGENTS.md`, `docker-compose.yml`, and `deploy/`), read these
   files first — they are the ground truth for this deployment:
   - `README.md` → section **"Run on a server (Docker)"**
   - `AGENTS.md` → section **"Oracle VPS / Docker handoff"** (the hard rules:
     never expose port 8642 to the internet, never print or commit secrets,
     never make broad changes outside the repo's deployment files)
   - `docs/ORACLE_VPS_HANDOFF.md` → read for background, but follow THIS prompt
     for the Tailscale steps; the Oracle runbook assumes a public domain and an
     SSH tunnel, which we are not using unless the owner later asks for public
     feeds.
2. Figure out where you are running:
   - If `tailscale ip -4` and Docker work on this machine and the PodcastSync
     repo is here, you are **on the VPS** — run the server commands locally.
   - Otherwise you are on the Mac (or another machine) and must drive the VPS
     over SSH. Ask the owner for the SSH login (`user@host`) and the **path** to
     their SSH key — never the key's contents. Test the login once with a
     harmless command before installing anything.
3. Ask questions one at a time, only when you need the answer. Do not dump a
   form on the owner. You will need these facts over the course of the install
   (gather each one right before its gate):

   - The VPS's **Tailscale IPv4** (you can read it yourself if you are on the
     VPS: `tailscale ip -4`; otherwise ask the owner to run that and paste the
     number, or run it over SSH).
   - Whether the owner has a **YouTube Data API key** and wants full channel
     history (optional — skip if they do not have one).
   - Whether podcast feeds must be reachable by **public internet podcast
     apps** such as Overcast (this changes the install; see the optional step
     near the end). Ask this once, up front, so you know which topology you are
     building.

## Gate 1 — Network check

1. Confirm Tailscale is up on the VPS. From the VPS (locally or over SSH):

   ```bash
   tailscale status
   tailscale ip -4
   ```

   Record the VPS IPv4 (something like `100.101.102.103`) as `<VPS_TS_IP>`.
2. Confirm the Mac is on the same Tailnet. Ask the owner to run `tailscale
   status` on their Mac, or ping the VPS address from the Mac:

   ```bash
   ping -c 2 <VPS_TS_IP>
   ```

   If either side is not connected, stop and ask the owner to fix their
   Tailscale login before continuing.

## Gate 2 — Code and Docker on the VPS

1. Confirm the PodcastSync source is on the VPS:
   - If the repo already exists there (it does if PodcastSync has been deployed
     before), go into it and confirm it is the current version. Updating an
     existing install: preserve `.env` untouched, then replace the code (see
     Gate 4 for the exact commands; for an rsync-driven install, re-run the
     rsync below, then `docker compose up -d --build`).
   - If the repo is NOT on the VPS and you are on the Mac with a PodcastSync
     checkout in front of you, send the working tree up with rsync (this
     transfers the exact version the owner is looking at, including this
     project's deployment files). Run from the repo root on the Mac:

     ```bash
     rsync -az --delete \
       --exclude .git --exclude venv --exclude build \
       --exclude .env --exclude cookies.txt --exclude .DS_Store \
       ./ <user>@<VPS_TS_IP>:~/podcastsync/
     ```

     The `.env` and `cookies.txt` exclusions mean an existing server copy of
     those files is never overwritten or deleted.
   - If you are on the VPS and the repo is missing, ask the owner how they want
     the code to get there (git clone URL and credentials, or paste) before
     proceeding.
2. Verify Docker and the Compose plugin on the VPS:

   ```bash
   docker --version
   docker compose version
   docker info
   ```

   If Docker is missing, do not install it on your own: explain what is needed
   and ask the owner to approve the installation. Never pipe an unreviewed
   remote script into a shell.

## Gate 3 — Create `.env` (private values only)

On the VPS, inside the repo directory, create `.env` **only if it does not
already exist**. If it exists, never overwrite it — read it and reconcile by
asking the owner when the values disagree. Keep the file mode at `600` and
never print its contents or paste them into chat.

```bash
cd ~/podcastsync            # the repo dir on the VPS
umask 077
if [[ ! -f .env ]]; then
  cat > .env <<EOF
PODCASTSYNC_BIND_IP=<VPS_TS_IP>
PODCASTSYNC_PUBLIC_URL=http://<VPS_TS_IP>:8642
YOUTUBE_API_KEY=
PODCASTSYNC_POLL_INTERVAL=30
EOF
fi
chmod 600 .env
```

Explain what these mean in plain terms:
- `PODCASTSYNC_BIND_IP` is the VPS's Tailscale address. Docker publishes the
  app on that interface only, so the dashboard is reachable over the Tailnet
  and **not** from the public internet. Never set it to `0.0.0.0`.
- `PODCASTSYNC_PUBLIC_URL` is the address the app bakes into RSS feed and audio
  links. Because the owner's podcast apps and dashboard all live on the
  Tailnet, that address is `http://<VPS_TS_IP>:8642`. (`docker-compose.yml`
  requires this variable to be set.)
- If the owner has a YouTube Data API key and wants full history, ask for it
  and set `YOUTUBE_API_KEY=<key>` in `.env` yourself using a secret prompt.
  Never accept the key in a chat message.

## Gate 4 — Build and start

```bash
cd ~/podcastsync
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 podcastsync
```

Wait until the `podcastsync` container reports **healthy** (the Compose file
defines a healthcheck). If the build or start fails, read the logs, fix what is
in your control, and otherwise stop and ask.

## Gate 5 — Verify from the VPS

```bash
curl -fsS http://127.0.0.1:8642/api/status
```

You should get a JSON status document. Then confirm the port is bound to the
Tailscale interface and nothing else:

```bash
docker compose port podcastsync 8642
```

The output must be `<VPS_TS_IP>:8642` — never `0.0.0.0:8642` or an empty
result. This is the check that the dashboard is private to the Tailnet.

## Gate 6 — Verify from the Mac over Tailscale

Ask the owner to open a terminal on their Mac (or run this yourself over the
Tailnet if you are on the Mac):

```bash
curl -fsS http://<VPS_TS_IP>:8642/api/status
```

Same JSON document, but reached across the Tailnet with no SSH tunnel and no
port forwarding. If this fails while the VPS-local check passed, the problem is
Tailscale reachability — check `tailscale status` on both machines and the
VPS's firewall before trying anything else. Do not "fix" it by binding Docker
to `0.0.0.0`.

## Gate 7 — First run with the owner (dashboard)

Walk the owner through this so they learn the tool:

1. Open the dashboard: `http://<VPS_TS_IP>:8642` in their browser on the Mac.
   Bookmark it.
2. Add one YouTube channel or playlist URL (paste a real one they want).
3. Press **Sync Now** and wait for at least one episode to show **Completed**
   and be playable. If nothing downloads or a download says "sign-in" is
   required, see the cookie step below.
4. In the source detail, copy the **RSS** feed URL and subscribe in a podcast
   app on the Mac (Apple Podcasts: File → Subscribe to Show by URL; or
   Downcast). Since everything is on the Tailnet, only podcast apps running on
   Tailnet-connected devices can fetch the feed.

## Optional — Public podcast feeds (Overcast, etc.)

If the owner wants **Overcast** or any other podcast client whose servers fetch
feeds from the public internet, the private Tailnet setup is not enough.
Explain that this requires a real domain, a DNS A record, and opening TCP 80
and 443 on the VPS, and that you will walk them through `docs/ORACLE_VPS_HANDOFF.md`
as a second phase if they want it. Do not silently make the feed public; do not
open port 8642 as a shortcut.

## Optional — YouTube sign-in cookies on the headless VPS

If a download requires YouTube sign-in (the dashboard will say so), a headless
VPS has no browser to pull cookies from. Ask the owner to export a
**Netscape-format `cookies.txt`** on their own machine and transfer it:

```bash
scp cookies.txt <user>@<VPS_TS_IP>:~/podcastsync/cookies.txt
```

Then, in the repo dir on the VPS:

```bash
cd ~/podcastsync
chmod 600 cookies.txt
docker compose -f docker-compose.yml -f docker-compose.cookies.yml up -d --build
docker compose exec -T podcastsync python -c '
import json, urllib.request
data = json.dumps({"cookies_file_path": "/data/cookies.txt"}).encode()
req = urllib.request.Request("http://127.0.0.1:8642/api/settings",
    data=data, headers={"Content-Type": "application/json"}, method="PATCH")
urllib.request.urlopen(req, timeout=5)'
```

Never print the cookie contents, commit the file, or bake it into an image.
Episodes that already failed stay failed until the owner re-downloads them.

## When you are done

Give the owner a short final summary containing:

- Dashboard URL: `http://<VPS_TS_IP>:8642` (Mac only, over Tailscale).
- Where their data lives: the `podcastsync-data` Docker volume (SQLite database
  and the `PodcastMirror` audio library). Back it up before any future update:
  `docker run --rm -v podcastsync-data:/data -v $(pwd):/backup alpine tar czf /backup/podcastsync-data-$(date +%F).tgz -C /data .`
- How to update later: replace the code (re-run the rsync from the Mac, or
  `git pull --ff-only` if the repo is a git checkout), then
  `docker compose up -d --build`. Never touch the existing `.env`.
- Logs and health: `docker compose logs -f podcastsync` and `docker compose ps`.
- A reminder to keep `.env` and `cookies.txt` private (mode `600`) and never to
  open port 8642 to the public internet.

Remember the hard rules at all times: never expose 8642 publicly, never print
or commit secrets, never alter DNS, firewall, or unrelated files, and always
stop and ask when something is uncertain.
