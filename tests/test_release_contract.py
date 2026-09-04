"""Static release-contract tests that run on the Linux development host.

The actual Swift, codesign, hdiutil, and PyInstaller execution belongs on the
macOS release runner. These tests keep the cross-platform shell/workflow
contracts from silently drifting before that runner is available.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_packaging_inventory_matches_backend_modules():
    script = read("scripts/build_backend.sh")
    listed = re.findall(r"--hidden-import\s+(backend(?:\.[A-Za-z_][\w]*)+)", script)

    assert listed, "build_backend.sh must list backend hidden imports"
    assert len(listed) == len(set(listed))
    for module in listed:
        module_path = ROOT / (module.replace(".", "/") + ".py")
        package_path = ROOT / module.replace(".", "/") / "__init__.py"
        assert module_path.is_file() or package_path.is_file(), (
            f"stale hidden import {module}; remove it or add the module"
        )

    assert "--collect-all feedgen" in script
    assert 'cp -r "$PROJECT_DIR/backend/static"' in script
    assert 'cp -r "$PROJECT_DIR/backend/migrations"' in script
    for trigger in (
        "apscheduler.triggers.interval",
        "apscheduler.triggers.date",
        "apscheduler.triggers.cron",
    ):
        assert f"--hidden-import {trigger}" in script, (
            f"add {trigger} to --hidden-import list in build_backend.sh"
        )


def test_build_app_fails_closed_for_packaging_inputs():
    script = read("scripts/build_app.sh")

    assert "command -v ffmpeg 2>/dev/null || true" in script
    assert "command -v ffprobe 2>/dev/null || true" in script
    assert "|| echo /opt/homebrew/bin/ffmpeg" not in script
    assert "|| echo /opt/homebrew/bin/ffprobe" not in script
    assert "PODCASTSYNC_ALLOW_LAUNCHER_FALLBACK" in script
    assert "PODCASTSYNC_ALLOW_LAUNCHER_FALLBACK:-0" in script
    assert "codesign --verify --deep --strict" in script
    assert "hdiutil attach -plist" in script
    assert "PlistBuddy" in script
    assert "trap " in script
    assert "NSHumanReadableCopyright" in script
    assert "LSApplicationCategoryType" in script


def test_version_check_script_accepts_matching_tag_and_rejects_mismatch():
    script = ROOT / "scripts/check_version.sh"
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


def test_release_workflow_is_explicit_and_reproducible():
    workflow = read(".github/workflows/build-release.yml")

    assert "macos-14" in workflow
    assert "default: v0.2.0" not in workflow
    assert "Check version consistency" in workflow
    assert "format('refs/tags/{0}', inputs.release_tag)" in workflow
    assert "retention-days: 30" in workflow
    assert "Smoke test packaged backend" in workflow
    assert "gh release upload" in workflow


def test_dependency_manifests_share_runtime_floors():
    pyproject = read("pyproject.toml")
    requirements = read("requirements.txt")

    for dependency in (
        '"yt-dlp>=2026.01.01"',
        '"mutagen>=1.47.0"',
    ):
        assert dependency in pyproject
        assert dependency.split('"')[1] in requirements


def test_ci_and_dependabot_contracts_exist():
    ci = read(".github/workflows/ci.yml")
    dependabot = read(".github/dependabot.yml")

    assert "pull_request" in ci
    assert 'python-version: ["3.10", "3.12"]' in ci
    assert "ruff check backend tests" in ci
    assert "python -m pytest tests/ -q" in ci
    assert 'package-ecosystem: "pip"' in dependabot
    assert 'package-ecosystem: "github-actions"' in dependabot
