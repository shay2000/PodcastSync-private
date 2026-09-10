# PodcastSync

Turn YouTube channels into your own personal podcast.

PodcastSync watches YouTube channels you choose, saves the audio of new videos
as they come out, and turns them into a podcast you can listen to in any
podcast app — just like a normal podcast subscription, except you pick the
content.

You run it once on a server (a small rented computer in the cloud), and after
that it works on its own. It is private: only you can reach it.

## Don't want to do it yourself? Give this to your AI assistant

If you use an AI assistant that can run commands for you (Claude Code, Codex,
Cursor, Kilo, and the like), copy everything in the box below, paste it into a
chat with it, and it will set the whole thing up for you, checking with you
whenever it needs a decision. It works whether you and the assistant are
sitting on the server, or on your own computer while the server is elsewhere.

```text
Please set up PodcastSync for me on my server, following the repository's own
instructions exactly.

1. Find the PodcastSync repository on this machine (look for a folder
   containing an AGENTS.md file and a deploy/ folder), or clone it from
   https://github.com/shay2000/PodcastSync-private if it is not here yet.
2. Read AGENTS.md and README.md in that folder. They are the source of truth.
3. If the server is a different machine from this one, work over SSH; ask me
   for the SSH login when you need it.
4. Install and start PodcastSync with the repository's installer:
   deploy/linux/install.sh (run it as shown in README.md section "Setting it
   up", with --bind-ip set to the server's Tailscale address if we use
   Tailscale). Do not expose the dashboard to the public internet.
5. Verify the install the way the repository's own instructions say to
   (health check, then the dashboard over the private address).
6. Report back: the dashboard address to open, and what I should subscribe to
   in my podcast app.

Rules: never expose port 8642 to the public internet, never print or commit
secrets, and if anything fails, stop and tell me before trying a fix you
invented yourself.
```

## What it does

1. You add YouTube channels you like (for example, a cooking channel or a
   news channel).
2. PodcastSync quietly checks those channels for new videos.
3. When it finds one, it saves just the audio.
4. Your podcast app downloads new episodes automatically, like any podcast.

That's it. Subscribe once in your podcast app and new videos show up as
episodes by themselves.

## What you need before starting

- **A server** — a small cloud computer running Linux (any cheap one works).
  If you already have one set up with [Tailscale](https://tailscale.com) (a
  tool that lets your devices talk to each other privately over the
  internet), you are ready.
- **Docker installed on that server** — Docker is a tool that runs apps in
  tidy, self-contained packages. Your server provider or a tech-savvy friend
  can set this up in a few minutes.
- **10 minutes.**

No programming knowledge is needed beyond copying and pasting two commands.

## Setting it up

### Step 1 — Install PodcastSync on your server

Log in to your server, then run this one command (copy it exactly):

```bash
curl -fsSL https://raw.githubusercontent.com/shay2000/PodcastSync-private/main/deploy/linux/install.sh | bash
```

This downloads PodcastSync and starts it. When it finishes, you will see a
message saying it is running and healthy.

> Using Tailscale? Run the version below instead, replacing `100.x.y.z` with
> your server's Tailscale address (run `tailscale ip -4` on the server to see
> it). Then you can open PodcastSync from any of your devices on your Tailnet.

```bash
curl -fsSL https://raw.githubusercontent.com/shay2000/PodcastSync-private/main/deploy/linux/install.sh | bash -s -- --bind-ip 100.x.y.z
```

### Step 2 — Open the dashboard

Go to this address in your web browser:

```
http://127.0.0.1:8642
```

(or `http://100.x.y.z:8642` if you used the Tailscale version)

This is your PodcastSync dashboard — a simple web page where you manage
everything.

### Step 3 — Add a YouTube channel

1. On the dashboard, find the **Add Source** box.
2. Paste in the web address of a YouTube channel, for example
   `https://www.youtube.com/@cookingchannel`.
3. Give it a name (anything you like).
4. Click **Add**, then click **Sync Now**.

PodcastSync starts saving audio from that channel. The first sync can take a
little while if the channel has many videos.

### Step 4 — Subscribe in your podcast app

1. On the dashboard, click **Copy Feed URL** next to your channel.
2. In your podcast app (Apple Podcasts, Downcast, and most others work):
   - Apple Podcasts: **File → Subscribe to Show by URL**, then paste.
   - Other apps: look for "Add by URL" or "Subscribe by URL", then paste.

Done! New videos from that channel now appear in your podcast app
automatically, as audio-only episodes.

## Everyday use

- **Listen**: in your podcast app, like any other podcast.
- **Add more channels**: dashboard → Add Source.
- **Pause a channel**: open the channel on the dashboard and toggle it off.
- **Update PodcastSync**: log in to the server and re-run the same install
  command from Step 1. Your channels and saved episodes are kept.

## Optional extras

**Better video history (recommended).** Without extra setup, PodcastSync can
only see about the 15 most recent videos on a channel. A free
*YouTube API key* removes that limit and shows the full history. Get one at
the [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
(create a project → enable "YouTube Data API v3" → create an API key), then
paste it into the dashboard under **Settings**.

**Locked or members-only videos.** Very occasionally a video requires being
signed in to YouTube. For those, you can provide a "cookies file" — see
[HANDOFF.md](HANDOFF.md) for the details.

**Listening from podcast apps that live in the cloud** (like Overcast). Those
apps cannot reach a private server, so they need the extra public mode
described in [HANDOFF.md](HANDOFF.md). Apps like Apple Podcasts and Downcast
work without it.

## Good to know

- **It's private.** Only you can reach your PodcastSync and your saved audio.
  Do not share the dashboard address publicly.
- **Your podcasts depend on the server.** If the server is off, podcast apps
  can't fetch new episodes (already-downloaded episodes keep working).
- **Be patient with podcast apps.** They sometimes take up to an hour to
  notice new episodes.
- **Personal use only.** Please respect the rights of the people whose videos
  you save — keep it to yourself.

## For developers and tinkerers

Everything technical — the API, running it locally, the Docker image,
deployment runbooks — lives in [HANDOFF.md](HANDOFF.md) and
[AGENTS.md](AGENTS.md). The short version:

```bash
git clone https://github.com/shay2000/PodcastSync-private.git
cd PodcastSync-private
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"
python -m pytest tests/ -q      # offline test suite
./scripts/dev.sh               # dev server at http://127.0.0.1:8642
```

Releases are Docker images on GHCR (`ghcr.io/shay2000/podcastsync`), built
for amd64 and arm64 by CI on every `v*` tag.
