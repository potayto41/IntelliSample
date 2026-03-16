"""Nature Wall news aggregation and in-memory caching."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Optional

import feedparser
from apscheduler.schedulers.background import BackgroundScheduler
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

FEEDS = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.nasa.gov/rss/dyn/breaking_news.rss",
    "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
]

MAX_ARTICLES = 30
REFRESH_INTERVAL_MINUTES = 60

news_cache: list[dict[str, str]] = []
_scheduler: Optional[BackgroundScheduler] = None


def _extract_image(entry: Any) -> Optional[str]:
    """Extract image URL from common RSS image fields in priority order."""
    media_content = getattr(entry, "media_content", None) or entry.get("media_content")
    if media_content:
        first = media_content[0] if isinstance(media_content, list) and media_content else media_content
        if isinstance(first, dict) and first.get("url"):
            return first["url"]

    media_thumbnail = getattr(entry, "media_thumbnail", None) or entry.get("media_thumbnail")
    if media_thumbnail:
        first = media_thumbnail[0] if isinstance(media_thumbnail, list) and media_thumbnail else media_thumbnail
        if isinstance(first, dict) and first.get("url"):
            return first["url"]

    enclosures = getattr(entry, "enclosures", None) or entry.get("enclosures")
    if enclosures:
        for enclosure in enclosures:
            href = enclosure.get("href") or enclosure.get("url")
            mime_type = (enclosure.get("type") or "").lower()
            if href and (mime_type.startswith("image/") or href.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))):
                return href

    summary_html = entry.get("summary") or entry.get("description") or ""
    if summary_html:
        soup = BeautifulSoup(summary_html, "html.parser")
        img = soup.find("img")
        if img and img.get("src"):
            return img.get("src")

    return None


def _format_published(entry: Any) -> str:
    raw = entry.get("published") or entry.get("updated") or ""
    if not raw:
        return ""
    try:
        parsed = parsedate_to_datetime(raw)
        return parsed.isoformat()
    except Exception:
        return raw


def fetch_articles() -> None:
    """Refresh news cache from RSS feeds. Only keeps articles with images."""
    global news_cache
    started = time.time()
    collected: list[dict[str, str]] = []
    skipped_without_images = 0
    total_entries_seen = 0

    for feed_url in FEEDS:
        try:
            parsed = feedparser.parse(feed_url)
            source = parsed.feed.get("title", feed_url)
            for entry in parsed.entries:
                total_entries_seen += 1
                image_url = _extract_image(entry)
                if not image_url:
                    skipped_without_images += 1
                    continue

                link = entry.get("link")
                title = entry.get("title")
                if not link or not title:
                    continue

                collected.append(
                    {
                        "title": title,
                        "image": image_url,
                        "url": link,
                        "source": source,
                        "published": _format_published(entry),
                    }
                )
        except Exception as exc:
            logger.warning("Failed to parse feed %s: %s", feed_url, exc)

    # Keep deterministic recent-first ordering when publish date is available.
    collected.sort(key=lambda item: item.get("published", ""), reverse=True)
    news_cache[:] = collected[:MAX_ARTICLES]

    logger.info("Fetched %s feeds", len(FEEDS))
    logger.info("Found %s articles", total_entries_seen)
    logger.info("Skipped %s without images", skipped_without_images)
    logger.info("Returning %s articles", len(news_cache))
    logger.info("Nature Wall cache refreshed in %.2fs", time.time() - started)


def start_news_scheduler() -> None:
    """Initialize the scheduler and start periodic cache refresh."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    fetch_articles()

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(fetch_articles, "interval", minutes=REFRESH_INTERVAL_MINUTES, id="nature_news_refresh", replace_existing=True)
    _scheduler.start()
    logger.info("Nature Wall scheduler started (%s min)", REFRESH_INTERVAL_MINUTES)


def stop_news_scheduler() -> None:
    """Stop the scheduler during app shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
