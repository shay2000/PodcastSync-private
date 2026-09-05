"""Deterministic contract tests for the Phase 6 V3 Docker packaging.

These tests inspect the committed Docker artifacts (``Dockerfile``,
``docker-compose.yml``, ``deploy/caddy/Caddyfile``) as static text and assert
the safety and integration requirements of Phase 6 V3 (docs/implementation/
phase6-vps.md):

* ``Dockerfile`` — Python 3.12 slim base; apt installs only ffmpeg and
  ``ca-certificates`` with ``--no-install-recommends``; runtime dependencies are
  filtered from ``requirements.txt`` so build-only PyInstaller is excluded;
  only the ``backend`` package is copied into the image; the app runs as a
  non-root ``podcastsync`` user with a writable ``/data``; port 8642 is
  exposed; the healthcheck uses Python (no curl anywhere); the CMD starts
  ``backend.main:app`` under uvicorn on ``0.0.0.0:8642`` with proxy-header
  trust only from ``127.0.0.1``.
* ``docker-compose.yml`` — safe by default: named persistent ``/data`` volume,
  ``restart: unless-stopped``, the host port defaults to ``127.0.0.1`` and can
  only be overridden with an explicit bind address, and PUBLIC_URL / API key /
  poll interval come from host environment variables (``${...}``) so no
  secret is embedded in the file.
* ``deploy/caddy/Caddyfile`` — reverse-proxies a placeholder domain to
  ``127.0.0.1:8642`` and documents that TLS must be configured before the site
  is exposed publicly; the Docker Caddyfile has the equivalent service-name
  proxy and only exposes feed/audio paths.

Nothing here starts Docker or makes network calls: the files are read straight
from the repository root.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DOCKERFILE = ROOT / "Dockerfile"
COMPOSE = ROOT / "docker-compose.yml"
COOKIES_COMPOSE = ROOT / "docker-compose.cookies.yml"
CADDYFILE = ROOT / "deploy" / "caddy" / "Caddyfile"
DOCKER_CADDYFILE = ROOT / "deploy" / "caddy" / "Caddyfile.docker"
ENV_EXAMPLE = ROOT / ".env.example"


def _text(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"{path} does not exist")
    return path.read_text(encoding="utf-8")


def _logical_lines(path: Path) -> list[str]:
    """Lines with ``\\`` continuations joined, blank lines and comments dropped."""
    logical: list[str] = []
    buf = ""
    for raw in _text(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        buf = line if not buf else f"{buf} {line}"
        if not line.endswith("\\"):
            logical.append(buf)
            buf = ""
    if buf:
        logical.append(buf)
    return logical


def _docker_instructions(name: str) -> list[str]:
    return [ln for ln in _logical_lines(DOCKERFILE) if re.match(rf"^{name}\b", ln)]


def _docker_instruction(name: str) -> str:
    matches = _docker_instructions(name)
    if not matches:
        raise AssertionError(f"Dockerfile has no {name} instruction")
    return matches[-1]


def _cmd_tokens() -> list[str]:
    rest = _docker_instruction("CMD").removeprefix("CMD").strip()
    if rest.startswith("["):
        return json.loads(rest)
    return shlex.split(rest)


# --- Dockerfile: base image and apt packages ---------------------------------


def test_dockerfile_uses_python_312_slim_base():
    froms = _docker_instructions("FROM")
    assert any("python:3.12-slim" in ln for ln in froms), f"FROM lines: {froms}"


def test_dockerfile_apt_installs_only_ffmpeg_and_ca_certificates():
    text = "\n".join(_logical_lines(DOCKERFILE))
    matches = re.findall(r"apt-get\s+install\b([^&\n]*)", text)
    assert matches, "no apt-get install command found"
    installed: set[str] = set()
    for args in matches:
        for chunk in re.findall(
            r"--no-install-recommends\s+([a-z0-9\-]+(?:\s+[a-z0-9\-]+)*)",
            args,
        ):
            installed.update(chunk.split())
    assert installed == {"ffmpeg", "ca-certificates"}, (
        f"apt packages installed: {sorted(installed)}"
    )


def test_dockerfile_apt_uses_no_install_recommends_and_cleans_lists():
    text = "\n".join(_logical_lines(DOCKERFILE))
    assert "--no-install-recommends" in text
    assert "rm -rf /var/lib/apt/lists" in text


# --- Dockerfile: Python dependencies and copied content -----------------------


def test_dockerfile_installs_runtime_requirements_without_build_tools():
    run_lines = [ln for ln in _logical_lines(DOCKERFILE) if ln.startswith("RUN ")]
    install_lines = [ln for ln in run_lines if "pip install" in ln]
    assert install_lines, "no RUN installs Python requirements"
    assert any("requirements-runtime.txt" in ln for ln in install_lines)
    assert any("--no-cache-dir" in ln for ln in install_lines)
    assert not any(re.search(r"pip install .* -r requirements\.txt", ln) for ln in install_lines)
    assert any("grep -viE" in ln and "pyinstaller" in ln for ln in run_lines), (
        "runtime image must filter the build-only PyInstaller dependency"
    )


def test_dockerfile_copies_only_the_backend_application():
    text = _text(DOCKERFILE)
    assert re.search(r"^COPY\s+backend\s+\S*backend\s*$", text, re.MULTILINE), (
        "the backend package must be copied into the image"
    )
    for forbidden in (
        r"^COPY\s+\.\s",
        r"^COPY\s+tests\b",
        r"^COPY\s+scripts\b",
        r"^COPY\s+docs\b",
        r"^COPY\s+macos\b",
        r"^COPY\s+README",
    ):
        assert not re.search(forbidden, text, re.MULTILINE), (
            f"forbidden broad COPY found: {forbidden!r}"
        )


# --- Dockerfile: data directories, user, port ---------------------------------


def test_dockerfile_points_data_envs_at_writable_data():
    env = _docker_instruction("ENV")
    assert "PODCASTSYNC_DB=/data/podcastsync.db" in env
    assert "PODCASTSYNC_STORAGE=/data/PodcastMirror" in env
    assert "PODCASTSYNC_PORT=8642" in env


def test_dockerfile_runs_as_nonroot_podcastsync_user():
    run_lines = [ln for ln in _logical_lines(DOCKERFILE) if ln.startswith("RUN ")]
    useradd = [ln for ln in run_lines if "useradd" in ln or "adduser" in ln]
    assert useradd, "no useradd/adduser found"
    assert all("podcastsync" in ln for ln in useradd)
    user_instructions = [ln for ln in _logical_lines(DOCKERFILE) if ln.startswith("USER ")]
    assert user_instructions and user_instructions[-1] == "USER podcastsync", (
        f"last USER must be podcastsync, got {user_instructions}"
    )
    last_useradd = max(i for i, ln in enumerate(_logical_lines(DOCKERFILE)) if "useradd" in ln)
    last_user = max(i for i, ln in enumerate(_logical_lines(DOCKERFILE)) if ln.startswith("USER "))
    assert last_useradd < last_user, "USER podcastsync must come after the user is created"


def test_dockerfile_gives_podcastsync_a_writable_data_directory():
    run_lines = [ln for ln in _logical_lines(DOCKERFILE) if ln.startswith("RUN ")]
    assert any("mkdir" in ln and "/data" in ln for ln in run_lines), "no mkdir for /data"
    chowns = [ln for ln in run_lines if "chown" in ln and "/data" in ln]
    assert chowns, "no chown making /data writable"
    assert all("podcastsync" in ln for ln in chowns)


def test_dockerfile_exposes_port_8642():
    exposes = _docker_instructions("EXPOSE")
    assert any("8642" in ln for ln in exposes), f"EXPOSE lines: {exposes}"


# --- Dockerfile: CMD and healthcheck ------------------------------------------


def test_dockerfile_cmd_starts_uvicorn_on_all_interfaces_with_proxy_headers():
    tokens = _cmd_tokens()
    assert "uvicorn" in tokens and "backend.main:app" in tokens
    assert tokens[:2] == ["python", "-m"], f"CMD must run python -m uvicorn: {tokens}"
    assert "--host" in tokens and tokens[tokens.index("--host") + 1] == "0.0.0.0"
    assert "--port" in tokens and tokens[tokens.index("--port") + 1] == "8642"
    assert "--proxy-headers" in tokens


def test_dockerfile_cmd_trusts_proxy_headers_only_from_loopback():
    tokens = _cmd_tokens()
    assert "--forwarded-allow-ips" in tokens
    trusted = tokens[tokens.index("--forwarded-allow-ips") + 1]
    assert trusted == "127.0.0.1", f"forwarded-allow-ips must be 127.0.0.1, got {trusted!r}"
    assert "*" not in trusted


def test_dockerfile_healthcheck_uses_python_not_curl():
    healthchecks = _docker_instructions("HEALTHCHECK")
    assert healthchecks, "no HEALTHCHECK instruction"
    for hc in healthchecks:
        assert "python" in hc, f"healthcheck must use python: {hc}"
        assert "/api/status" in hc
    text = _text(DOCKERFILE)
    assert "curl" not in text, "curl must not appear anywhere in the Dockerfile"
    assert not re.search(r"^COPY\s+.+cookies", text, re.MULTILINE), (
        "no cookies file may be copied into the image"
    )


# --- docker-compose.yml: safe-by-default shape ---------------------------------


def test_compose_defines_podcastsync_service_built_from_context():
    text = _text(COMPOSE)
    assert re.search(r"^services:\s*$", text, re.MULTILINE)
    assert re.search(r"^  podcastsync:\s*$", text, re.MULTILINE)
    assert re.search(r"^    build:\s*\.\s*$", text, re.MULTILINE)


def test_compose_restarts_unless_stopped():
    assert re.search(r"^\s*restart:\s*unless-stopped\s*$", _text(COMPOSE), re.MULTILINE)


def test_compose_binds_host_port_to_explicit_safe_interface():
    text = _text(COMPOSE)
    assert re.search(
        r'^\s*-\s*"\$\{PODCASTSYNC_BIND_IP:-127\.0\.0\.1\}:8642:8642"\s*$',
        text,
        re.MULTILINE,
    ), (
        "port must default to loopback and require an explicit bind address override"
    )
    for banned in (
        r'^\s*-\s*"8642:8642"\s*$',
        r'^\s*-\s*"0\.0\.0\.0:8642:8642"\s*$',
        r"^\s*-\s*8642:8642\s*$",
        r"^\s*-\s*0\.0\.0\.0:8642:8642\s*$",
    ):
        assert not re.search(banned, text, re.MULTILINE), f"dangerous publish found: {banned!r}"


def test_compose_uses_named_volume_for_data():
    text = _text(COMPOSE)
    assert re.search(r"^\s*-\s*podcastsync-data:/data\s*$", text, re.MULTILINE), (
        "service must mount the named volume at /data"
    )
    services_idx = text.index("services:")
    volumes_idx = text.index("volumes:")
    assert services_idx < volumes_idx, "volumes: must come after services:"
    assert re.search(r"^volumes:\s*$", text, re.MULTILINE)
    assert re.search(r"^  podcastsync-data:\s*$", text, re.MULTILINE), (
        "podcastsync-data must be declared as a named volume"
    )


def test_cookie_compose_override_mounts_gitignored_file_read_only():
    text = _text(COOKIES_COMPOSE)
    assert re.search(
        r"^\s*-\s*\./cookies\.txt:/data/cookies\.txt:ro\s*$", text, re.MULTILINE
    )
    assert "cookies.txt" in _text(ROOT / ".gitignore")


def test_compose_environment_is_interpolated_and_contains_no_secrets():
    text = _text(COMPOSE)
    for key, pattern in [
        (
            "PODCASTSYNC_PUBLIC_URL",
            r"^\s*-\s*PODCASTSYNC_PUBLIC_URL=\$\{PODCASTSYNC_PUBLIC_URL:\?set to https://your.domain\}\s*$",
        ),
        (
            "YOUTUBE_API_KEY",
            r"^\s*-\s*YOUTUBE_API_KEY=\$\{YOUTUBE_API_KEY:-\}\s*$",
        ),
        (
            "PODCASTSYNC_POLL_INTERVAL",
            r"^\s*-\s*PODCASTSYNC_POLL_INTERVAL=\$\{PODCASTSYNC_POLL_INTERVAL:-30\}\s*$",
        ),
    ]:
        assert re.search(pattern, text, re.MULTILINE), f"expected env entry for {key}"
    env_entries = re.findall(r"^\s*-\s*([A-Z0-9_]+)=(.*)$", text, re.MULTILINE)
    assert env_entries, "no environment entries found"
    for key, value in env_entries:
        assert value.startswith("${") and value.endswith("}"), (
            f"environment value for {key} must come from the host env, got {value!r}"
        )
    assert "AIza" not in text, "looks like a real YouTube API key was committed"


def test_compose_has_no_curl_based_healthcheck_and_no_cookies():
    text = _text(COMPOSE)
    assert "curl" not in text
    assert "cookies" not in text


def test_compose_public_profile_publishes_only_caddy_ports():
    text = _text(COMPOSE)
    assert re.search(r"^\s*profiles:\s*\[\"public\"\]\s*$", text, re.MULTILINE)
    assert re.search(r'^\s*-\s*"80:80"\s*$', text, re.MULTILINE)
    assert re.search(r'^\s*-\s*"443:443"\s*$', text, re.MULTILINE)
    assert "./deploy/caddy/Caddyfile.docker:/etc/caddy/Caddyfile:ro" in text
    assert "PODCASTSYNC_DOMAIN=${PODCASTSYNC_DOMAIN:-}" in text
    assert "caddy-data:/data" in text and "caddy-config:/config" in text


def test_docker_caddyfile_routes_only_public_feed_and_audio_paths():
    text = _text(DOCKER_CADDYFILE)
    assert "{$PODCASTSYNC_DOMAIN}" in text
    assert re.search(r"^\s*@public path /feed/\* /audio/\*\s*$", text, re.MULTILINE)
    assert re.search(r"^\s*reverse_proxy podcastsync:8642\s*$", text, re.MULTILINE)
    assert 'respond "Not found" 404' in text
    assert not re.search(
        r"^\s*reverse_proxy\s+(?!podcastsync:8642\s*$).+$", text, re.MULTILINE
    )


def test_env_example_contains_setup_placeholders_not_credentials():
    text = _text(ENV_EXAMPLE)
    assert "PODCASTSYNC_DOMAIN=podcast.example.com" in text
    assert "PODCASTSYNC_PUBLIC_URL=https://podcast.example.com" in text
    assert re.search(r"^YOUTUBE_API_KEY=\s*$", text, re.MULTILINE)
    assert "AIza" not in text


# --- deploy/caddy/Caddyfile ----------------------------------------------------


def test_caddyfile_proxies_placeholder_domain_to_loopback_backend():
    text = _text(CADDYFILE)
    assert re.search(r"^[A-Za-z0-9.\-]*example\.com\s*\{\s*$", text, re.MULTILINE), (
        "Caddyfile must use a placeholder domain ending in example.com"
    )
    assert re.search(r"^\s*reverse_proxy\s+127\.0\.0\.1:8642\s*$", text, re.MULTILINE)


def test_caddyfile_documents_tls_before_public_exposure():
    lower = _text(CADDYFILE).lower()
    assert "tls" in lower, "Caddyfile must mention TLS"
    assert "public" in lower, "Caddyfile must mention public exposure"


# --- Cross-file integration contracts ------------------------------------------


def test_port_8642_is_consistent_across_artifacts():
    docker = _text(DOCKERFILE)
    assert re.search(r"^EXPOSE\s+8642\b", docker, re.MULTILINE)
    tokens = _cmd_tokens()
    assert "--port" in tokens and tokens[tokens.index("--port") + 1] == "8642"
    assert "${PODCASTSYNC_BIND_IP:-127.0.0.1}:8642:8642" in _text(COMPOSE)
    assert "127.0.0.1:8642" in _text(CADDYFILE)


def test_volume_target_matches_container_data_envs():
    compose = _text(COMPOSE)
    dockerfile = _text(DOCKERFILE)
    assert re.search(r"^\s*-\s*podcastsync-data:/data\s*$", compose, re.MULTILINE)
    assert "PODCASTSYNC_DB=/data/podcastsync.db" in dockerfile
    assert "PODCASTSYNC_STORAGE=/data/PodcastMirror" in dockerfile


def test_loopback_only_publish_complements_loopback_proxy_trust():
    dockerfile = _text(DOCKERFILE)
    compose = _text(COMPOSE)
    assert "${PODCASTSYNC_BIND_IP:-127.0.0.1}:8642:8642" in compose
    assert "--forwarded-allow-ips" in dockerfile
    assert "127.0.0.1" in dockerfile
    assert "0.0.0.0:8642:8642" not in compose
