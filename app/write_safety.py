"""
Write safety & abuse protection.

Simple, production-safe mechanisms to prevent write floods and abuse:
  - Per-IP rate limiting for write endpoints
  - CSV upload size/row limits
  - Input validation (defensive)

Uses in-memory state (no external deps, no background workers).
"""

import logging
import time
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)

# ==================================================
# CONFIG
# ==================================================

# Rate limiting: max requests per IP per window
RATE_LIMIT_WINDOW = 60  # seconds
MAX_WRITES_PER_IP = 10  # POST /add-site per minute
MAX_UPLOADS_PER_IP = 2  # POST /upload-csv per minute

# CSV upload limits
MAX_CSV_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_CSV_ROWS = 500  # per upload

# ==================================================
# RATE LIMITER (in-memory)
# ==================================================

class RateLimiter:
    """Simple in-memory rate limiter per IP."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, ip: str) -> bool:
        """Return True if request is allowed, False if rate limited."""
        now = time.time()
        ips_requests = self.requests[ip]

        # Remove old timestamps outside the window
        ips_requests[:] = [t for t in ips_requests if now - t < self.window_seconds]

        if len(ips_requests) >= self.max_requests:
            logger.warning(f"Rate limit exceeded for {ip}")
            return False

        ips_requests.append(now)
        return True


add_site_limiter = RateLimiter(MAX_WRITES_PER_IP, RATE_LIMIT_WINDOW)
upload_csv_limiter = RateLimiter(MAX_UPLOADS_PER_IP, RATE_LIMIT_WINDOW)


# ==================================================
# VALIDATION
# ==================================================


def validate_csv_upload(file_size: int, row_count: int) -> tuple[bool, Optional[str]]:
    """
    Validate CSV upload: size and row count.
    Return (is_valid, error_message).
    """
    if file_size > MAX_CSV_SIZE_BYTES:
        error = f"CSV too large: {file_size} bytes (max {MAX_CSV_SIZE_BYTES})"
        logger.warning(error)
        return False, error

    if row_count > MAX_CSV_ROWS:
        error = f"CSV has too many rows: {row_count} (max {MAX_CSV_ROWS})"
        logger.warning(error)
        return False, error

    return True, None


# ==================================================
# IP EXTRACTION
# ==================================================


def get_client_ip(request) -> str:
    """
    Extract client IP from request.
    Handles X-Forwarded-For and direct connections.
    """
    # X-Forwarded-For for proxies (Choreo, CDN, etc.)
    if request.headers.get("x-forwarded-for"):
        return request.headers["x-forwarded-for"].split(",")[0].strip()

    # Direct connection
    if request.client:
        return request.client.host

    return "unknown"
