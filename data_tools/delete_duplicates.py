#!/usr/bin/env python
"""
Delete duplicate sites from PostgreSQL database.

This script removes duplicate entries based on website_url, keeping only the most recent one
(by created_at timestamp).

Usage:
    python delete_duplicates.py

Requirements:
    - PostgreSQL database configured via environment variables
    - All dependencies installed
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal, engine
from app.models import Site, Base
from app.config.postgres import get_sqlalchemy_url
from sqlalchemy import text


def delete_duplicate_sites() -> dict:
    """
    Delete duplicate sites, keeping only the most recent entry for each website_url.

    Returns dict with deletion statistics.
    """
    print("🔄 Starting duplicate deletion...")

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Find duplicates
        print("🔍 Finding duplicate sites...")

        # Query to find duplicates
        duplicates_query = text("""
            SELECT website_url, COUNT(*) as count
            FROM sites
            GROUP BY website_url
            HAVING COUNT(*) > 1
            ORDER BY count DESC
        """)

        duplicates = db.execute(duplicates_query).fetchall()
        print(f"📊 Found {len(duplicates)} website_urls with duplicates")

        total_deleted = 0
        total_processed = 0

        for website_url, count in duplicates:
            # For each duplicate group, keep the most recent (by created_at)
            keep_query = text("""
                SELECT id FROM sites
                WHERE website_url = :url
                ORDER BY created_at DESC
                LIMIT 1
            """)

            keep_id = db.execute(keep_query, {'url': website_url}).scalar()

            # Delete all others
            delete_query = text("""
                DELETE FROM sites
                WHERE website_url = :url AND id != :keep_id
            """)

            result = db.execute(delete_query, {'url': website_url, 'keep_id': keep_id})
            deleted_count = result.rowcount

            total_deleted += deleted_count
            total_processed += 1

            if total_processed % 100 == 0:
                print(f"📊 Processed {total_processed} duplicate groups, deleted {total_deleted} sites...")

        db.commit()
        print(f"✅ Deleted {total_deleted} duplicate sites")

        return {
            'duplicate_groups': len(duplicates),
            'total_deleted': total_deleted
        }

    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def main():
    """Main entry point."""
    try:
        # Check database connection
        print("🔍 Checking database connection...")
        db_url = get_sqlalchemy_url()
        print("✅ Database configuration found")

        # Run deletion
        results = delete_duplicate_sites()

        print("\n📊 Deletion Results:")
        print(f"🔄 Duplicate groups processed: {results['duplicate_groups']}")
        print(f"🗑️  Sites deleted: {results['total_deleted']}")

        print("\n🎉 Duplicate deletion complete!")

    except Exception as e:
        print(f"❌ Deletion failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
