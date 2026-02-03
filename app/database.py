import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool

# PostgreSQL configuration
from app.config.postgres import get_sqlalchemy_url, get_pool_config
DATABASE_URL = get_sqlalchemy_url()

# Create PostgreSQL engine with connection pooling
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

    with engine.connect() as conn:
        for idx_name, table_name, columns in indexes:
            try:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name} ({columns})"))
                conn.commit()
            except Exception as e:
                # Index may already exist; ignore gracefully
                pass

