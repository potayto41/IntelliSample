"""Audius-backed music search and normalization helpers."""

from __future__ import annotations

import os

try:
    import httpx
except Exception:  # pragma: no cover - optional runtime dependency
    httpx = None

AUDIOUS_BASE_URL = "https://discoveryprovider.audius.co"
AUDIOUS_APP_NAME = os.getenv("AUDIOUS_APP_NAME", "sampleforge")
AUDIOUS_API_KEY = os.getenv("AUDIOUS_API_KEY", "")
AUDIOUS_BEARER_TOKEN = os.getenv("AUDIOUS_BEARER_TOKEN", "")
REQUEST_TIMEOUT = 12.0
MAX_RESULTS = 12

HOME_QUERIES = [
    ("Trending", "trending"),
    ("Lo-fi", "lofi"),
    ("Ambient", "ambient"),
    ("Electronic", "electronic"),
    ("Focus", "focus"),
]

FALLBACK_SONGS = [
    {
        "id": "fallback-1",
        "title": "SampleForge Chill Stream",
        "artist": "Fallback Radio",
        "artwork": "https://images.pexels.com/photos/164938/pexels-photo-164938.jpeg?auto=compress&cs=tinysrgb&w=800",
        "stream_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
        "duration": 0,
        "tags": ["chill", "focus", "fallback"],
    },
    {
        "id": "fallback-2",
        "title": "Deep Focus Pulse",
        "artist": "Fallback Radio",
        "artwork": "https://images.pexels.com/photos/164745/pexels-photo-164745.jpeg?auto=compress&cs=tinysrgb&w=800",
        "stream_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
        "duration": 0,
        "tags": ["focus", "ambient", "fallback"],
    },
    {
        "id": "fallback-3",
        "title": "Night Drive Textures",
        "artist": "Fallback Radio",
        "artwork": "https://images.pexels.com/photos/270348/pexels-photo-270348.jpeg?auto=compress&cs=tinysrgb&w=800",
        "stream_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
        "duration": 0,
        "tags": ["electronic", "night", "fallback"],
    },
    {
        "id": "fallback-4",
        "title": "Ambient Space Bloom",
        "artist": "Fallback Radio",
        "artwork": "https://images.pexels.com/photos/2150/sky-space-dark-galaxy.jpg?auto=compress&cs=tinysrgb&w=800",
        "stream_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3",
        "duration": 0,
        "tags": ["space", "ambient", "fallback"],
    },
    {
        "id": "fallback-5",
        "title": "Minimal Morning Flow",
        "artist": "Fallback Radio",
        "artwork": "https://images.pexels.com/photos/417173/pexels-photo-417173.jpeg?auto=compress&cs=tinysrgb&w=800",
        "stream_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-5.mp3",
        "duration": 0,
        "tags": ["morning", "minimal", "fallback"],
    },
]


def _request_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if AUDIOUS_API_KEY:
        headers["x-api-key"] = AUDIOUS_API_KEY
    if AUDIOUS_BEARER_TOKEN:
        headers["Authorization"] = f"Bearer {AUDIOUS_BEARER_TOKEN}"
    return headers


def _resolve_artwork(track: dict) -> str:
    artwork = track.get("artwork") or {}
    if isinstance(artwork, dict):
        return (
            artwork.get("480x480")
            or artwork.get("1000x1000")
            or artwork.get("150x150")
            or ""
        )
    return ""


def normalize_audius_response(data: list[dict]) -> dict[str, list[dict]]:
    """Normalize Audius payload to the UI contract used by Music Wall."""
    songs: list[dict] = []

    for item in data:
        track_id = item.get("id")
        if not track_id:
            continue

        stream_url = ((item.get("stream") or {}).get("url") or "").strip()
        if not stream_url:
            stream_url = f"{AUDIOUS_BASE_URL}/v1/tracks/{track_id}/stream?app_name={AUDIOUS_APP_NAME}"

        songs.append(
            {
                "id": str(track_id),
                "title": item.get("title", "Untitled"),
                "artist": (item.get("user") or {}).get("name", "Unknown artist"),
                "artwork": _resolve_artwork(item),
                "stream_url": stream_url,
                "duration": int(item.get("duration") or 0),
            }
        )

        if len(songs) >= MAX_RESULTS:
            break

    return {"songs": songs}


async def fetch_from_audius(query: str, limit: int = MAX_RESULTS) -> list[dict]:
    """Fetch raw track results from Audius search endpoint."""
    if not query.strip() or httpx is None:
        return []

    params = {
        "query": query,
        "limit": max(1, min(limit, MAX_RESULTS)),
        "app_name": AUDIOUS_APP_NAME,
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=_request_headers()) as client:
            response = await client.get(f"{AUDIOUS_BASE_URL}/v1/tracks/search", params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return []

    data = payload.get("data", []) if isinstance(payload, dict) else []
    return data if isinstance(data, list) else []


def fallback_search(query: str) -> dict[str, list[dict]]:
    """Local fallback when Audius is unavailable or returns no results."""
    q = (query or "").strip().lower()
    if not q:
        return {"songs": FALLBACK_SONGS[:MAX_RESULTS]}

    filtered = []
    for song in FALLBACK_SONGS:
        haystack = " ".join(
            [
                song.get("title", ""),
                song.get("artist", ""),
                " ".join(song.get("tags", [])),
            ]
        ).lower()
        if q in haystack:
            filtered.append(song)

    return {"songs": filtered[:MAX_RESULTS]}
