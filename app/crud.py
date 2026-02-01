from __future__ import annotations

import math
from typing import Iterable

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Site


# --------------------------------------------------
# Simple normalization + tiny Levenshtein helper
# --------------------------------------------------

def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _levenshtein(a: str, b: str) -> int:
    """
    Very small Levenshtein implementation (no external libs).
    Used only as a fallback for typo-tolerance on short tokens.
    """
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    if la < lb:
        a, b, la, lb = b, a, lb, la
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            dele = prev[j] + 1
            sub = prev[j - 1] + (ca != cb)
            cur.append(min(ins, dele, sub))
        prev = cur
    return prev[-1]


# --------------------------------------------------
# Synonyms & query expansion
# --------------------------------------------------

SYNONYMS = {
    # shop / e‑commerce
    "shop": ["store", "ecommerce", "e-commerce", "cart", "checkout"],
    "store": ["shop", "ecommerce", "e-commerce"],
    "ecommerce": ["shop", "store", "online shop", "online store"],
    # blog / content / publishing
    "blog": ["content", "publishing", "articles", "news"],
    "content": ["blog", "media"],
    # no‑code platforms
    "no-code": ["nocode", "bubble", "webflow", "framer"],
    "nocode": ["no-code", "bubble", "webflow"],
    # design / creative
    "design": ["designer", "agency", "studio", "portfolio", "ui", "ux", "creative"],
    "portfolio": ["case study", "projects", "design"],
    "agency": ["studio", "design", "creative"],
}


def _expand_terms(raw_query: str) -> list[str]:
    """
    Normalize and expand the query into search terms.

    - Lowercase, split on whitespace and punctuation.
    - Add simple synonyms and variants (e.g. shop → ecommerce, store).
    """
    q = _norm(raw_query)
    if not q:
        return []
    # naive tokenization
    import re

    tokens = re.split(r"[^a-z0-9]+", q)
    tokens = [t for t in tokens if t]
    terms: set[str] = set(tokens)
    for t in list(terms):
        for syn in SYNONYMS.get(t, []):
            terms.add(syn.lower())
    return list(terms)


# --------------------------------------------------
# Search & ranking
# --------------------------------------------------

def get_all_sites(db: Session) -> list[Site]:
    return db.query(Site).all()


def _rank_site(site: Site, terms: Iterable[str]) -> float:
    """
    Weighted ranking logic.

    Rough heuristic:
      - Name/domain match > path match > platform/industry match > tag match.
      - Tag matches are boosted by tag_confidence when available.
      - Small typo tolerance via Levenshtein distance on tokens.

    This is intentionally simple and explainable, but works well up to ~50k rows.

    Example behavior:
      - \"webflow saas\" returns Webflow SaaS landing pages above generic blogs.
      - \"shop\" returns ecommerce sites (Shopify, store, cart…) above blogs.
      - \"design\" surfaces agency/portfolio/UI-heavy sites.
    """
    score = 0.0

    url = _norm(site.website_url)
    platform = _norm(site.platform)
    industry = _norm(site.industry)
    tags_text = _norm(site.tags)
    tag_conf = site.tag_confidence or {}

    # Pre-split URL into domain + path tokens
    host = ""
    path = ""
    if "://" in url:
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            host = _norm(parsed.netloc)
            path = _norm(parsed.path)
        except Exception:
            host = url
            path = ""
    else:
        host = url

    # Tokens from tags (for fuzzy + confidence boosting)
    tag_tokens = [t.strip().lower() for t in (site.tags or "").split(",") if t.strip()]

    for term in terms:
        if not term:
            continue
        # Exact/substring matches
        if term in host:
            score += 5.0  # domain match (strong signal)
        if term in path:
            score += 4.0  # URL path / slug
        if term in platform:
            score += 4.5  # platform field
        if term in industry:
            score += 4.0  # industry field

        # Tag matches: boosted by tag_confidence when available
        for tag in tag_tokens:
            if not tag:
                continue
            base = 2.5
            matched = False
            if term in tag or tag in term:
                matched = True
            else:
                # tiny typo tolerance on short tags
                if abs(len(term) - len(tag)) <= 2 and _levenshtein(term, tag) <= 1:
                    matched = True
            if matched:
                conf = float(tag_conf.get(tag, 0.0)) if isinstance(tag_conf, dict) else 0.0
                score += base * (1.0 + min(conf, 1.0))

        # Very small fuzzy bump on platform/industry if close edit distance
        for field in (platform, industry):
            if not field:
                continue
            # quick filter: only for short-ish queries
            if len(term) <= 12 and abs(len(term) - len(field)) <= 6:
                if _levenshtein(term, field) == 1:
                    score += 1.0

    return score


def search_sites(db: Session, query: str) -> list[Site]:
    """
    Legacy helper kept for compatibility.

    Uses the same ranking as paginated search but returns all matches.
    """
    items, _ = search_sites_paginated(db, query, skip=0, limit=10_000)
    return items


def search_sites_paginated(db: Session, query: str, skip: int, limit: int) -> tuple[list[Site], int]:
    """
    Return a page of sites plus the total matching count, with ranking.

    Implementation notes:
      * Phase 1 (SQL): use LIKE filters on normalized query + synonyms to
        get a reasonable candidate set (fast on 10k–50k rows).
      * Phase 2 (Python): compute a ranking score per candidate based on
        domain/platform/industry/tags + tag_confidence.
      * If Phase 1 finds no candidates, fall back to a fuzzy scan over all
        rows using a lightweight Levenshtein distance.
    """
    terms = _expand_terms(query)
    if not terms:
        return [], 0

    # -------------------------------
    # Phase 1: SQL candidate filter
    # -------------------------------
    like_clauses = []
    for term in terms:
        pat = f"%{term}%"
        like_clauses.extend(
            [
                Site.website_url.ilike(pat),
                Site.platform.ilike(pat),
                Site.industry.ilike(pat),
                Site.tags.ilike(pat),
            ]
        )

    if like_clauses:
        candidates = db.query(Site).filter(or_(*like_clauses)).all()
    else:
        candidates = []

    # -------------------------------
    # Phase 2: fallback fuzzy search
    # -------------------------------
    if not candidates:
        # No direct LIKE matches – do a fuzzy pass over all sites.
        all_sites = db.query(Site).all()
        # Simple filter: only keep rows with a minimal fuzzy signal.
        filtered: list[tuple[Site, float]] = []
        main_term = _norm(query)
        for s in all_sites:
            host = _norm(s.website_url)
            if "//" in host:
                try:
                    from urllib.parse import urlparse as _parse

                    host = _norm(_parse(host).netloc)
                except Exception:
                    pass
            # quick fuzzy on domain + platform/industry
            approx = 0
            for field in (host, _norm(s.platform), _norm(s.industry)):
                if field and abs(len(main_term) - len(field)) <= 6:
                    d = _levenshtein(main_term, field)
                    if d <= 2:
                        approx += 1
            if approx:
                filtered.append((s, float(approx)))
        # Use approx as tiny pre-score, then full ranking below
        candidates = [s for s, _ in filtered]

    if not candidates:
        return [], 0

    # -------------------------------
    # Phase 3: ranking inside Python
    # -------------------------------
    scored = [(s, _rank_site(s, terms)) for s in candidates]
    # Drop obviously irrelevant rows (score == 0)
    scored = [(s, sc) for s, sc in scored if sc > 0]
    if not scored:
        return [], 0

    scored.sort(key=lambda x: -x[1])
    ordered_sites = [s for s, _ in scored]
    total = len(ordered_sites)
    start = max(0, skip)
    end = start + max(0, limit)
    page_items = ordered_sites[start:end]
    return page_items, total


def bulk_create_sites(db: Session, sites: list[dict]) -> int:
    created = 0
    for site in sites:
        db_site = Site(**site)
        db.add(db_site)
        try:
            db.commit()
            created += 1
        except IntegrityError:
            db.rollback()  # skip duplicates safely
    return created