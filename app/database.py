import os
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool, QueuePool

# Database URL detection (PostgreSQL takes precedence)
_USE_POSTGRES = os.getenv("USE_POSTGRES", "false").lower() == "true"

if _USE_POSTGRES:
    # PostgreSQL configuration (v5+)
    from app.config.postgres import get_sqlalchemy_url, get_pool_config
    DATABASE_URL = get_sqlalchemy_url()
else:
    # SQLite configuration (v3-v4 legacy)
    DATABASE_URL = "sqlite:///./sites.db"

# Create engine with appropriate pooling strategy
if _USE_POSTGRES:
    pool_config = get_pool_config()
    engine = create_engine(
        DATABASE_URL,
        poolclass=QueuePool,
        pool_size=pool_config["pool_size"],
        max_overflow=pool_config["max_overflow"],
        pool_timeout=pool_config["pool_timeout"],
        pool_recycle=pool_config["pool_recycle"],
        pool_pre_ping=pool_config["pool_pre_ping"],
    )
else:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # SQLite optimization
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def ensure_enrichment_columns():
    """
    Add enrichment columns to existing 'sites' table if missing.
    Safe to run multiple times; no-op when table missing or columns exist.
    Supports both SQLite (TEXT) and PostgreSQL (JSON/JSONB).
    """
    cols_to_add = [
        ("industries", "TEXT"),
        ("platforms", "TEXT"),
        ("colors", "TEXT"),
        ("tag_confidence", "TEXT"),
        ("last_enriched_at", "TEXT"),
        ("enrichment_signals", "TEXT"),
        ("last_used_at", "TEXT"),
        ("heat_score", "FLOAT"),  # v5 - add for all databases
        ("site_metadata", "TEXT"),  # v5 - SQLite uses TEXT for JSON
        ("created_at", "TEXT"),  # v5 - SQLite uses TEXT for DateTime
        ("updated_at", "TEXT"),  # v5 - SQLite uses TEXT for DateTime
    ]
    
    with engine.connect() as conn:
        # Check if sites table exists
        if _USE_POSTGRES:
            # PostgreSQL introspection
            result = conn.execute(text(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='sites')"
            ))
            table_exists = result.scalar()
        else:
            # SQLite introspection
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sites'"
            ))
            table_exists = result.fetchone() is not None
        
        if not table_exists:
            return
        
        # Get existing columns
        if _USE_POSTGRES:
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='sites'"
            ))
            existing = {row[0] for row in result}
        else:
            result = conn.execute(text("PRAGMA table_info(sites)"))
            existing = {row[1] for row in result} if result else set()
        
        # Add missing columns
        for name, typ in cols_to_add:
            if name not in existing:
                conn.execute(text(f'ALTER TABLE sites ADD COLUMN "{name}" {typ}'))
                conn.commit()


def ensure_postgres_indexes():
    """
    Create PostgreSQL-specific indexes for improved query performance.
    Only runs when USE_POSTGRES=true.
    """
    if not _USE_POSTGRES:
        return
    
    indexes = [
        ("idx_sites_url", "sites", "website_url"),
        ("idx_sites_platform", "sites", "platform"),
        ("idx_sites_industry", "sites", "industry"),
        ("idx_sites_last_used_at", "sites", "last_used_at"),
        ("idx_sites_heat_score", "sites", "heat_score DESC"),
        ("idx_sites_created_at", "sites", "created_at DESC"),
    ]
    
    with engine.connect() as conn:
        for idx_name, table_name, columns in indexes:
            try:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name} ({columns})"))
                conn.commit()
            except Exception as e:
                # Index may already exist; ignore gracefully
                pass

