"""
Site enrichment pipeline (offline script).

Fetches each URL from sites_raw.csv, detects:
  - Multiple platforms (CMS/framework) with confidence 0–1
  - Multiple industries with confidence 0–1
  - Tags with confidence 0–1
  - Primary/secondary colors from meta, inline styles, CSS variables

Outputs sites_enriched.csv with legacy columns (platform, industry, tags) plus
JSON columns for the app: platforms, industries, colors, tag_confidence, last_enriched_at.

How enrichment works:
  1. Fetch HTML; extract title, meta description, body text.
  2. Platform detection: scan HTML (and script/src/href) for known signatures.
     Each signature hit adds to that platform’s score; score is turned into
     confidence (capped 0–1). All platforms above a threshold are kept.
  3. Industry detection: score text against keyword lists per industry.
     Scores are normalized to 0–1; industries above threshold are kept.
  4. Tags: frequent meaningful words; confidence from rank (top ≈ 1.0, decay).
  5. Colors: meta theme-color, meta msapplication-TileColor, then inline
     style and inline CSS for hex colors; first two distinct become primary/secondary.

Example enriched record (JSON-ish, for reference):
  {
    "website_url": "https://example.com",
    "platform": "Webflow, Next.js",
    "industry": "SaaS, Agency",
    "tags": "pricing, hero, features",
    "platforms": ["Webflow", "Next.js"],
    "industries": ["SaaS", "Agency"],
    "colors": {"primary": "#0070f3", "secondary": "#7928ca"},
    "tag_confidence": {"pricing": 0.92, "hero": 0.78, "features": 0.65},
    "last_enriched_at": "2025-01-27T12:00:00"
  }
"""
import csv
import json
import os
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

# ==================================================
# CONFIG
# ==================================================

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV = os.path.join(_SCRIPT_DIR, "sites_raw.csv")
OUTPUT_CSV = os.path.join(_SCRIPT_DIR, "sites_enriched.csv")

REQUEST_TIMEOUT = 8
SLEEP_SECONDS = 1
MAX_TAGS = 10
MIN_CONFIDENCE = 0.15  # drop platform/industry below this

HEADERS = {
    "User-Agent": "Mozilla/5.0 (SiteCatalogEnricher/1.0)",
}

# ==================================================
# CMS / PLATFORM SIGNATURES (extensible)
# Each key = platform name; value = list of case-insensitive substring signals.
# Stronger/multiple signals → higher confidence.
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
    "Custom": [],  # fallback when nothing else matches
}

# ==================================================
# INDUSTRY TAXONOMY (extensible)
# Keywords (case-insensitive) per industry; more hits → higher score → confidence.
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
# HEX COLOR REGEX (inline styles, meta, CSS)
# ==================================================

_HEX_RE = re.compile(
    r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b"
)


def _normalize_hex(s: str) -> str:
    h = s.lstrip("#")
    if len(h) == 3:
        h = "".join(c + c for c in h)
    if len(h) >= 6:
        return "#" + h[:6].lower()
    return s


# ==================================================
# FETCH
# ==================================================


def fetch_site(url: str) -> tuple[str, str, str]:
    """Fetch URL; return (html, combined_text_for_industry_tags, base_url)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        html = r.text
        base = r.url
    except Exception as e:
        print(f"[ERROR] {url} → {e}")
        return "", "", url

    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").strip() if soup.title else ""
    meta = soup.find("meta", attrs={"name": "description"})
    desc = (meta.get("content", "") or "").strip() if meta and meta.get("content") else ""
    paragraphs = " ".join(p.get_text() for p in soup.find_all("p")[:14])
    combined = f"{title} {desc} {paragraphs}"
    return html, combined, base


# ==================================================
# PLATFORM DETECTION (multiple + confidence)
# ==================================================


def detect_platforms(html: str) -> list[tuple[str, float]]:
    """
    Return list of (platform_name, confidence 0–1).
    Multiple matches allowed; confidence from relative signal strength.
    """
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


# ==================================================
# INDUSTRY DETECTION (multiple + confidence)
# ==================================================


def detect_industries(text: str) -> list[tuple[str, float]]:
    """
    Return list of (industry_name, confidence 0–1).
    Scores from keyword counts, normalized by max score.
    """
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


# ==================================================
# TAGS + CONFIDENCE
# ==================================================


def extract_tags_with_confidence(text: str) -> dict[str, float]:
    """
    Return dict tag -> confidence 0–1.
    Higher frequency / rank → higher confidence; top tag ≈ 1.0, then decay.
    """
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


# ==================================================
# COLOR EXTRACTION
# ==================================================


def extract_colors(html: str, soup: BeautifulSoup, base_url: str) -> dict[str, str | None]:
    """
    Return {"primary": "#hex or None", "secondary": "#hex or None"}.
    Sources: meta theme-color, msapplication-TileColor, inline style/CSS hex.
    Fallback gracefully if none found.
    """
    primary: str | None = None
    secondary: str | None = None
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

    # Meta theme-color
    for meta in soup.find_all("meta", attrs={"name": re.compile(r"theme-color|msapplication-TileColor", re.I)}):
        c = meta.get("content") or ""
        for m in _HEX_RE.finditer(c):
            add_hex(m)
            break

    # Inline style and style block content (first ~50k chars)
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

    return {"primary": primary, "secondary": secondary}


# ==================================================
# BUILD OUTPUT ROW
# ==================================================


def enrich_one(url: str, html: str, text: str, base_url: str) -> dict:
    """Run all detectors and return a row dict for CSV."""
    soup = BeautifulSoup(html, "html.parser") if html else BeautifulSoup("", "html.parser")

    platforms_with_conf = detect_platforms(html)
    industries_with_conf = detect_industries(text)
    tag_confidence = extract_tags_with_confidence(text)
    colors = extract_colors(html, soup, base_url)

    platforms = [p for p, _ in platforms_with_conf]
    industries = [i for i, _ in industries_with_conf]

    # Raw signal snapshot for debugging / self-improvement.
    # Stored in the DB as JSON so future pipelines can introspect why a
    # platform/industry/color was chosen without re-scraping HTML.
    signals = {
        "platform_scores": {p: c for p, c in platforms_with_conf},
        "industry_scores": {i: c for i, c in industries_with_conf},
        "colors": colors,
    }

    # Legacy display fields (first/join for UI)
    platform_legacy = ", ".join(platforms[:3]) if platforms else "Unknown"
    industry_legacy = ", ".join(industries[:3]) if industries else "Unknown"
    tags_legacy = ", ".join(sorted(tag_confidence.keys(), key=lambda t: -tag_confidence.get(t, 0))[:MAX_TAGS])

    return {
        "website_url": url,
        "platform": platform_legacy,
        "industry": industry_legacy,
        "tags": tags_legacy,
        "platforms": json.dumps(platforms),
        "industries": json.dumps(industries),
        "colors": json.dumps(colors),
        "tag_confidence": json.dumps(tag_confidence),
        "enrichment_signals": json.dumps(signals),
        "last_enriched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ==================================================
# MAIN
# ==================================================


def main():
    fieldnames = [
        "website_url", "platform", "industry", "tags",
        "platforms", "industries", "colors", "tag_confidence",
        "enrichment_signals", "last_enriched_at",
    ]
    with open(INPUT_CSV, newline="", encoding="utf-8") as infile, \
         open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as outfile:
        reader = csv.DictReader(infile)
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        for idx, row in enumerate(reader, start=1):
            url = (row.get("website_url") or "").strip()
            if not url:
                continue
            print(f"[{idx}] Processing {url}")
            html, text, base_url = fetch_site(url)
            out = enrich_one(url, html, text, base_url)
            writer.writerow(out)
            time.sleep(SLEEP_SECONDS)

    print("\n✅ Enrichment complete.")
    print(f"📄 Output file: {OUTPUT_CSV}")


# --------------------------------------------------
# Re-enrichment helper
# --------------------------------------------------

RE_ENRICH_THRESHOLD_DAYS = 30


def needs_reenrichment(last_enriched_at: datetime | None, now: datetime | None = None) -> bool:
    """
    Decide whether a site should be re-enriched.

    - If never enriched → True
    - If older than RE_ENRICH_THRESHOLD_DAYS → True
    - Otherwise → False

    Intended to be used by a future CLI / admin endpoint that iterates over\n"
    Site rows in the DB and selectively calls `enrich_one` again.\n"
    """
    if last_enriched_at is None:
        return True
    if now is None:
        now = datetime.now(timezone.utc)
    delta = now - last_enriched_at
    return delta.days >= RE_ENRICH_THRESHOLD_DAYS


if __name__ == "__main__":
    main()
