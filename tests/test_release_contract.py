"""Static release-contract tests.

These keep the cross-platform shell/workflow contracts from silently drifting
before a release runs: the Linux install script, the version guard, the
Docker/GHCR release workflow, and the dependency manifests.

The actual Docker build, image push, and container smoke test belong to the
release workflow itself.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_version_check_script_accepts_matching_tag_and_rejects_mismatch():
    script = ROOT / "scripts" / "check_version.sh"
    assert script.is_file()

    pyproject_version = re.search(r'^version = "([^"]+)"', read("pyproject.toml"), re.MULTILINE)
    assert pyproject_version, "pyproject.toml must define a project version"

    matching = subprocess.run(
        [str(script), f"v{pyproject_version.group(1)}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    mismatch = subprocess.run(
        [str(script), "v9.9.9"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert matching.returncode == 0, matching.stderr
    assert mismatch.returncode != 0
    assert "does not match" in mismatch.stderr


def test_release_workflow_builds_and_publishes_docker_image():
    workflow = read(".github/workflows/build-release.yml")

    assert "runs-on: ubuntu-latest" in workflow
    assert "default: v0.2.0" not in workflow
    assert "Check version consistency" in workflow
    assert "format('refs/tags/{0}', inputs.release_tag)" in workflow
    assert "retention-days: 30" in workflow
    assert "gh release upload" in workflow

    # The release artifact is a Docker image on GHCR, built for both VPS arches.
    assert "packages: write" in workflow
    assert "docker/build-push-action" in workflow
    assert "linux/amd64,linux/arm64" in workflow
    # A release must be verified by actually running the container.
    assert "Smoke test the built image" in workflow
    assert "api/status" in workflow
    # No macOS packaging steps may return.
    for banned in ("macos-14", "build_app.sh", "hdiutil", "codesign", "PyInstaller"):
        assert banned not in workflow, f"{banned} must not appear in the release workflow"


def test_linux_install_script_downloads_release_files_and_start_containers():
    script = read("deploy/linux/install.sh")

    # Installs from raw.githubusercontent, into a predictable directory.
    assert "raw.githubusercontent.com" in script
    assert "docker-compose.yml" in script
    assert "docker-compose.cookies.yml" in script
    assert ".env.example" in script
    assert "Caddyfile.docker" in script
    # Fails closed on missing Docker / Compose plugin / daemon access.
    assert "Docker is not installed" in script
    assert "the Docker Compose plugin is not available" in script
    assert "Docker is not running" in script
    # Never binds the dashboard publicly by default.
    assert "--bind-ip)" in script
    assert 'bind_ip="127.0.0.1"' in script
    assert "0.0.0.0" not in script
    # Idempotent: keeps an existing .env, fetches fresh compose files.
    assert ".env already exists; leaving it unchanged" in script
    # Verifies the container became healthy before declaring success.
    assert '"Health":"healthy"' in script
    assert "docker compose logs" in script


def test_packaging_inventory_has_no_macos_leftovers():
    # The Swift app, PyInstaller bundling, and DMG assembly are gone for good.
    for banned in (
        "macos",
        "debug_app.sh",
        "scripts/build_app.sh",
        "scripts/build_backend.sh",
        "scripts/bundle_macos_tool.sh",
        "scripts/generate_app_icon.swift",
    ):
        assert not (ROOT / banned).exists(), f"{banned} still exists"

    # The runtime code has no frozen-bundle code paths left.
    for py_file in (ROOT / "backend").rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        assert "_MEIPASS" not in text, f"{py_file} still references PyInstaller"
        assert "quarantine" not in text.lower(), f"{py_file} still clears macOS quarantine"
        assert "osascript" not in text, f"{py_file} still shells out to macOS"


def test_dependency_manifests_share_runtime_floors():
    pyproject = read("pyproject.toml")
    requirements = read("requirements.txt")

    for dependency in (
        '"yt-dlp>=2026.01.01"',
        '"mutagen>=1.47.0"',
    ):
        assert dependency in pyproject
        assert dependency.split('"')[1] in requirements

    # PyInstaller was a build-only dep for the removed macOS bundle.
    assert "pyinstaller" not in requirements.lower()
    assert "pyinstaller" not in pyproject.lower()


def test_ci_and_dependabot_contracts_exist():
    ci = read(".github/workflows/ci.yml")
    dependabot = read(".github/dependabot.yml")

    assert "pull_request" in ci
    assert 'python-version: ["3.10", "3.12"]' in ci
    assert "ruff check backend tests" in ci
    assert "python -m pytest tests/ -q" in ci
    assert 'package-ecosystem: "pip"' in dependabot
    assert 'package-ecosystem: "github-actions"' in dependabot
