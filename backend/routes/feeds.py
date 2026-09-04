"""RSS feed routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from backend.rss_generator import generate_feed
from backend.services.sources import source_dto

router = APIRouter()


def _feed_base_url(request: Request) -> str:
    """Use the configured public origin, falling back to the request origin."""
    settings = request.app.state.settings
    if settings.public_url:
        return settings.base_url
    return str(request.base_url).rstrip("/")


@router.get("/feed/{source_id}.xml")
async def get_feed(source_id: int, request: Request) -> Response:
    """Serve the podcast RSS feed for a specific source."""
    db = request.app.state.db

    source = db.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    base_url = _feed_base_url(request)
    videos = db.get_completed_videos_for_source(source_id)
    xml = generate_feed(source, videos, base_url)

    return Response(
        content=xml,
        media_type="application/rss+xml",
        headers={"Cache-Control": "max-age=300"},
    )


@router.get("/feeds")
async def list_feeds(request: Request) -> list[dict]:
    """List all available feeds with their URLs."""
    db = request.app.state.db

    base_url = _feed_base_url(request)
    sources = db.get_all_sources()
    feeds = []
    for s in sources:
        dto = source_dto(db, s)
        feeds.append(
            {
                "id": dto["id"],
                "name": dto["name"],
                "source_type": dto["source_type"],
                "enabled": dto["enabled"],
                "feed_url": f"{base_url}/feed/{dto['id']}.xml",
                "video_count": dto["video_count"],
                "completed_count": dto["completed_count"],
            }
        )
    return feeds
