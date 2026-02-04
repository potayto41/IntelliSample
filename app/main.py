from datetime import datetime as datetime_naive
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from .database import SessionLocal, engine, ensure_enrichment_columns, ensure_postgres_indexes
from .models import Base, Site, TagFeedback
from . import crud
from .enrichment import enrich_and_persist
from .write_safety import add_site_limiter, upload_csv_limiter, validate_csv_upload, get_client_ip
from .platform_icons import get_platform_icon_svg
import csv
import io
import json
import logging
import math
import time
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Note: Base.metadata.create_all() moved to startup event to avoid import-time database operations

app = FastAPI()

# Point to the actual static directory name in this project ("Static")
app.mount("/static", StaticFiles(directory="app/Static"), name="static")
templates = Jinja2Templates(directory="app/templates")

PAGE_SIZE = 10

@app.on_event("startup")
async def startup_event():
    """Initialize database schema and ensure enrichment columns exist."""
    try:
        logger.info("Running database schema initialization...")
        # Only run schema creation if we're not using a managed database
        # For Neon/PostgreSQL cloud services, tables should already exist
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Base tables created/verified")
        except Exception as e:
            logger.warning(f"Could not create base tables (might already exist in managed DB): {e}")

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
    else:
        current_page = 1
        sites = []
        total_results = 0
        total_pages = 1
        has_previous = False
        has_next = False

    # Update last_used_at for returned sites (non-blocking)
    for site in sites:
        try:
            crud.update_site_usage(db, site.id)
        except Exception:
            pass  # silently fail; never break read operations

    platform_icons = [get_platform_icon_svg(s.platform) for s in sites]
    
    # Prepare site data for frontend: hide tags, expose last_used_at
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


@app.get("/api/suggestions")
def suggestions(q: str = ""):
    """
    Return autocomplete suggestions for search.
    Useful for "Did you mean…" functionality.
    """
    q = (q or "").strip()
    if len(q) < 2:
        return JSONResponse({"suggestions": []})

    db = SessionLocal()
    try:
        sugg = crud.get_search_suggestions(db, q, limit=5)
        return JSONResponse({"suggestions": sugg})
    finally:
        db.close()

@app.post("/upload-csv")
async def upload_csv(request: Request, file: UploadFile = File(...)):
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

                # Run enrichment pipeline independently per row
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
async def add_site(request: Request, website_url: str = Form(...)):
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

    db = SessionLocal()
    try:
        success, error_msg, result = enrich_and_persist(db, url)
        if success and result:
            logger.info(f"✅ Successfully enriched {url}")
            return JSONResponse(
                {
                    "status": "success",
                    "message": f"Site {url} added successfully",
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
    finally:
        db.close()
