from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"

DEFAULT_RESULT = {
    "intent": "Find relevant websites based on the search query",
    "keywords": [],
    "expanded_queries": [],
    "category": "tools",
    "filters": {"industry": None, "platform": None},
}

CATEGORY_HINTS = {
    "music": ["music", "song", "artist", "audio", "playlist", "audius"],
    "news": ["news", "headline", "article", "journal", "media"],
    "games": ["game", "games", "tic tac toe", "criss cross", "arcade"],
    "tools": ["tool", "tools", "saas", "software", "automation", "app"],
    "productivity": ["productivity", "workflow", "focus", "planner", "tasks"],
}

INDUSTRY_HINTS = [
    "saas",
    "e-commerce",
    "ecommerce",
    "agency",
    "portfolio",
    "finance",
    "education",
    "healthcare",
    "technology",
    "marketing",
    "community",
]

PLATFORM_HINTS = [
    "webflow",
    "wordpress",
    "shopify",
    "framer",
    "react",
    "nextjs",
    "wix",
    "hubspot",
    "magento",
    "ghost",
]

QUERY_VARIANTS = {
    "saas": ["software as a service", "b2b saas tools"],
    "agency": ["creative agency websites", "digital agency portfolio"],
    "ecommerce": ["e-commerce storefronts", "online store websites"],
    "e-commerce": ["ecommerce websites", "online shop websites"],
    "design": ["ui ux design websites", "creative portfolio websites"],
    "portfolio": ["showcase websites", "case study websites"],
    "startup": ["early stage startup websites", "startup saas websites"],
}


def _normalize_query(query: str) -> str:
    return " ".join((query or "").strip().split())


def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    if not text:
        return None

    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def _ensure_shape(payload: dict[str, Any], query: str) -> dict[str, Any]:
    result = dict(DEFAULT_RESULT)
    result["filters"] = {"industry": None, "platform": None}

    if isinstance(payload, dict):
        intent = payload.get("intent")
        keywords = payload.get("keywords")
        expanded = payload.get("expanded_queries")
        category = payload.get("category")
        filters = payload.get("filters")

        if isinstance(intent, str) and intent.strip():
            result["intent"] = intent.strip()
        if isinstance(keywords, list):
            result["keywords"] = [str(k).strip() for k in keywords if str(k).strip()][:12]
        if isinstance(expanded, list):
            result["expanded_queries"] = [str(q).strip() for q in expanded if str(q).strip()][:6]
        if isinstance(category, str) and category.strip():
            result["category"] = category.strip().lower()
        if isinstance(filters, dict):
            industry = filters.get("industry")
            platform = filters.get("platform")
            result["filters"] = {
                "industry": str(industry).strip() if isinstance(industry, str) and industry.strip() else None,
                "platform": str(platform).strip() if isinstance(platform, str) and platform.strip() else None,
            }

    if not result["keywords"]:
        result["keywords"] = [t for t in re.split(r"[^a-z0-9\-\+]+", query.lower()) if t][:8]

    return result


def _guess_category(q: str) -> str:
    ql = q.lower()
    for category, hints in CATEGORY_HINTS.items():
        if any(h in ql for h in hints):
            return category
    return "tools"


def _first_match(q: str, choices: list[str]) -> str | None:
    ql = q.lower()
    for item in choices:
        if item in ql:
            return item
    return None


def _heuristic_analysis(query: str) -> dict[str, Any]:
    q = _normalize_query(query)
    if not q:
        return dict(DEFAULT_RESULT)

    terms = [t for t in re.split(r"[^a-z0-9\-\+]+", q.lower()) if t]
    category = _guess_category(q)
    industry = _first_match(q, INDUSTRY_HINTS)
    platform = _first_match(q, PLATFORM_HINTS)

    expanded_queries: list[str] = []
    expanded_queries.append(q)

    for term in terms:
        for variant in QUERY_VARIANTS.get(term, []):
            expanded_queries.append(variant)

    if len(terms) >= 2:
        expanded_queries.append(" ".join(terms[:2]))

    expanded_queries.append(f"best {q} websites")

    deduped = []
    seen = set()
    for eq in expanded_queries:
        key = eq.strip().lower()
        if key and key not in seen and key != q.lower():
            seen.add(key)
            deduped.append(eq.strip())
        if len(deduped) >= 6:
            break

    intent = f"Find websites relevant to {q}"
    if industry:
        intent = f"Find {industry} websites relevant to {q}"

    return {
        "intent": intent,
        "keywords": terms[:10],
        "expanded_queries": deduped,
        "category": category,
        "filters": {
            "industry": industry,
            "platform": platform,
        },
    }


def _gemini_analysis(query: str) -> dict[str, Any] | None:
    gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    gemini_model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

    if not gemini_api_key:
        return None

    prompt = (
        "You are an intelligent search query understanding engine. "
        "Return ONLY valid JSON with keys: intent, keywords, expanded_queries, category, filters. "
        "filters must include industry and platform (or null). "
        "If query is vague, make a reasonable assumption. "
        f"User query: {query}"
    )

    params = urlencode({"key": gemini_api_key})
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?{params}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }

    try:
        request = Request(
            url=url,
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=8.0) as response:
            response_body = response.read().decode("utf-8")
            data = json.loads(response_body)
    except Exception:
        return None

    try:
        candidates = data.get("candidates", [])
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        text = parts[0].get("text", "") if parts else ""
        parsed = _extract_json_from_text(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None

    return None


def analyze_search_query(query: str) -> dict[str, Any]:
    q = _normalize_query(query)
    if not q:
        return dict(DEFAULT_RESULT)

    gemini_payload = _gemini_analysis(q)
    if gemini_payload:
        return _ensure_shape(gemini_payload, q)

    heuristic_payload = _heuristic_analysis(q)
    return _ensure_shape(heuristic_payload, q)
