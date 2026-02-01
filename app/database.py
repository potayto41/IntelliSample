from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

# SQLite database file (auto-created)
DATABASE_URL = "sqlite:///./sites.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
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
    SQLite stores JSON/DateTime as TEXT.
    """
    cols_to_add = [
        ("industries", "TEXT"),
        ("platforms", "TEXT"),
        ("colors", "TEXT"),
        ("tag_confidence", "TEXT"),
        ("last_enriched_at", "TEXT"),
        ("enrichment_signals", "TEXT"),
        ("last_used_at", "TEXT"),
    ]
    with engine.connect() as conn:
        r = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sites'"
        ))
        if not r.fetchone():
            return
        r = conn.execute(text("PRAGMA table_info(sites)"))
        existing = {row[1] for row in r} if r else set()
        for name, typ in cols_to_add:
            if name not in existing:
                conn.execute(text(f'ALTER TABLE sites ADD COLUMN "{name}" {typ}'))
                conn.commit()
