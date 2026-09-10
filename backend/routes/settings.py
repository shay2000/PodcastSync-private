"""Application settings API routes."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import APIRouter, Request

from backend.models import SettingsResponse, SettingsUpdate

router = APIRouter()


def settings_to_response(settings) -> dict:
    """Serialize settings without exposing the YouTube API key."""
    return {
        "youtube_api_key_set": bool(settings.youtube_api_key),
        "poll_interval_minutes": settings.poll_interval_minutes,
        "storage_path": str(settings.storage_path),
        "server_port": settings.server_port,
        "base_url": settings.base_url,
        "public_url": settings.public_url,
        "cookies_from_browser": settings.cookies_from_browser,
        "cookies_file_path": settings.cookies_file_path,
        "cookies_file_available": bool(
            settings.cookies_file_path and Path(settings.cookies_file_path).is_file()
        ),
    }


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(request: Request) -> dict:
    return settings_to_response(request.app.state.settings)


@router.post("/pick-directory")
async def pick_directory() -> dict:
    """Open a native macOS folder picker and return its selected path."""
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'POSIX path of (choose folder with prompt "Select download folder")',
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        path = result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        path = None
    return {"path": path}


def _apply_setting(request: Request, key: str, value) -> None:
    """Persist one settings field to app state and the database.

    Field-specific side effects (API-key forwarding to the orchestrator,
    scheduler rescheduling) are handled here so the PATCH route stays flat.
    ``key`` comes from ``SettingsUpdate.model_dump``, so it is always a known
    settings field.
    """
    db = request.app.state.db
    settings = request.app.state.settings

    setattr(settings, key, value)
    db.set_setting(key, str(value))

    if key == "youtube_api_key":
        request.app.state.orchestrator.update_api_key(value)
    elif key == "poll_interval_minutes":
        scheduler = getattr(request.app.state, "scheduler", None)
        if scheduler and scheduler.running:
            from backend.scheduler import reschedule_poll

            reschedule_poll(scheduler, settings.poll_interval_minutes)


@router.patch("/settings", response_model=SettingsResponse)
async def update_settings(body: SettingsUpdate, request: Request) -> dict:
    settings = request.app.state.settings

    # exclude_unset keeps PATCH partial; explicitly-sent nulls are skipped,
    # matching the original per-field "is not None" guards.
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    for key, value in updates.items():
        _apply_setting(request, key, value)

    return settings_to_response(settings)
