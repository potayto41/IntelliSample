import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError, OperationalError

logger = logging.getLogger(__name__)

# Use DATABASE_URL from environment. Fail fast if missing.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

# Detect database type and optimize pool settings accordingly
is_supabase_pooler = "pooler.supabase.com" in DATABASE_URL
is_supabase_direct = "supabase.co" in DATABASE_URL
is_render = "render.com" in DATABASE_URL or "postgres.railway.app" in DATABASE_URL
is_localhost = "localhost" in DATABASE_URL

# Set pool defaults based on database type
if is_supabase_pooler:
    # Supabase Transaction Pooler: Small pools (server-side pooling)
    default_pool_size = 1
    default_max_overflow = 2
    default_pool_recycle = 300
    logger.info("Detected: Supabase Transaction Pooler (port 6543)")
elif is_render or is_supabase_direct:
    # Render or direct Supabase: Can handle standard pools
    default_pool_size = 5
    default_max_overflow = 10
    default_pool_recycle = 3600
    logger.info(f"Detected: {'Render' if is_render else 'Supabase direct'} PostgreSQL")
elif is_localhost:
    # Local development: Use efficient pool settings
    default_pool_size = 5
    default_max_overflow = 10
    default_pool_recycle = 3600
    logger.info("Detected: Local PostgreSQL (development)")
else:
    # Unknown: Use conservative settings
    default_pool_size = 3
    default_max_overflow = 5
    default_pool_recycle = 1800
    logger.warning(f"Unknown database host in: {DATABASE_URL[:50]}... Using conservative pool settings")

# SQLAlchemy engine configuration (auto-tuned by database type)
connect_args = {"sslmode": "require"}
if is_localhost:
    # Local development: SSL optional
    connect_args = {}

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Test connection before use (prevents stale connections)
    pool_size=int(os.getenv("DB_POOL_SIZE", default_pool_size)),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", default_max_overflow)),
    pool_recycle=int(os.getenv("DB_POOL_RECYCLE", default_pool_recycle)),
    connect_args=connect_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Track database connection status
db_connection_healthy = False


def check_database_connection() -> bool:
    """
    Verify database connection is active.
    Returns True if successful, False otherwise.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (OperationalError, SQLAlchemyError) as e:
        logger.error(f"Database connection check failed: {e}")
        return False


def ensure_enrichment_columns():
    """
    Add enrichment columns to existing 'sites' table if missing.
    Safe to run multiple times; no-op when table missing or columns exist.
    PostgreSQL-specific implementation using JSONB for complex data types.
    Fails gracefully if database is unavailable.
    """
    cols_to_add = [
        ("industries", "JSONB"),
        ("platforms", "JSONB"),
        ("colors", "JSONB"),
        ("tag_confidence", "JSONB"),
        ("last_enriched_at", "TIMESTAMP WITH TIME ZONE"),
        ("enrichment_signals", "JSONB"),
        ("last_used_at", "TIMESTAMP WITH TIME ZONE"),
        ("heat_score", "FLOAT"),
        ("site_metadata", "JSONB"),
        ("created_at", "TIMESTAMP WITH TIME ZONE"),
        ("updated_at", "TIMESTAMP WITH TIME ZONE"),
    ]

    try:
        with engine.connect() as conn:
            # Check if sites table exists
            result = conn.execute(text(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='sites')"
            ))
            table_exists = result.scalar()

            if not table_exists:
                return

            # Get existing columns
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='sites'"
            ))
            existing = {row[0] for row in result}

            # Add missing columns
            for name, typ in cols_to_add:
                if name not in existing:
                    conn.execute(text(f'ALTER TABLE sites ADD COLUMN "{name}" {typ}'))
                    conn.commit()
    except (OperationalError, SQLAlchemyError) as e:
        # Fail gracefully; schema migration should be managed explicitly in production
        logger.warning(f"Could not ensure enrichment columns: {e}")
        return


def ensure_postgres_indexes():
    """
    Create PostgreSQL-specific indexes for improved query performance.
    Fails gracefully if database is unavailable.
    """
    indexes = [
        ("idx_sites_url", "sites", "website_url"),
        ("idx_sites_platform", "sites", "platform"),
        ("idx_sites_industry", "sites", "industry"),
        ("idx_sites_last_used_at", "sites", "last_used_at"),
        ("idx_sites_heat_score", "sites", "heat_score DESC"),
        ("idx_sites_created_at", "sites", "created_at DESC"),
    ]

    try:
        with engine.connect() as conn:
            for idx_name, table_name, columns in indexes:
                try:
                    conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name} ({columns})"))
                    conn.commit()
                except Exception:
                    # Index may already exist; ignore gracefully
                    pass
    except (OperationalError, SQLAlchemyError) as e:
        # Ignore index creation errors in production; log for visibility
        logger.warning(f"Could not create indexes: {e}")
        return


def get_db():
    """
    Dependency for FastAPI endpoints. Yields a new DB session per request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

