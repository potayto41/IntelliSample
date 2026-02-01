"""
Site catalog model. Supports both SQLite (v3-v4) and PostgreSQL (v5+).
All enrichment and v5 fields are nullable for backward compatibility.
"""
from sqlalchemy import Column, Integer, String, DateTime, JSON, Float
from .database import Base


class Site(Base):
    __tablename__ = "sites"

    id = Column(Integer, primary_key=True, index=True)
    website_url = Column(String, unique=True, index=True)

    # Legacy display fields (always used by UI). Populated from first/join of
    # platforms/industries when enriched, or from manual/CSV input.
    platform = Column(String, nullable=True)
    industry = Column(String, nullable=True)
    tags = Column(String, nullable=True)

    # Enrichment schema (nullable; added without breaking existing rows)
    # - industries: ["SaaS", "E-commerce"]
    # - platforms: ["Webflow", "Next.js"]
    # - colors: {"primary": "#0070f3", "secondary": "#7928ca"}
    # - tag_confidence: {"pricing": 0.92, "hero": 0.78}
    industries = Column(JSON, nullable=True)   # list[str]
    platforms = Column(JSON, nullable=True)    # list[str]
    colors = Column(JSON, nullable=True)       # {"primary": str, "secondary": str}
    tag_confidence = Column(JSON, nullable=True)  # {"tag": 0.0..1.0}
    last_enriched_at = Column(DateTime, nullable=True)
    # Raw enrichment signals for debugging / self‑improvement (JSON blob)
    # Example: {"platform_scores": {...}, "industry_scores": {...}, "color_sources": {...}}
    enrichment_signals = Column(JSON, nullable=True)

    # Usage tracking: updated when site is viewed or returned in search/browse results
    # Enables heat score features and sample diversity
    last_used_at = Column(DateTime, nullable=True)
    
    # v5 Features
    # Heat score: popularity metric combining usage count, recency, and engagement
    # Higher = more popular/useful sample. Updated incrementally by ranking/search logic.
    heat_score = Column(Float, nullable=True, default=0.0, index=True)
    
    # Site metadata: rich field storage for future features (search filters, analytics, etc.)
    # Example: {"migrated_from": "sqlite", "source": "csv_import", "original_domain": "..."}
    # Renamed from 'metadata' to 'site_metadata' to avoid SQLAlchemy reserved name conflict
    site_metadata = Column(JSON, nullable=True)
    
    # Timestamps for auditing and expiration
    created_at = Column(DateTime, nullable=True, index=True)
    updated_at = Column(DateTime, nullable=True)



class TagFeedback(Base):
    """
    Anonymous tag feedback.

    Suggestions are stored for review / future retraining but are NOT auto-applied.
    """
    __tablename__ = "tag_feedback"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, nullable=True, index=True)
    website_url = Column(String, nullable=False, index=True)
    suggested_tags = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)
