#!/usr/bin/env bash
# =============================================================================
# Supabase Transaction Pooler Configuration Script
# =============================================================================
# Use this script to set the DATABASE_URL environment variable for 
# Supabase Transaction Pooler connection in WSO2 Choreo.
#
# Steps:
# 1. Get your Supabase pooler connection string from Dashboard
# 2. Update the DATABASE_URL value below
# 3. Set it in Choreo: Project → Settings → Env Variables
#
# =============================================================================

# EXAMPLE CONFIGURATION
# Replace with YOUR actual values from Supabase Dashboard

# Get from Supabase:
# - Settings → Database
# - Connection pooler (dropdown)
# - Select "Session" (or "Transaction" for Supabase Postgres)
# - Copy the entire connection string

# Format verification:
# ✓ Scheme: postgresql+psycopg2://
# ✓ Host: aws-0-us-east-1.pooler.supabase.com (or your region)
# ✓ Port: 6543
# ✓ Database: postgres
# ✓ Query string: ?sslmode=require

# CORRECT FORMAT (WSO2 Choreo / Production):
# postgresql+psycopg2://postgres.xxxxxxxxxxxxx:PASSWORD@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require

# For WSO2 Choreo deployment:
# 1. Copy your Supabase pooler connection string
# 2. Go to Choreo Console → Project → Settings
# 3. Under "Environment Variables", set:
#    Name: DATABASE_URL
#    Value: (paste connection string here)
# 4. Save and redeploy

# For local development (.env file):
# Create/update .env in project root with:
export DATABASE_URL="postgresql+psycopg2://postgres.xxxxxxxxxxxxx:PASSWORD@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require"

# Optional: Pool configuration (if needed)
# Default values are optimized for Supabase pooler - uncomment only if changing
# export DB_POOL_SIZE=1
# export DB_MAX_OVERFLOW=2
# export DB_POOL_RECYCLE=300

echo "Database URL configured"
echo "Verify with: curl http://localhost:8000/health/db"
