"""
Centralized site enrichment pipeline (reusable for all write operations).

Pipeline stages:
  1. Input validation
  2. URL normalization
  3. Metadata enrichment (lightweight, synchronous)
  4. Persistence using existing storage
  5. Structured result output

Explicitly handles errors; one failure must NOT break batch operations.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from .models import Site

logger = logging.getLogger(__name__)

# ==================================================
# CONFIG
# ==================================================

REQUEST_TIMEOUT = 8
MAX_TAGS = 10
MIN_CONFIDENCE = 0.15

HEADERS = {
    "User-Agent": "Mozilla/5.0 (SiteCatalogEnricher/1.0)",
}

# ==================================================
# CMS / PLATFORM SIGNATURES
# ==================================================

PLATFORM_SIGNATURES = {
    "WordPress": ["/wp-content/", "wp-json", "wp-includes", "wordpress"],
    "Webflow": ["webflow.js", "data-wf-page", "webflow.com"],
    "Shopify": ["cdn.shopify.com", "x-shopify", "shopify-section", "shopify"],
    "Wix": ["wixstatic.com", "wixsite.com", "wix.com"],
    "Squarespace": ["static.squarespace.com", "squarespace"],
    "Framer": ["framerusercontent.com", "framer"],
    "Ghost": ["ghost.io", "data-ghost", "ghost-content-api"],
    "Kajabi": ["kajabi.com", "cdn.kajabi.com", "kajabi-storefront"],
    "Bubble": ["bubble.io", "bubble.is", "bubbleapps.io"],
    "Magento": ["magento", "mage/", "mage."],
    "Drupal": ["drupal", "drupal-settings-json", "sites/default"],
    "Joomla": ["joomla", "com_content", "Joomla"],
    "Next.js": ["_next/static", "__NEXT_DATA__", "next/dist"],
    "Nuxt": ["_nuxt", "__NUXT__", "nuxt/"],
    "Laravel": ["laravel", "laravel_session", "csrf-token"],
    "Weebly": ["weebly.com", "weebly.cloud"],
    "Notion": ["notion.site", "notion.so", "notion-api"],
    "Carrd": ["carrd.co", "carrd.co/assets"],
    "Tilda": ["tilda.ws", "tilda.cc"],
    "Thinkific": ["thinkific.com", "thinkific"],
    "Teachable": ["teachable.com", "teachable"],
    "ClickFunnels": ["clickfunnels.com", "clickfunnels"],
    "HubSpot CMS": ["hubspot", "hs-scripts", "hs-sdk"],
    "React": ["react", "data-reactroot", "ReactDOM"],
    "Vue": ["vue", "vue.js", "__VUE__"],
    "Custom": [],
}

# ==================================================
# INDUSTRY TAXONOMY
# ==================================================

INDUSTRY_KEYWORDS = {
    "SaaS": ["saas", "software", "platform", "api", "dashboard", "cloud", "subscription"],
    "E-commerce": ["shop", "store", "cart", "checkout", "product", "buy", "e-commerce", "ecommerce"],
    "Blog": ["blog", "post", "article", "writing", "newsletter"],
    "Portfolio": ["portfolio", "projects", "case study", "resume", "cv", "work"],
    "Agency": ["agency", "studio", "consulting", "solutions", "services", "we help"],
    "Education": ["education", "course", "academy", "learning", "training", "teach", "school"],
    "Finance": ["finance", "bank", "loan", "investment", "crypto", "trading", "payment"],
    "Healthcare": ["health", "clinic", "medical", "doctor", "wellness", "hospital", "care"],
    "Community": ["community", "forum", "members", "discord", "slack", "network"],
    "Marketplace": ["marketplace", "market", "vendors", "listings", "buyers", "sellers"],
    "Media": ["media", "news", "magazine", "articles", "content", "publish"],
    "Fitness": ["fitness", "gym", "workout", "training", "sports", "athlete"],
    "Real Estate": ["real estate", "property", "listing", "rent", "housing", "realtor"],
    "Restaurant": ["restaurant", "menu", "food", "cafe", "dining", "reservation"],
    "Travel": ["travel", "hotel", "booking", "tour", "vacation", "trip"],
    "Nonprofit": ["nonprofit", "ngo", "charity", "foundation", "donation", "cause"],
    "Technology": ["technology", "developer", "engineering", "it ", "software"],
    "Marketing": ["marketing", "seo", "ads", "campaign", "branding", "growth"],
}

STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "your",
    "you", "are", "was", "were", "has", "have", "will", "our",
    "their", "they", "them", "into", "about", "all", "can", "get",
}

# ==================================================
# HEX COLOR REGEX
# ==================================================

_HEX_RE = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")


def _normalize_hex(s: str) -> str:
    """Normalize hex color to 6-digit uppercase."""
    h = s.lstrip("#")
    if len(h) == 3:
        h = "".join(c + c for c in h)
    if len(h) >= 6:
        return "#" + h[:6].lower()
    return s


# ==================================================
# STAGE 1: INPUT VALIDATION
# ==================================================


def validate_url(url: str) -> tuple[bool, Optional[str]]:
    """
    Validate URL format. Return (is_valid, error_message).
    """
    url = (url or "").strip()
    if not url:
        return False, "URL is empty"
    if not url.startswith(("http://", "https://")):
        return False, "URL must start with http:// or https://"
    if len(url) > 2048:
        return False, "URL is too long (max 2048 chars)"
    return True, None


# ==================================================
# STAGE 2: URL NORMALIZATION
# ==================================================


def normalize_url(url: str) -> str:
    """Trim whitespace, ensure scheme."""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


# ==================================================
# STAGE 3: METADATA ENRICHMENT (FETCHING & DETECTION)
# ==================================================


def fetch_site_metadata(url: str) -> tuple[str, str, str]:
    """
    Fetch HTML and extract text for enrichment.
    Return (html, combined_text, base_url).
    On error, return ("", "", url).
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        html = r.text
        base = r.url
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return "", "", url

    try:
        soup = BeautifulSoup(html, "html.parser")
        title = (soup.title.string or "").strip()
        meta = soup.find("meta", attrs={"name": "description"})
        desc = (meta.get("content", "") or "").strip() if meta and meta.get("content") else ""
        paragraphs = " ".join(p.get_text() for p in soup.find_all("p")[:14])
        combined = f"{title} {desc} {paragraphs}"
        return html, combined, base
    except Exception as e:
        logger.warning(f"Failed to parse HTML for {url}: {e}")
        return html, "", url


def detect_platforms(html: str) -> list[tuple[str, float]]:
    """Return list of (platform_name, confidence 0–1)."""
    if not html:
        return []
    lower = html.lower()
    scores: dict[str, float] = {}

    for platform, signals in PLATFORM_SIGNATURES.items():
        if platform == "Custom":
            continue
        for sig in signals:
            if sig.lower() in lower:
                scores[platform] = scores.get(platform, 0.0) + 1.0

    if not scores:
        return [("Custom", 0.5)]

    total = sum(scores.values())
    out = [(p, min(1.0, s / max(2.0, total * 0.4))) for p, s in scores.items()]
    out.sort(key=lambda x: -x[1])
    return [(p, c) for p, c in out if c >= MIN_CONFIDENCE]


def detect_industries(text: str) -> list[tuple[str, float]]:
    """Return list of (industry_name, confidence 0–1)."""
    if not text:
        return []
    clean = text.lower()
    clean = re.sub(r"[^a-z0-9\s]", " ", clean)
    scores: dict[str, float] = {}

    for industry, keywords in INDUSTRY_KEYWORDS.items():
        cnt = sum(clean.count(k.lower()) for k in keywords)
        if cnt > 0:
            scores[industry] = float(cnt)

    if not scores:
        return []
    mx = max(scores.values())
    out = [(i, min(1.0, s / max(1.0, mx))) for i, s in scores.items()]
    out.sort(key=lambda x: -x[1])
    return [(i, c) for i, c in out if c >= MIN_CONFIDENCE][:5]


def extract_tags_with_confidence(text: str) -> dict[str, float]:
    """Return dict tag -> confidence 0–1."""
    words = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower()).split()
    freq: dict[str, int] = {}
    for w in words:
        if len(w) < 4 or w in STOPWORDS:
            continue
        freq[w] = freq.get(w, 0) + 1

    sorted_items = sorted(freq.items(), key=lambda x: -x[1])[:MAX_TAGS]
    if not sorted_items:
        return {}
    max_f = sorted_items[0][1]
    return {
        w: round(min(1.0, 0.2 + 0.8 * (f / max_f)), 2)
        for w, f in sorted_items
    }


def extract_colors(html: str) -> dict[str, Optional[str]]:
    """Return {"primary": "#hex or None", "secondary": "#hex or None"}."""
    primary: Optional[str] = None
    secondary: Optional[str] = None
    seen: set[str] = set()

    def add_hex(match: re.Match) -> None:
        nonlocal primary, secondary
        h = _normalize_hex("#" + match.group(1))
        if h in seen or len(seen) >= 2:
            return
        seen.add(h)
        if primary is None:
            primary = h
        else:
            secondary = h

    try:
        soup = BeautifulSoup(html, "html.parser")
        for meta in soup.find_all("meta", attrs={"name": re.compile(r"theme-color|msapplication-TileColor", re.I)}):
            c = meta.get("content") or ""
            for m in _HEX_RE.finditer(c):
                add_hex(m)
                break

        style_text = ""
        for tag in soup.find_all(attrs={"style": True}):
            style_text += " " + (tag.get("style") or "")
        for tag in soup.find_all("style"):
            style_text += " " + (tag.string or "")
        style_text = style_text[:50000]
        for m in _HEX_RE.finditer(style_text):
            add_hex(m)
            if primary and secondary:
                break
    except Exception as e:
        logger.warning(f"Failed to extract colors: {e}")

    return {"primary": primary, "secondary": secondary}


# ==================================================
# STAGE 4 & 5: BUILD ENRICHMENT RESULT & PERSIST
# ==================================================


class EnrichmentResult:
    """Structured output of the enrichment pipeline."""

    def __init__(
        self,
        website_url: str,
        platform: str,
        industry: str,
        tags: str,
        platforms: list[str],
        industries: list[str],
        colors: dict[str, Optional[str]],
        tag_confidence: dict[str, float],
        enrichment_signals: dict,
        last_enriched_at: str,
    ):
        self.website_url = website_url
        self.platform = platform
        self.industry = industry
        self.tags = tags
        self.platforms = platforms
        self.industries = industries
        self.colors = colors
        self.tag_confidence = tag_confidence
        self.enrichment_signals = enrichment_signals
        self.last_enriched_at = last_enriched_at

    def to_dict(self) -> dict:
        """Convert to dict for API responses."""
        return {
            "website_url": self.website_url,
            "platform": self.platform,
            "industry": self.industry,
            "tags": self.tags,
            "platforms": self.platforms,
            "industries": self.industries,
            "colors": self.colors,
            "tag_confidence": self.tag_confidence,
            "last_enriched_at": self.last_enriched_at,
        }


def build_enrichment_result(
    url: str,
    html: str,
    text: str,
) -> EnrichmentResult:
    """
    Run all detectors and return structured EnrichmentResult.
    """
    platforms_with_conf = detect_platforms(html)
    industries_with_conf = detect_industries(text)
    tag_confidence = extract_tags_with_confidence(text)
    colors = extract_colors(html)

    platforms = [p for p, _ in platforms_with_conf]
    industries = [i for i, _ in industries_with_conf]

    signals = {
        "platform_scores": {p: c for p, c in platforms_with_conf},
        "industry_scores": {i: c for i, c in industries_with_conf},
        "colors": colors,
    }

    # Legacy display fields
    platform_legacy = ", ".join(platforms[:3]) if platforms else "Unknown"
    industry_legacy = ", ".join(industries[:3]) if industries else "Unknown"
    tags_legacy = ", ".join(
        sorted(tag_confidence.keys(), key=lambda t: -tag_confidence.get(t, 0))[:MAX_TAGS]
    )

    return EnrichmentResult(
        website_url=url,
        platform=platform_legacy,
        industry=industry_legacy,
        tags=tags_legacy,
        platforms=platforms,
        industries=industries,
        colors=colors,
        tag_confidence=tag_confidence,
        enrichment_signals=signals,
        last_enriched_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def persist_enrichment(db: Session, result: EnrichmentResult) -> Optional[Site]:
    """
    Persist enrichment result to database.
    Return the Site object on success, None on error.
    """
    try:
        site = db.query(Site).filter(Site.website_url == result.website_url).first()
        if not site:
            site = Site(website_url=result.website_url)
            db.add(site)

        # Update fields
        site.platform = result.platform
        site.industry = result.industry
        site.tags = result.tags
        site.platforms = result.platforms
        site.industries = result.industries
        site.colors = result.colors
        site.tag_confidence = result.tag_confidence
        site.enrichment_signals = result.enrichment_signals
        site.last_enriched_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(site)
        logger.info(f"Persisted enrichment for {result.website_url}")
        return site
    except Exception as e:
        logger.error(f"Failed to persist enrichment for {result.website_url}: {e}")
        db.rollback()
        return None


# ==================================================
# MAIN PIPELINE ENTRY POINT
# ==================================================


def enrich_and_persist(db: Session, url: str) -> tuple[bool, Optional[str], Optional[EnrichmentResult]]:
    """
    Complete enrichment pipeline: validate → normalize → fetch → detect → persist.

    Returns:
        (success: bool, error: Optional[str], result: Optional[EnrichmentResult])

    Rules:
        - success=True means fully persisted
        - error contains human-readable message if failed
        - result is populated on success
    """
    # STAGE 1: Validate
    is_valid, error_msg = validate_url(url)
    if not is_valid:
        logger.warning(f"Invalid URL: {url} - {error_msg}")
        return False, error_msg, None

    # STAGE 2: Normalize
    normalized_url = normalize_url(url)

    # STAGE 3: Fetch & Enrich
    html, text, base_url = fetch_site_metadata(normalized_url)
    if not html:
        error_msg = f"Failed to fetch {normalized_url}"
        logger.error(error_msg)
        return False, error_msg, None

    result = build_enrichment_result(normalized_url, html, text)

    # STAGE 4 & 5: Persist
    persisted = persist_enrichment(db, result)
    if not persisted:
        error_msg = f"Failed to persist enrichment for {normalized_url}"
        return False, error_msg, None

    return True, None, result
