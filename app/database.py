import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

# Use DATABASE_URL from environment. Fail fast if missing.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

# SQLAlchemy engine with sensible pooling for production
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=int(os.getenv("DB_POOL_SIZE", 5)),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", 10)),
    pool_recycle=int(os.getenv("DB_POOL_RECYCLE", 1800)),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def ensure_enrichment_columns():
    """
    Add enrichment columns to existing 'sites' table if missing.
    Safe to run multiple times; no-op when table missing or columns exist.
    PostgreSQL-specific implementation using JSONB for complex data types.
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
    except SQLAlchemyError:
        # Fail gracefully; schema migration should be managed explicitly in production
        return


def ensure_postgres_indexes():
    """
    Create PostgreSQL-specific indexes for improved query performance.
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
    except SQLAlchemyError:
        # Ignore index creation errors in production
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

