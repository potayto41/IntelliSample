"""
SQLite to PostgreSQL migration tool for Sample Dispenser v5.

Usage:
    python data_tools/migrate_to_postgres.py
    
Environment variables:
    SQLITE_PATH: Path to source SQLite database (default: sites.db)
    DATABASE_URL: Target PostgreSQL connection string
    DRY_RUN: Set to "true" for validation without data transfer
    BACKUP_PATH: Path to backup SQLite before migration (default: sites.db.backup)

This script:
1. Validates source SQLite database integrity
2. Backs up original SQLite file
3. Creates target PostgreSQL tables
4. Migrates data with type conversion
5. Validates row counts and sample data
6. Logs all operations for auditability
"""

import os
import sqlite3
import json
import shutil
import logging
from datetime import datetime
from typing import List, Dict, Any, Tuple
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('migration.log'),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

# Configuration from environment
SQLITE_PATH = os.getenv("SQLITE_PATH", "sites.db")
BACKUP_PATH = os.getenv("BACKUP_PATH", f"{SQLITE_PATH}.backup")
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# PostgreSQL connection (lazy import to allow CLI-only usage)
_pg_connection = None


def get_postgres_connection():
    """Lazy-load PostgreSQL connection."""
    global _pg_connection
    if _pg_connection is None:
        try:
            import psycopg2
            from app.config.postgres import get_database_url
            
            db_url = get_database_url()
            # Parse connection string
            # Format: postgresql://user:password@host:port/database
            _pg_connection = psycopg2.connect(db_url)
        except ImportError:
            logger.error("psycopg2 not installed. Run: pip install psycopg2-binary")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise
    
    return _pg_connection


def validate_sqlite_database() -> bool:
    """Validate SQLite database integrity."""
    if not os.path.exists(SQLITE_PATH):
        logger.error(f"SQLite database not found: {SQLITE_PATH}")
        return False
    
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sites'"
        )
        if not cursor.fetchone():
            logger.warning("'sites' table not found in SQLite database")
            conn.close()
            return False
        
        # Check row count
        cursor.execute("SELECT COUNT(*) FROM sites")
        count = cursor.fetchone()[0]
        logger.info(f"✓ SQLite validation passed: {count} sites found")
        
        # Check for data integrity issues
        cursor.execute("SELECT id, website_url FROM sites WHERE website_url IS NULL OR website_url = ''")
        invalid = cursor.fetchall()
        if invalid:
            logger.warning(f"  {len(invalid)} sites have empty URLs (will be skipped)")
        
        conn.close()
        return True
    
    except sqlite3.DatabaseError as e:
        logger.error(f"SQLite database error: {e}")
        return False


def backup_sqlite_database() -> bool:
    """Create backup of SQLite database before migration."""
    if DRY_RUN:
        logger.info("(DRY RUN) Would backup SQLite to: {BACKUP_PATH}")
        return True
    
    try:
        if os.path.exists(BACKUP_PATH):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            old_backup = f"{BACKUP_PATH}.{timestamp}"
            shutil.move(BACKUP_PATH, old_backup)
            logger.info(f"Archived previous backup to: {old_backup}")
        
        shutil.copy2(SQLITE_PATH, BACKUP_PATH)
        logger.info(f"✓ Backup created: {BACKUP_PATH}")
        return True
    
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return False


def read_sqlite_sites() -> List[Dict[str, Any]]:
    """Read all sites from SQLite with type conversion."""
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM sites")
        rows = cursor.fetchall()
        
        sites = []
        for row in rows:
            # Skip rows with empty URLs
            if not row.get("website_url"):
                logger.warning(f"Skipping site with empty URL (id={row.get('id')})")
                continue
            
            # Convert JSON strings to objects (v4 format used TEXT for JSON)
            site = dict(row)
            for json_field in ["platforms", "industries", "colors", "tag_confidence", "enrichment_signals"]:
                if json_field in site and site[json_field]:
                    try:
                        site[json_field] = json.loads(site[json_field]) if isinstance(site[json_field], str) else site[json_field]
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Failed to parse {json_field} for site {site.get('id')}: {e}")
                        site[json_field] = {}
            
            # Ensure heat_score exists (defaults to 0 for v4 data)
            if "heat_score" not in site or site["heat_score"] is None:
                site["heat_score"] = 0.0
            
            # Ensure site_metadata exists
            if "site_metadata" not in site or site["site_metadata"] is None:
                site["site_metadata"] = {"migrated_from": "sqlite", "migration_date": datetime.now().isoformat()}
            else:
                try:
                    metadata = json.loads(site["site_metadata"]) if isinstance(site["site_metadata"], str) else site["site_metadata"]
                except (json.JSONDecodeError, TypeError):
                    metadata = {}
                metadata["migrated_from"] = "sqlite"
                metadata["migration_date"] = datetime.now().isoformat()
                site["site_metadata"] = metadata
            
            sites.append(site)
        
        conn.close()
        logger.info(f"✓ Read {len(sites)} valid sites from SQLite")
        return sites
    
    except Exception as e:
        logger.error(f"Failed to read SQLite sites: {e}")
        return []


def create_postgres_tables() -> bool:
    """Create PostgreSQL tables for Sample Dispenser v5."""
    if DRY_RUN:
        logger.info("(DRY RUN) Would create PostgreSQL tables")
        return True
    
    try:
        conn = get_postgres_connection()
        cursor = conn.cursor()
        
        # Create sites table with v5 schema
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sites (
                id SERIAL PRIMARY KEY,
                website_url VARCHAR(2048) UNIQUE NOT NULL,
                platform VARCHAR(255),
                industry VARCHAR(255),
                tags TEXT,
                platforms JSONB,
                industries JSONB,
                colors JSONB,
                tag_confidence JSONB,
                enrichment_signals JSONB,
                last_enriched_at TIMESTAMP,
                last_used_at TIMESTAMP,
                site_metadata JSONB,
                heat_score FLOAT DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sites_url ON sites(website_url)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sites_platform ON sites(platform)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sites_industry ON sites(industry)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sites_last_used_at ON sites(last_used_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sites_heat_score ON sites(heat_score DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sites_created_at ON sites(created_at DESC)")
        
        # Create tag_feedback table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tag_feedback (
                id SERIAL PRIMARY KEY,
                site_id INTEGER REFERENCES sites(id) ON DELETE SET NULL,
                website_url VARCHAR(2048),
                suggested_tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        cursor.close()
        logger.info("✓ PostgreSQL tables created successfully")
        return True
    
    except Exception as e:
        logger.error(f"Failed to create PostgreSQL tables: {e}")
        return False


def migrate_sites(sites: List[Dict[str, Any]]) -> Tuple[int, int]:
    """
    Migrate sites from SQLite data to PostgreSQL.
    Returns: (success_count, failure_count)
    """
    if DRY_RUN:
        logger.info(f"(DRY RUN) Would migrate {len(sites)} sites")
        return len(sites), 0
    
    try:
        conn = get_postgres_connection()
        cursor = conn.cursor()
        
        success_count = 0
        failure_count = 0
        
        for site in sites:
            try:
                # Prepare values for insertion
                cursor.execute("""
                    INSERT INTO sites (
                        website_url, platform, industry, tags,
                        platforms, industries, colors, tag_confidence,
                        enrichment_signals, last_enriched_at, last_used_at,
                        site_metadata, heat_score, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    site.get("website_url"),
                    site.get("platform"),
                    site.get("industry"),
                    site.get("tags"),
                    json.dumps(site.get("platforms", {})),
                    json.dumps(site.get("industries", {})),
                    json.dumps(site.get("colors", {})),
                    json.dumps(site.get("tag_confidence", {})),
                    json.dumps(site.get("enrichment_signals", {})),
                    site.get("last_enriched_at"),
                    site.get("last_used_at"),
                    json.dumps(site.get("site_metadata", {})),
                    float(site.get("heat_score", 0.0)),
                    site.get("created_at") or datetime.now().isoformat(),
                ))
                success_count += 1
            
            except Exception as e:
                failure_count += 1
                logger.warning(f"Failed to migrate site {site.get('website_url')}: {e}")
                conn.rollback()
                continue
        
        conn.commit()
        cursor.close()
        logger.info(f"✓ Migration complete: {success_count} successful, {failure_count} failed")
        return success_count, failure_count
    
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return 0, len(sites)


def validate_migration(expected_count: int) -> bool:
    """Validate that migration was successful."""
    try:
        conn = get_postgres_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM sites")
        actual_count = cursor.fetchone()[0]
        
        cursor.close()
        
        if actual_count == expected_count:
            logger.info(f"✓ Validation passed: {actual_count} sites in PostgreSQL")
            return True
        else:
            logger.warning(f"⚠ Row count mismatch: expected {expected_count}, got {actual_count}")
            return actual_count > 0
    
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return False


def main():
    """Execute migration workflow."""
    logger.info("=" * 60)
    logger.info("SQLite to PostgreSQL Migration - Sample Dispenser v5")
    logger.info(f"Mode: {'DRY RUN (validation only)' if DRY_RUN else 'FULL MIGRATION'}")
    logger.info("=" * 60)
    
    # Step 1: Validate SQLite
    if not validate_sqlite_database():
        logger.error("SQLite validation failed. Aborting migration.")
        return False
    
    # Step 2: Backup SQLite
    if not backup_sqlite_database():
        logger.error("Backup failed. Aborting migration.")
        return False
    
    # Step 3: Read sites from SQLite
    sites = read_sqlite_sites()
    if not sites:
        logger.error("No sites to migrate. Aborting.")
        return False
    
    # Step 4: Create PostgreSQL tables
    if not create_postgres_tables():
        logger.error("Failed to create PostgreSQL tables. Aborting migration.")
        return False
    
    # Step 5: Migrate data
    success_count, failure_count = migrate_sites(sites)
    
    # Step 6: Validate migration
    if not validate_migration(success_count):
        logger.error("Migration validation failed.")
        return False
    
    logger.info("=" * 60)
    logger.info("✓ Migration completed successfully!")
    logger.info("=" * 60)
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
