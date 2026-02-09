cripty# Migration to Supabase Database

## Steps to Complete Migration

- [x] Update DATABASE_URL in app/config/postgres.py to use Supabase URL
- [x] Create database tables on Supabase using SQLAlchemy models
- [x] Run bulk import script to populate data from sites_enriched.csv
- [ ] Seed heat data using seed_heat_data.py
- [ ] Test connection and verify data import
- [ ] Run the app to ensure it works with Supabase
