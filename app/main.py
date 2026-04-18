import os
from datetime import datetime as datetime_naive
from fastapi import FastAPI, Request, UploadFile, File, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import text
from .database import engine, ensure_enrichment_columns, ensure_postgres_indexes, get_db, check_database_connection
from .models import Base, Site, TagFeedback
from . import crud
from .enrichment import enrich_and_persist
from .write_safety import add_site_limiter, upload_csv_limiter, validate_csv_upload, get_client_ip
from .platform_icons import get_platform_icon_svg
from .news_portal import news_cache, start_news_scheduler, stop_news_scheduler
from .music_portal import HOME_QUERIES, fallback_search, fetch_from_audius, normalize_audius_response
import csv
import io
import json
import logging
import math
import time
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Database connection health status
db_connection_healthy = False

# Note: Base.metadata.create_all() moved to startup event to avoid import-time database operations

app = FastAPI()

# Point to the actual static directory name in this project ("Static")
app.mount("/static", StaticFiles(directory="app/Static"), name="static")
templates = Jinja2Templates(directory="app/templates")

PAGE_SIZE = 10

@app.on_event("startup")
async def startup_event():
    """Initialize database schema and ensure enrichment columns exist."""
    global db_connection_healthy
    try:
        logger.info("Running database schema initialization...")

        # Check database connectivity first
        if not check_database_connection():
            logger.warning("Database connection check failed on startup. App will continue but DB operations may fail.")
            db_connection_healthy = False
        else:
            db_connection_healthy = True
            logger.info("Database connection check passed")

        # Only create schema automatically in development
        if os.getenv("ENVIRONMENT", "").lower() == "development":
            try:
                Base.metadata.create_all(bind=engine)
                logger.info("Base tables created/verified (development)")
            except Exception as e:
                logger.warning(f"Could not create base tables: {e}")

        try:
            ensure_enrichment_columns()
            logger.info("Enrichment columns ensured")
        except Exception as e:
            logger.warning(f"Could not ensure enrichment columns: {e}")

        try:
            ensure_postgres_indexes()
            logger.info("PostgreSQL indexes created")
        except Exception as e:
            logger.warning(f"Could not create indexes: {e}")

        logger.info("Database schema initialization completed")
    except Exception as e:
        logger.error(f"Database schema initialization failed: {e}")
        # Don't crash the app, but log the error
        pass
    finally:
        # Nature Wall is in-memory and independent from DB; always start scheduler.
        start_news_scheduler()



@app.on_event("shutdown")
async def shutdown_event():
    """Stop background schedulers gracefully."""
    stop_news_scheduler()

def _get_search_results(db, q: str, page: int):
    """
    Shared search + pagination logic. Returns dict with sites, platform_icons, page, etc.

    Note: Tags are hidden from frontend response (exposed only in API).
    """
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
        # Debug: Log heat stamp data pipeline
        if sites:
            logger.debug(f"Search query '{q}' returned {len(sites)} sites; first site heat_score={sites[0].heat_score}")
    else:
        current_page = 1
        sites = []
        total_results = 0
        total_pages = 1
        has_previous = False
        has_next = False

    # Update last_used_at for returned sites (non-blocking)
    try:
        for s in sites:
            try:
                crud.update_site_usage(db, s.id)
            except Exception:
                pass  # silently fail; never break read operations
    except Exception:
        pass

    platform_icons = [get_platform_icon_svg(s.platform) for s in sites]

    # Prepare site data for frontend: include heat stamp fields
    sites_data = []
    for site in sites:
        site_dict = {
            "id": site.id,
            "website_url": site.website_url,
            "platform": site.platform,
            "industry": site.industry,
            "platforms": site.platforms or [],
            "industries": site.industries or [],
            "colors": site.colors or {},
            "last_used_at": site.last_used_at.isoformat() if site.last_used_at else None,
            "heat_score": float(site.heat_score) if site.heat_score is not None else 0.0,
        }
        sites_data.append(site_dict)

    return {
        "sites": sites_data,
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
def index(request: Request, q: str = "", page: int = 1, db: Session = Depends(get_db)):
    ctx = _get_search_results(db, q, page)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request, **ctx},
    )


@app.get("/add-sites", response_class=HTMLResponse)
def add_sites_page(request: Request):
    """Add Sites page (UI only). No upload logic wired."""
    return templates.TemplateResponse(request=request, name="add-sites.html", context={"request": request})


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = "", page: int = 1, db: Session = Depends(get_db)):
    """Returns only the results section HTML (partial) for AJAX replacement."""
    ctx = _get_search_results(db, q, page)
    return templates.TemplateResponse(
        request=request,
        name="results.html",
        context={"request": request, **ctx},
    )


@app.get("/api/suggestions")
def suggestions(q: str = "", db: Session = Depends(get_db)):
    """
    Return autocomplete suggestions for search.
    Useful for "Did you mean…" functionality.
    """
    q = (q or "").strip()
    if len(q) < 2:
        return JSONResponse({"suggestions": []})

    sugg = crud.get_search_suggestions(db, q, limit=5)
    return JSONResponse({"suggestions": sugg})


def insert_pre_enriched_row(db: Session, row: dict) -> tuple[bool, str]:
    """
    Insert a pre-enriched row directly into the database.

    Returns (success, error_message)
    """
    try:
        url = row.get("website_url", "").strip()

        # Check if site already exists
        existing = db.query(Site).filter(Site.website_url == url).first()
        if existing:
            return False, "Site already exists"

        # Parse JSON fields
        platforms = json.loads(row.get("platforms", "[]")) if row.get("platforms") else []
        industries = json.loads(row.get("industries", "[]")) if row.get("industries") else []
        colors = json.loads(row.get("colors", "{}")) if row.get("colors") else {}
        tag_confidence = json.loads(row.get("tag_confidence", "{}")) if row.get("tag_confidence") else {}
        enrichment_signals = json.loads(row.get("enrichment_signals", "{}")) if row.get("enrichment_signals") else {}

        # Parse timestamp
        last_enriched_at = None
        if row.get("last_enriched_at"):
            try:
                last_enriched_at = datetime.fromisoformat(row["last_enriched_at"].replace('Z', '+00:00'))
            except ValueError:
                pass

        # Create site
        site = Site(
            website_url=url,
            platform=row.get("platform", ""),
            industry=row.get("industry", ""),
            tags=row.get("tags", ""),
            platforms=platforms if platforms else None,
            industries=industries if industries else None,
            colors=colors if colors else None,
            tag_confidence=tag_confidence if tag_confidence else None,
            enrichment_signals=enrichment_signals if enrichment_signals else None,
            last_enriched_at=last_enriched_at,
            created_at=datetime_naive.now(),
            updated_at=datetime_naive.now()
        )

        db.add(site)
        db.commit()
        return True, ""

    except Exception as e:
        db.rollback()
        return False, str(e)


@app.post("/upload-csv")
async def upload_csv(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Bulk upload sites via CSV with automatic enrichment.

    Safe processing: one bad row does not fail the entire batch.
    Returns success count, failure count, and error details per row.

    CSV should have a 'website_url' column.

    Rate limited: 2 uploads per IP per minute.
    Max file size: 5 MB. Max rows: 500.
    """
    async def event_stream():
        ip = get_client_ip(request)
        logger.info(f"POST /upload-csv from {ip}: {file.filename}")

        # Rate limiting
        if not upload_csv_limiter.is_allowed(ip):
            logger.warning(f"Upload rate limit hit for {ip}")
            yield f"data: {{\"error\": \"Too many uploads. Please wait before trying again.\"}}\n\n"
            return

        if not file.filename or not file.filename.endswith(".csv"):
            logger.warning(f"Invalid file type from {ip}: {file.filename}")
            yield f"data: {{\"error\": \"Only CSV files are allowed\"}}\n\n"
            return

        try:
            content = await file.read()
        except Exception as e:
            logger.error(f"Failed to read file from {ip}: {e}")
            yield f"data: {{\"error\": \"Failed to read file\"}}\n\n"
            return

        # Validate file size
        file_size = len(content)
        if file_size > 5 * 1024 * 1024:  # 5 MB
            logger.warning(f"CSV too large from {ip}: {file_size} bytes")
            yield f"data: {{\"error\": \"File too large (max 5 MB)\"}}\n\n"
            return

        try:
            decoded = content.decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to decode CSV from {ip}: {e}")
            yield f"data: {{\"error\": \"Failed to decode CSV (must be UTF-8)\"}}\n\n"
            return

        reader = csv.DictReader(io.StringIO(decoded))
        if not reader.fieldnames or "website_url" not in reader.fieldnames:
            logger.warning(f"Invalid CSV format from {ip}: missing website_url column")
            yield f"data: {{\"error\": \"CSV must have a 'website_url' column\"}}\n\n"
            return

        # Check if CSV contains pre-enriched data
        enriched_columns = {"platforms", "industries", "colors", "tag_confidence", "enrichment_signals", "last_enriched_at"}
        is_pre_enriched = enriched_columns.issubset(set(reader.fieldnames or []))

        if is_pre_enriched:
            logger.info(f"CSV from {ip} contains pre-enriched data - skipping enrichment step")
            yield f"data: {{\"message\": \"Detected pre-enriched CSV - fast import mode\"}}\n\n"
        else:
            logger.info(f"CSV from {ip} needs enrichment - standard processing")
            yield f"data: {{\"message\": \"CSV needs enrichment - standard processing\"}}\n\n"

        try:
            db = SessionLocal()
            success_count = 0
            failure_count = 0
            errors = []
            row_idx = 2
            total_rows = sum(1 for _ in csv.DictReader(io.StringIO(content.decode("utf-8"))))
            processed = 0
            yield f"data: {{\"progress\":0}}\n\n"
            for row in csv.DictReader(io.StringIO(content.decode("utf-8"))):
                # Enforce row limit
                if row_idx - 2 >= 500:  # 500 data rows max
                    logger.warning(f"CSV row limit exceeded from {ip}")
                    errors.append({
                        "row": row_idx,
                        "url": "",
                        "error": "CSV exceeds 500-row limit",
                    })
                    break

                url = row.get("website_url", "").strip()
                if not url:
                    failure_count += 1
                    errors.append({"row": row_idx, "url": url, "error": "Empty URL"})
                    row_idx += 1
                    continue

                if is_pre_enriched:
                    # Fast path: insert pre-enriched data directly
                    ok, error_msg = insert_pre_enriched_row(db, row)
                    if ok:
                        success_count += 1
                        logger.info(f"Row {row_idx}: ✅ {url} (pre-enriched)")
                    else:
                        failure_count += 1
                        logger.warning(f"Row {row_idx}: ❌ {url} - {error_msg}")
                        errors.append({
                            "row": row_idx,
                            "url": url,
                            "error": error_msg or "Failed to insert pre-enriched data",
                        })
                else:
                    # Standard path: run enrichment pipeline
                    ok, error_msg, result = enrich_and_persist(db, url)
                    if ok:
                        success_count += 1
                        logger.info(f"Row {row_idx}: ✅ {url}")
                    else:
                        failure_count += 1
                        logger.warning(f"Row {row_idx}: ❌ {url} - {error_msg}")
                        errors.append({
                            "row": row_idx,
                            "url": url,
                            "error": error_msg or "Unknown error",
                        })

                row_idx += 1
                processed += 1
                percent = int((processed / total_rows) * 100)
                yield f"data: {{\"progress\":{percent}}}\n\n"
                time.sleep(0.01)

            db.close()
            yield f"data: {{\"progress\":100, \"status\":\"complete\"}}\n\n"
        except Exception as e:
            yield f"data: {{\"progress\":0, \"status\":\"error\", \"error\":\"{str(e)}\"}}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/tag-feedback")
async def tag_feedback(website_url: str = Form(...), suggested_tags: str = Form(...), db: Session = Depends(get_db)):
    """
    Anonymous tag feedback endpoint.

    Suggestions are stored for review and future self‑improvement, but are NOT
    auto-applied to the live catalog (no auth / moderation yet).
    """
    url = (website_url or "").strip()
    if not url or not suggested_tags.strip():
        return {"status": "ignored"}

    site = db.query(Site).filter(Site.website_url == url).first()
    fb = TagFeedback(
        site_id=site.id if site else None,
        website_url=url,
        suggested_tags=suggested_tags.strip(),
        created_at=datetime_naive.now(),
    )
    db.add(fb)
    db.commit()

    return {"status": "ok"}


@app.post("/add-site")
async def add_site(request: Request, website_url: str = Form(...), db: Session = Depends(get_db)):
    """
    Add a single site with automatic enrichment.

    Accepts a URL, runs the centralized enrichment pipeline,
    and returns the enriched result or error.

    Rate limited: 10 requests per IP per minute.
    """
    ip = get_client_ip(request)
    url = (website_url or "").strip()
    logger.info(f"POST /add-site from {ip}: {url}")

    # Rate limiting
    if not add_site_limiter.is_allowed(ip):
        logger.warning(f"Rate limit hit for {ip}")
        return JSONResponse(
            {"error": "Too many requests. Please wait before trying again."},
            status_code=429,
        )

    if not url:
        return JSONResponse(
            {"error": "URL is required"},
            status_code=400,
        )

    # Avoid re-enriching rows that are already present; this gives users clear feedback
    # and prevents accidental updates from duplicate submissions.
    existing_site = db.query(Site).filter(Site.website_url == url).first()
    if existing_site:
        return JSONResponse(
            {
                "status": "error",
                "error": "Site already exists.",
            },
            status_code=409,
        )

    try:
        success, error_msg, result = enrich_and_persist(db, url)
        if success and result:
            logger.info(f"✅ Successfully enriched {url}")
            return JSONResponse(
                {
                    "status": "success",
                    "message": "Site added successfully.",
                    "site": result.to_dict(),
                },
                status_code=201,
            )
        else:
            logger.error(f"❌ Failed to enrich {url}: {error_msg}")
            return JSONResponse(
                {
                    "status": "error",
                    "error": error_msg or "Unknown error during enrichment",
                },
                status_code=400,
            )
    except Exception as e:
        logger.error(f"Unexpected error in /add-site: {e}")
        return JSONResponse(
            {
                "status": "error",
                "error": "Internal server error",
            },
            status_code=500,
        )
    # DB session closed by dependency


@app.get("/api/sites/recent")
def recent_sites(limit: int = 10, db: Session = Depends(get_db)):
    """
    Return recently created sites for lightweight UI refreshes.

    The Add Site page uses this endpoint to reflect inserts immediately
    after enrichment and DB persistence complete.
    """
    clamped_limit = max(1, min(limit, 50))
    sites = (
        db.query(Site)
        .order_by(Site.id.desc())
        .limit(clamped_limit)
        .all()
    )

    return JSONResponse(
        {
            "sites": [
                {
                    "id": site.id,
                    "website_url": site.website_url,
                    "platform": site.platform,
                    "industry": site.industry,
                }
                for site in sites
            ]
        }
    )


@app.get("/nature-wall", response_class=HTMLResponse)
def nature_wall_page(request: Request):
    """Public visual news portal page."""
    return templates.TemplateResponse(request=request, name="nature-wall.html", context={"request": request})


@app.get("/api/nature-news")
def nature_news():
    """Return cached nature/science articles for Nature Wall."""
    return JSONResponse({"articles": news_cache})


@app.get("/music-wall", response_class=HTMLResponse)
def music_wall_page(request: Request):
    """Public music portal page with Audius-backed audio playback."""
    return templates.TemplateResponse(request=request, name="music-wall.html", context={"request": request})


@app.get("/not-games", response_class=HTMLResponse)
def not_games_page(request: Request):
    """Placeholder hub for upcoming lightweight browser games."""
    return templates.TemplateResponse(request=request, name="not-games.html", context={"request": request})


@app.get("/api/music/search")
async def music_search(q: str = ""):
    """Search songs via Audius API with local fallback."""
    raw = await fetch_from_audius(q)
    normalized = normalize_audius_response(raw)
    if not normalized["songs"]:
        fallback = fallback_search(q)
        if not fallback["songs"]:
            return JSONResponse({"songs": [], "error": "Music service temporarily unavailable"})
        return JSONResponse({**fallback, "fallback": True})
    return JSONResponse(normalized)


@app.get("/api/music/home")
async def music_home():
    """Return sectioned home feed for Music Wall."""
    sections = []
    for title, query in HOME_QUERIES:
        raw = await fetch_from_audius(query)
        normalized = normalize_audius_response(raw)
        songs = normalized["songs"] if normalized["songs"] else fallback_search(query)["songs"]
        sections.append({"title": title, "query": query, "songs": songs})
    return JSONResponse({"sections": sections})


@app.get("/health/db")
def health_db():
    """
    Database connectivity health check endpoint.

    Attempts SELECT 1 query to verify database connection.

    Returns:
        200 OK: {"status": "ok"} if database is reachable
        500 Error: {"status": "error", "detail": "..."} if database is unreachable
    """
    try:
        if check_database_connection():
            return JSONResponse(
                {"status": "ok"},
                status_code=200
            )
        else:
            return JSONResponse(
                {"status": "error", "detail": "Database connection check failed"},
                status_code=500
            )
    except Exception as e:
        logger.error(f"DB health check failed: {e}")
        return JSONResponse(
            {"status": "error", "detail": str(e)},
            status_code=500
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
