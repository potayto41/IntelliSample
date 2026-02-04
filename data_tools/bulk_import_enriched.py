#!/usr/bin/env python
"""
Bulk import enriched sites from CSV to PostgreSQL.

This script reads sites_enriched.csv (output from enrich_sites.py) and bulk inserts
the data into PostgreSQL, bypassing the slow per-row enrichment process.

Usage:
    python bulk_import_enriched.py

Requirements:
    - sites_enriched.csv exists in the same directory
    - PostgreSQL database configured via environment variables
    - All dependencies installed
"""

import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal, engine
from app.models import Site, Base
from app.config.postgres import get_sqlalchemy_url


def bulk_import_enriched_sites(csv_path: str = None) -> dict:
    """
    Bulk import enriched sites from CSV to PostgreSQL.

    Returns dict with import statistics.
    """
    # Use data_tools directory path if not provided
    if csv_path is None:
        csv_path = os.path.join(os.path.dirname(__file__), "sites_enriched.csv")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    print(f"🔄 Starting bulk import from {csv_path}")

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        imported = 0
        skipped = 0
        errors = []

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            sites_data = []

            for row_num, row in enumerate(reader, start=2):
                try:
                    url = row.get('website_url', '').strip()
                    if not url:
                        errors.append(f"Row {row_num}: Empty URL")
                        continue

                    # Check if site already exists
                    existing = db.query(Site).filter(Site.website_url == url).first()
                    if existing:
                        print(f"⏭️  Skipping existing site: {url}")
                        skipped += 1
                        continue

                    # Parse JSON fields with fallbacks
                    platforms = []
                    industries = []
                    colors = {}
                    tag_confidence = {}
                    enrichment_signals = {}

                    try:
                        platforms = json.loads(row.get('platforms', '[]')) if row.get('platforms') else []
                    except json.JSONDecodeError:
                        pass

                    try:
                        industries = json.loads(row.get('industries', '[]')) if row.get('industries') else []
                    except json.JSONDecodeError:
                        pass

                    try:
                        colors = json.loads(row.get('colors', '{}')) if row.get('colors') else {}
                    except json.JSONDecodeError:
                        pass

                    try:
                        tag_confidence = json.loads(row.get('tag_confidence', '{}')) if row.get('tag_confidence') else {}
                    except json.JSONDecodeError:
                        pass

                    try:
                        enrichment_signals = json.loads(row.get('enrichment_signals', '{}')) if row.get('enrichment_signals') else {}
                    except json.JSONDecodeError:
                        pass

                    # Parse last_enriched_at
                    last_enriched_at = None
                    if row.get('last_enriched_at'):
                        try:
                            # Handle different datetime formats
                            last_enriched_at = datetime.fromisoformat(row['last_enriched_at'].replace('Z', '+00:00'))
                        except ValueError:
                            pass

                    # Create site object
                    site = Site(
                        website_url=url,
                        platform=row.get('platform', ''),
                        industry=row.get('industry', ''),
                        tags=row.get('tags', ''),
                        platforms=platforms if platforms else None,
                        industries=industries if industries else None,
                        colors=colors if colors else None,
                        tag_confidence=tag_confidence if tag_confidence else None,
                        enrichment_signals=enrichment_signals if enrichment_signals else None,
                        last_enriched_at=last_enriched_at,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc)
                    )

                    sites_data.append(site)
                    imported += 1

                    if imported % 100 == 0:
                        print(f"📊 Processed {imported} sites...")

                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")
                    continue

        # Bulk insert
        if sites_data:
            print(f"💾 Bulk inserting {len(sites_data)} sites...")
            db.bulk_save_objects(sites_data)
            db.commit()
            print("✅ Bulk insert completed!")

        return {
            'imported': imported,
            'skipped': skipped,
            'errors': errors,
            'total_processed': imported + skipped + len(errors)
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

        # Run import
        results = bulk_import_enriched_sites()

        print("\n📊 Import Results:")
        print(f"✅ Sites imported: {results['imported']}")
        print(f"⏭️  Sites skipped (already exist): {results['skipped']}")
        print(f"❌ Errors: {len(results['errors'])}")
        print(f"📈 Total processed: {results['total_processed']}")

        if results['errors']:
            print("\n🚨 Errors encountered:")
            for error in results['errors'][:10]:  # Show first 10 errors
                print(f"  - {error}")
            if len(results['errors']) > 10:
                print(f"  ... and {len(results['errors']) - 10} more")

        print("\n🎉 Bulk import complete!")

    except Exception as e:
        print(f"❌ Import failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()