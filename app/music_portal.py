"""Piped-backed music search and normalization helpers."""

from __future__ import annotations

import random
from urllib.parse import parse_qs, urlparse

try:
    import httpx
except Exception:  # pragma: no cover - optional runtime dependency
    httpx = None

from .config.piped import MAX_RESULTS, PIPED_INSTANCES, REQUEST_TIMEOUT

HOME_QUERIES = [
    ("Trending", "lofi hip hop"),
    ("Ambient", "ambient music"),
    ("Nature", "nature sounds"),
    ("Focus", "deep focus music"),
    ("Space", "space ambient"),
]

FALLBACK_SONGS = [
    {"video_id": "5qap5aO4i9A", "title": "Lofi Hip Hop Radio", "thumbnail": "https://img.youtube.com/vi/5qap5aO4i9A/hqdefault.jpg", "channel": "Lofi Girl", "duration": 0, "tags": ["lofi", "hip hop", "focus", "trending"]},
    {"video_id": "DWcJFNfaw9c", "title": "Deep Focus Music", "thumbnail": "https://img.youtube.com/vi/DWcJFNfaw9c/hqdefault.jpg", "channel": "Yellow Brick Cinema", "duration": 0, "tags": ["focus", "study", "ambient"]},
    {"video_id": "eKFTSSKCzWA", "title": "Relaxing Nature Sounds", "thumbnail": "https://img.youtube.com/vi/eKFTSSKCzWA/hqdefault.jpg", "channel": "Relaxation Film", "duration": 0, "tags": ["nature", "ambient", "sleep"]},
    {"video_id": "zSWdZVtXT7E", "title": "Interstellar Theme", "thumbnail": "https://img.youtube.com/vi/zSWdZVtXT7E/hqdefault.jpg", "channel": "Hans Zimmer", "duration": 0, "tags": ["space", "ambient"]},
    {"video_id": "1ZYbU82GVz4", "title": "Nature Relaxation Music", "thumbnail": "https://img.youtube.com/vi/1ZYbU82GVz4/hqdefault.jpg", "channel": "Relax Channel", "duration": 0, "tags": ["nature", "relax"]},
]


def _extract_video_id(url: str) -> str:
    if not url:
        return ""

    parsed = urlparse(url)
    query_video_id = parse_qs(parsed.query).get("v", [""])[0]
    if query_video_id:
        return query_video_id

    path = parsed.path.strip("/")
    if path.startswith("watch/"):
        return path.split("watch/", 1)[1]
    if path:
        return path.split("/")[-1]
    return ""


async def fetch_from_piped(query: str) -> list[dict]:
    """Fetch raw results from available Piped instances with failover."""
    instances = PIPED_INSTANCES[:]
    random.shuffle(instances)

    if not query.strip() or httpx is None:
        return []

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for instance in instances:
            try:
                response = await client.get(
                    f"{instance}/api/v1/search",
                    params={"q": query, "filter": "videos"},
                )
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, list):
                    return payload
            except Exception:
                continue

    return []


def normalize_piped_response(data: list[dict]) -> dict[str, list[dict]]:
    """Normalize Piped payload to the UI contract."""
    songs: list[dict] = []

    for item in data:
        if item.get("type") != "video":
            continue

        video_id = _extract_video_id(item.get("url", ""))
        if not video_id:
            continue

        songs.append(
            {
                "video_id": video_id,
                "title": item.get("title", "Untitled"),
                "thumbnail": item.get("thumbnail", ""),
                "channel": item.get("uploaderName", "Unknown channel"),
                "duration": item.get("duration", 0),
            }
        )
        if len(songs) >= MAX_RESULTS:
            break

    return {"songs": songs}


def fallback_search(query: str) -> dict[str, list[dict]]:
    """Local fallback when all Piped instances fail."""
    q = (query or "").strip().lower()
    if not q:
        return {"songs": FALLBACK_SONGS[:MAX_RESULTS]}

    filtered = []
    for song in FALLBACK_SONGS:
        haystack = " ".join([song.get("title", ""), song.get("channel", ""), " ".join(song.get("tags", []))]).lower()
        if q in haystack:
            filtered.append(song)

    return {"songs": filtered[:MAX_RESULTS]}
