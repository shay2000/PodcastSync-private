"""Pydantic models for API request/response and internal dataclasses."""

from __future__ import annotations

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# API request / response models
# ---------------------------------------------------------------------------


class SourceCreate(BaseModel):
    url: str = Field(..., description="YouTube channel or playlist URL")
    name: str = Field("", description="Custom label (auto-generated if blank)")
    max_backfill: int = Field(15, ge=1, le=50, description="Max past episodes on first sync")
    custom_storage_path: str | None = Field(
        None, description="Override download folder (absolute path)"
    )
    max_keep_episodes: int | None = Field(
        None, ge=1, description="Rolling delete: keep only this many downloaded episodes"
    )


class SourceUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    max_backfill: int | None = Field(None, ge=1, le=50)
    custom_storage_path: str | None = None
    max_keep_episodes: int | None = Field(None, ge=1)


class SourceResponse(BaseModel):
    id: int
    name: str
    source_type: str
    youtube_id: str
    url: str
    enabled: bool
    max_backfill: int
    last_polled_at: str | None
    video_count: int = 0
    completed_count: int = 0
    created_at: str
    custom_storage_path: str | None = None
    icon_url: str | None = None
    max_keep_episodes: int | None = None


class VideoResponse(BaseModel):
    id: int
    video_id: str
    title: str
    description: str
    publish_date: str | None
    duration_seconds: int | None
    download_status: str
    file_size: int | None
    error_message: str | None
    created_at: str


class StatusResponse(BaseModel):
    server_running: bool = True
    next_poll: str | None = None
    last_poll: str | None = None
    download_queue_size: int = 0
    active_downloads: int = 0


class SettingsResponse(BaseModel):
    youtube_api_key_set: bool
    poll_interval_minutes: int
    storage_path: str
    server_port: int
    base_url: str
    public_url: str = ""
    cookies_from_browser: str = ""
    cookies_file_path: str = ""
    cookies_file_available: bool = False


class SettingsUpdate(BaseModel):
    youtube_api_key: str | None = None
    poll_interval_minutes: int | None = Field(None, ge=1, le=1440)
    cookies_from_browser: str | None = None
    cookies_file_path: str | None = None
