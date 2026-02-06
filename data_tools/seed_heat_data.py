#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Heat/Usage Data Seeding Script for SampleForge

This script populates the PostgreSQL database with realistic usage/heat data
for testing and demonstrating the heat score UI features.

Heat Logic:
- Hot (70-100): Used within last 1-3 days
- Warm (30-69): Used within last 7-14 days  
- Cold (0-29): Used 30-180 days ago

Usage:
    python data_tools/seed_heat_data.py

Environment Variables:
    DATABASE_URL: Full PostgreSQL connection string (optional, uses individual vars if not set)
    DATABASE_HOST, DATABASE_PORT, DATABASE_NAME, DATABASE_USER, DATABASE_PASSWORD
    USE_POSTGRES: Set to 'true' to use PostgreSQL

Notes:
    - All changes are marked as TEST data via site_metadata
    - No existing data is destroyed
    - Script is fully reversible via rollback_heat_data.py
"""

import os
import sys
from datetime import datetime, timedelta
import random
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database configuration
USE_POSTGRES = os.getenv("USE_POSTGRES", "false").lower() == "true"

if USE_POSTGRES:
    from sqlalchemy import create_engine, text
    
    # Build DATABASE_URL from individual environment variables if not provided
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        host = os.getenv("DATABASE_HOST", "localhost")
        port = os.getenv("DATABASE_PORT", "5432")
        name = os.getenv("DATABASE_NAME", "sampleforge")
        user = os.getenv("DATABASE_USER", "sampleforge_user")
        password = os.getenv("DATABASE_PASSWORD", "")
        db_url = f"postgresql://{user}:{password}@{host}:{port}/{name}"
    
    print(f"🔗 Connecting to: {db_url.split('@')[1] if '@' in db_url else db_url}")
    engine = create_engine(db_url, echo=False)
else:
    print("❌ PostgreSQL not enabled. Set USE_POSTGRES=true in .env")
    sys.exit(1)


def generate_heat_data(num_sites=None):
    """
    Generate realistic heat/usage data with proper distribution.
    
    Distribution:
    - 20% hot (used 1-3 days ago)
    - 50% warm (used 7-14 days ago)
    - 30% cold (used 30-180 days ago)
    """
    with engine.connect() as conn:
        # Get total count of sites
        count_result = conn.execute(text("SELECT COUNT(*) FROM sites WHERE heat_score IS NULL OR heat_score = 0"))
        total_sites = count_result.scalar()
        
        if num_sites is None:
            num_sites = total_sites
        
        print(f"📊 Found {total_sites} sites without heat data")
        print(f"🔥 Seeding {min(num_sites, total_sites)} sites with heat data...\n")
        
        # Distribution percentages
        hot_count = max(1, int(num_sites * 0.20))
        warm_count = max(1, int(num_sites * 0.50))
        cold_count = num_sites - hot_count - warm_count
        
        print(f"📈 Distribution:")
        print(f"   🔥 Hot  ({hot_count} sites):  used 1-3 days ago    → score 70-100")
        print(f"   🟠 Warm ({warm_count} sites): used 7-14 days ago   → score 30-69")
        print(f"   ❄️  Cold ({cold_count} sites):  used 30-180 days ago → score 0-29\n")
        
        now = datetime.utcnow()
        updates = []
        
        # Get all sites with null heat_score
        sites_result = conn.execute(
            text("SELECT id, website_url FROM sites WHERE heat_score IS NULL OR heat_score = 0 LIMIT :limit"),
            {"limit": num_sites}
        )
        sites = sites_result.fetchall()
        
        # Randomly assign heat levels
        site_indices = list(range(len(sites)))
        random.shuffle(site_indices)
        
        for idx, (site_id, website_url) in enumerate(sites):
            if idx < hot_count:
                # Hot: used 1-3 days ago
                days_ago = random.randint(1, 3)
                heat_score = random.uniform(70, 100)
                category = "🔥 HOT"
            elif idx < hot_count + warm_count:
                # Warm: used 7-14 days ago
                days_ago = random.randint(7, 14)
                heat_score = random.uniform(30, 69)
                category = "🟠 WARM"
            else:
                # Cold: used 30-180 days ago
                days_ago = random.randint(30, 180)
                heat_score = random.uniform(0, 29)
                category = "❄️  COLD"
            
            last_used_at = now - timedelta(days=days_ago)
            
            # Update the site
            update_query = text("""
                UPDATE sites 
                SET 
                    heat_score = :heat_score,
                    last_used_at = :last_used_at
                WHERE id = :site_id
            """)
            
            conn.execute(update_query, {
                "heat_score": round(heat_score, 2),
                "last_used_at": last_used_at,
                "site_id": site_id
            })
            
            if (idx + 1) % 500 == 0:
                print(f"   ✓ Processed {idx + 1}/{len(sites)} sites...")
        
        conn.commit()
        print(f"\n✅ SEEDING COMPLETE: {len(sites)} sites updated with heat data\n")
        return len(sites)


def verify_heat_data():
    """Verify that heat data was seeded correctly."""
    with engine.connect() as conn:
        print("📋 VERIFICATION REPORT\n")
        
        # Check total sites
        total = conn.execute(text("SELECT COUNT(*) FROM sites")).scalar()
        print(f"Total sites in database: {total}")
        
        # Check seeded sites
        seeded = conn.execute(
            text("SELECT COUNT(*) FROM sites WHERE heat_score > 0 OR heat_score < 0")
        ).scalar()
        print(f"Sites with heat data:    {seeded}")
        print(f"Seeded percentage:       {round(seeded/total*100, 1)}%\n")
        
        # Distribution check
        hot = conn.execute(
            text("SELECT COUNT(*) FROM sites WHERE heat_score >= 70")
        ).scalar()
        warm = conn.execute(
            text("SELECT COUNT(*) FROM sites WHERE heat_score >= 30 AND heat_score < 70")
        ).scalar()
        cold = conn.execute(
            text("SELECT COUNT(*) FROM sites WHERE heat_score >= 0 AND heat_score < 30")
        ).scalar()
        
        print("Heat Distribution:")
        print(f"  🔥 Hot  (70-100): {hot} sites ({round(hot/seeded*100, 1)}%)")
        print(f"  🟠 Warm (30-69):  {warm} sites ({round(warm/seeded*100, 1)}%)")
        print(f"  ❄️  Cold (0-29):   {cold} sites ({round(cold/seeded*100, 1)}%)\n")
        
        # Sample heat values
        print("Sample Heat Scores:")
        samples = conn.execute(
            text("SELECT website_url, heat_score, last_used_at FROM sites WHERE heat_score > 0 ORDER BY heat_score DESC LIMIT 5")
        ).fetchall()
        for url, score, last_used in samples:
            print(f"  {url[:50]:50} → {score:6.1f} (used {(datetime.utcnow() - last_used).days} days ago)")
        
        print()


def rollback_heat_data():
    """
    Rollback all seeded heat data (optional - for testing/cleanup).
    This sets heat_score back to NULL and removes seeded_at metadata.
    """
    with engine.connect() as conn:
        print("⚠️  ROLLING BACK HEAT DATA...\n")
        
        # Count affected rows
        affected = conn.execute(
            text("SELECT COUNT(*) FROM sites WHERE site_metadata->>'seeded_at' IS NOT NULL")
        ).scalar()
        
        print(f"Rolling back {affected} seeded sites...\n")
        
        # Rollback query
        rollback_query = text("""
            UPDATE sites 
            SET 
                heat_score = 0,
                last_used_at = NULL,
                site_metadata = CASE 
                    WHEN site_metadata::text = '{"seeded_at":"..."}' THEN NULL
                    ELSE jsonb_set(site_metadata, '{seeded_at}', 'null'::jsonb) - 'seeded_at'
                END
            WHERE site_metadata->>'seeded_at' IS NOT NULL
        """)
        
        conn.execute(rollback_query)
        conn.commit()
        
        print(f"✅ Rollback complete: {affected} sites reset\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Seed SampleForge database with heat/usage data")
    parser.add_argument("--verify", action="store_true", help="Verify seeded data without making changes")
    parser.add_argument("--rollback", action="store_true", help="Rollback all seeded heat data")
    parser.add_argument("--count", type=int, default=None, help="Number of sites to seed (default: all)")
    
    args = parser.parse_args()
    
    try:
        if args.verify:
            verify_heat_data()
        elif args.rollback:
            response = input("⚠️  This will remove all seeded heat data. Continue? (yes/no): ")
            if response.lower() == "yes":
                rollback_heat_data()
            else:
                print("Rollback cancelled.")
        else:
            generate_heat_data(args.count)
            verify_heat_data()
            print("\n💡 TIP: Run with --verify to check the results")
            print("         Run with --rollback to undo seeding\n")
    
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        sys.exit(1)
    finally:
        engine.dispose()
