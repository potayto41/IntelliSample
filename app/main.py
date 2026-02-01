from datetime import datetime as datetime_naive
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from .database import SessionLocal, engine, ensure_enrichment_columns
from .models import Base, Site, TagFeedback
from . import crud
from .platform_icons import get_platform_icon_svg
import csv
import io
import json
import math
from urllib.parse import quote

Base.metadata.create_all(bind=engine)
ensure_enrichment_columns()

app = FastAPI()

# Point to the actual static directory name in this project ("Static")
app.mount("/static", StaticFiles(directory="app/Static"), name="static")
templates = Jinja2Templates(directory="app/templates")

PAGE_SIZE = 10


def _get_search_results(db, q: str, page: int):
    """Shared search + pagination logic. Returns dict with sites, platform_icons, page, etc."""
    q = (q or "").strip()
    if q:
        raw_page = page if page > 0 else 1
        skip = (raw_page - 1) * PAGE_SIZE
        sites, total_results = crud.search_sites_paginated(db, q, skip=skip, limit=PAGE_SIZE)
        total_pages = max(1, math.ceil(total_results / PAGE_SIZE)) if total_results > 0 else 1
        if raw_page > total_pages and total_results > 0:
            raw_page = 1
            skip = 0
            sites, total_results = crud.search_sites_paginated(db, q, skip=skip, limit=PAGE_SIZE)
        current_page = raw_page
        has_previous = current_page > 1
        has_next = current_page < total_pages and total_results > PAGE_SIZE
    else:
        current_page = 1
        sites = []
        total_results = 0
        total_pages = 1
        has_previous = False
        has_next = False

    platform_icons = [get_platform_icon_svg(s.platform) for s in sites]
    return {
        "sites": sites,
        "platform_icons": platform_icons,
        "query": q,
        "query_encoded": quote(q),
        "page": current_page,
        "total_pages": total_pages,
        "total_results": total_results,
        "page_size": PAGE_SIZE,
        "has_previous": has_previous,
        "has_next": has_next,
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request, q: str = "", page: int = 1):
    db = SessionLocal()
    ctx = _get_search_results(db, q, page)
    db.close()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, **ctx},
    )


@app.get("/add-sites", response_class=HTMLResponse)
def add_sites_page(request: Request):
    """Add Sites page (UI only). No upload logic wired."""
    return templates.TemplateResponse("add-sites.html", {"request": request})


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = "", page: int = 1):
    """Returns only the results section HTML (partial) for AJAX replacement."""
    db = SessionLocal()
    ctx = _get_search_results(db, q, page)
    db.close()
    return templates.TemplateResponse(
        "results.html",
        {"request": request, **ctx},
    )

@app.post("/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        return {"error": "Only CSV files are allowed"}

    content = await file.read()
    decoded = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded))

    sites = []
    for row in reader:
        url = row.get("website_url", "").strip()
        if not url:
            continue
        platform_legacy = row.get("platform", "").strip()
        industry_legacy = row.get("industry", "").strip()
        tags_legacy = row.get("tags", "").strip()
        # Enriched columns (optional): platforms, industries, colors, tag_confidence, last_enriched_at, enrichment_signals
        platforms_json = row.get("platforms", "").strip()
        industries_json = row.get("industries", "").strip()
        colors_json = row.get("colors", "").strip()
        tag_conf_json = row.get("tag_confidence", "").strip()
        last_enriched = row.get("last_enriched_at", "").strip()
        signals_json = row.get("enrichment_signals", "").strip()

        platforms = json.loads(platforms_json) if platforms_json else None
        industries = json.loads(industries_json) if industries_json else None
        colors = json.loads(colors_json) if colors_json else None
        tag_confidence = json.loads(tag_conf_json) if tag_conf_json else None
        enrichment_signals = json.loads(signals_json) if signals_json else None

        # Backward compat: keep platform/industry/tags for display
        if platforms and not platform_legacy:
            platform_legacy = ", ".join(p for p in platforms[:3])
        if industries and not industry_legacy:
            industry_legacy = ", ".join(i for i in industries[:3])
        if tag_confidence and not tags_legacy:
            tags_legacy = ", ".join(sorted(tag_confidence.keys(), key=lambda t: -tag_confidence.get(t, 0))[:6])

        rec = {
            "website_url": url,
            "platform": platform_legacy or None,
            "industry": industry_legacy or None,
            "tags": tags_legacy or None,
        }
        if platforms is not None:
            rec["platforms"] = platforms
        if industries is not None:
            rec["industries"] = industries
        if colors is not None:
            rec["colors"] = colors
        if tag_confidence is not None:
            rec["tag_confidence"] = tag_confidence
        if enrichment_signals is not None:
            rec["enrichment_signals"] = enrichment_signals
        if last_enriched:
            try:
                rec["last_enriched_at"] = datetime_naive.fromisoformat(
                    last_enriched.replace("Z", "+00:00")
                )
            except Exception:
                pass
        sites.append(rec)

    db = SessionLocal()
    created = crud.bulk_create_sites(db, sites)
    db.close()

    return {"message": f"{created} sites imported successfully"}


@app.post("/tag-feedback")
async def tag_feedback(website_url: str = Form(...), suggested_tags: str = Form(...)):
    """
    Anonymous tag feedback endpoint.

    Suggestions are stored for review and future self‑improvement, but are NOT
    auto-applied to the live catalog (no auth / moderation yet).
    """
    url = (website_url or "").strip()
    if not url or not suggested_tags.strip():
        return {"status": "ignored"}

    db = SessionLocal()
    try:
        site = db.query(Site).filter(Site.website_url == url).first()
        fb = TagFeedback(
            site_id=site.id if site else None,
            website_url=url,
            suggested_tags=suggested_tags.strip(),
            created_at=datetime_naive.now(),
        )
        db.add(fb)
        db.commit()
    finally:
        db.close()

    return {"status": "ok"}


@app.post("/add-site")
async def add_site(
    website_url: str = Form(...),
    platform: str = Form(""),
    industry: str = Form(""),
    tags: str = Form(""),
):
    """Add a single site from the manual form and redirect home."""
    db = SessionLocal()
    crud.bulk_create_sites(
        db,
        [
            {
                "website_url": website_url.strip(),
                "platform": platform.strip(),
                "industry": industry.strip(),
                "tags": tags.strip(),
            }
        ],
    )
    db.close()

    # Redirect back to the homepage so the new entry shows up
    return RedirectResponse(url="/", status_code=303)
