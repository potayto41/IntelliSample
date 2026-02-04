"""
PostgreSQL configuration and connection pooling for Sample Dispenser.
Supports both Choreo cloud deployment and local development.
"""

import os
from typing import Optional
from urllib.parse import urlparse

# Environment-based configuration
DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")
DATABASE_HOST: str = os.getenv("DATABASE_HOST")
DATABASE_PORT: str = os.getenv("DATABASE_PORT")
DATABASE_NAME: str = os.getenv("DATABASE_NAME")
DATABASE_USER: str = os.getenv("DATABASE_USER")
DATABASE_PASSWORD: str = os.getenv("DATABASE_PASSWORD")

# Connection pooling settings (optimized for Choreo/serverless)
POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "3600"))

# Migration & data settings
ENABLE_DATA_MIGRATION: bool = os.getenv("ENABLE_DATA_MIGRATION", "false").lower() == "true"


def get_database_url() -> str:
    """
    Build PostgreSQL connection string from environment variables.
    Priority: DATABASE_URL env var > Render-style env vars
    """
    if DATABASE_URL:
        return DATABASE_URL
    missing = []
    for var_name, var in zip([
        "DATABASE_HOST", "DATABASE_PORT", "DATABASE_NAME", "DATABASE_USER"
    ], [DATABASE_HOST, DATABASE_PORT, DATABASE_NAME, DATABASE_USER]):
        if not var:
            missing.append(var_name)
    if missing:
        raise RuntimeError(f"Missing required database environment variables: {missing}")
    if DATABASE_PASSWORD:
        return f"postgresql://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
    else:
        return f"postgresql://{DATABASE_USER}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"


def get_sqlalchemy_url() -> str:
    """
    Get SQLAlchemy-compatible PostgreSQL URL with psycopg2 driver.
    """
    url = get_database_url()
    # Replace postgresql:// with postgresql+psycopg2:// for SQLAlchemy
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def get_pool_config() -> dict:
    """
    Return connection pool configuration optimized for serverless/Choreo.
    """
    return {
        "poolclass": "QueuePool",  # Use queue-based pooling for thread safety
        "pool_size": POOL_SIZE,
        "max_overflow": MAX_OVERFLOW,
        "pool_timeout": POOL_TIMEOUT,
        "pool_recycle": POOL_RECYCLE,
        "pool_pre_ping": True,  # Test connection before using (prevents stale connections)
    }


# Endpoint configuration (Choreo-compatible)
APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT: int = int(os.getenv("APP_PORT", "8080"))


if __name__ == "__main__":
    # Debug: print resolved configuration
    print(f"Database URL: {get_database_url()}")
    print(f"SQLAlchemy URL: {get_sqlalchemy_url()}")
    print(f"Pool config: {get_pool_config()}")
    print(f"App endpoint: {APP_HOST}:{APP_PORT}")
