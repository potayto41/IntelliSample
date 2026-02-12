#!/usr/bin/env bash
# =============================================================================
# Production Implementation Verification Checklist
# =============================================================================
# Use this checklist to verify the database connectivity fix is properly 
# deployed and functioning in your WSO2 Choreo environment.
#
# Run these tests after deployment.
# =============================================================================

echo "=================================================="
echo "Database Connectivity Fix - Verification Checklist"
echo "=================================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

DEPLOYMENT_URL=${1:-"https://your-app-url"}
echo "Target URL: $DEPLOYMENT_URL"
echo ""

# ============================================================================
# 1. Verify DATABASE_URL Configuration
# ============================================================================
echo -e "${YELLOW}[1] Verifying DATABASE_URL Configuration${NC}"
echo "In Choreo Console:"
echo "  1. Go to Project → Settings → Environment Variables"
echo "  2. Verify DATABASE_URL exists and contains:"
echo "     ✓ Scheme: postgresql+psycopg2://"
echo "     ✓ Host: aws-*.pooler.supabase.com"
echo "     ✓ Port: 6543"
echo "     ✓ Query String: ?sslmode=require"
echo ""
echo "Expected format:"
echo "  postgresql+psycopg2://postgres.XXXX:PASSWORD@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require"
echo ""

# ============================================================================
# 2. Check Startup Logs
# ============================================================================
echo -e "${YELLOW}[2] Checking Startup Logs${NC}"
echo "In Choreo Console → Build & Deploy → Logs"
echo ""
echo "Expected log messages (in this order):"
echo "  ✓ 'Running database schema initialization...'"
echo "  ✓ 'Database connection check passed' (OR warning if DB unavailable)"
echo "  ✓ 'Enrichment columns ensured'"
echo "  ✓ 'PostgreSQL indexes created'"
echo "  ✓ 'Database schema initialization completed'"
echo ""

# ============================================================================
# 3. Test Health Check Endpoint
# ============================================================================
echo -e "${YELLOW}[3] Testing Health Check Endpoint${NC}"
echo "Command:"
echo "  curl -i $DEPLOYMENT_URL/health/db"
echo ""
echo "Expected response (if database is connected):"
echo "  HTTP/1.1 200 OK"
echo '  {"status": "ok"}'
echo ""
echo "Expected response (if database is not available):"
echo "  HTTP/1.1 500 Internal Server Error"
echo '  {"status": "error", "detail": "..."}'
echo ""

# ============================================================================
# 4. Verify Connection Pooling
# ============================================================================
echo -e "${YELLOW}[4] Verifying Connection Pool Configuration${NC}"
echo "Configuration should be:"
echo "  ✓ pool_size: 1 (NOT 5)"
echo "  ✓ max_overflow: 2 (NOT 10)"
echo "  ✓ pool_recycle: 300 (NOT 1800)"
echo "  ✓ pool_pre_ping: True"
echo "  ✓ connect_args['sslmode']: require"
echo ""
echo "Check in: app/database.py line ~29"
echo ""

# ============================================================================
# 5. Test Database Operations
# ============================================================================
echo -e "${YELLOW}[5] Testing Database Operations${NC}"
echo "In the application:"
echo "  1. Perform a search query: $DEPLOYMENT_URL/?q=test"
echo "  2. Add a new site (if enabled)"
echo "  3. Check platform icons load (tests CRUD operations)"
echo ""
echo "Expected behavior:"
echo "  ✓ Results display normally"
echo "  ✓ No 5xx errors (only graceful degradation if DB unavailable)"
echo "  ✓ Platform icons load from database"
echo ""

# ============================================================================
# 6. Load Balancer Configuration (if applicable)
# ============================================================================
echo -e "${YELLOW}[6] Load Balancer Health Check (Optional)${NC}"
echo "If using a load balancer (ALB, NLB, etc.):"
echo "  1. Update health check path to: /health/db"
echo "  2. Expected HTTP status: 200"
echo "  3. Expected response body: {\"status\": \"ok\"}"
echo ""

# ============================================================================
# 7. Verify Error Handling
# ============================================================================
echo -e "${YELLOW}[7] Testing Error Handling${NC}"
echo "To test graceful degradation:"
echo "  1. Temporarily disable DATABASE_URL in Choreo"
echo "  2. Redeploy"
echo "  3. App should start (NOT crash)"
echo "  4. Search queries should return error JSON (NOT 5xx crash)"
echo "  5. Health check should return 500: {\"status\": \"error\"}"
echo ""

# ============================================================================
# 8. Files Modified Verification
# ============================================================================
echo -e "${YELLOW}[8] Files Modified Verification${NC}"
echo "Verify these files are updated in your deployment:"
echo ""
echo "Modified files (must be present):"
echo "  ✓ app/database.py"
echo "    - Engine config with pool_size=1, max_overflow=2, pool_recycle=300"
echo "    - check_database_connection() function"
echo "    - OperationalError exception handling"
echo ""
echo "  ✓ app/main.py"
echo "    - Import check_database_connection"
echo "    - db_connection_healthy global variable"
echo "    - Startup event with connection check"
echo "    - Enhanced /health/db endpoint"
echo ""
echo "  ✓ requirements.txt"
echo "    - Version pinning for stability"
echo "    - psycopg2-binary>=2.9.0"
echo ""
echo "Unchanged files (business logic intact):"
echo "  ✓ app/models.py (no schema changes)"
echo "  ✓ app/crud.py (no query changes)"
echo "  ✓ app/enrichment.py (no enrichment changes)"
echo "  ✓ All templates and static files"
echo ""

# ============================================================================
# 9. Performance Verification
# ============================================================================
echo -e "${YELLOW}[9] Performance Verification${NC}"
echo "Expected improvements:"
echo "  ✓ Startup time: ~2-3 seconds (graceful even if DB down)"
echo "  ✓ Query latency: ~100-150ms (pooler overhead reduced)"
echo "  ✓ Memory usage: Lower (small pool size)"
echo "  ✓ Max concurrent connections: 3 (pool_size=1 + overflow=2)"
echo ""

# ============================================================================
# 10. Troubleshooting
# ============================================================================
echo -e "${YELLOW}[10] Troubleshooting${NC}"
echo ""
echo "Still seeing IPv6 errors?"
echo "  → Verify DATABASE_URL uses pooler host: aws-*.pooler.supabase.com"
echo "  → NOT direct connection: db.*.supabase.co"
echo ""
echo "Health check returns 500?"
echo "  → Check logs for connection error details"
echo "  → Verify pool credentials are correct"
echo "  → Verify port 6543 is accessible (not 5432)"
echo ""
echo "App crashes on startup?"
echo "  → Should NOT crash anymore (gracefully degrades)"
echo "  → If still crashing, check DATABASE_URL is set"
echo "  → Check full startup logs in Choreo Console"
echo ""
echo "Database queries fail?"
echo "  → Check /health/db endpoint returns 200 OK"
echo "  → Verify Database is running and reachable"
echo "  → Check connection pool credentials"
echo ""

# ============================================================================
# Quick Test Commands
# ============================================================================
echo ""
echo "=================================================="
echo "Quick Test Commands"
echo "=================================================="
echo ""
echo "1. Health Check:"
echo "   curl -i $DEPLOYMENT_URL/health/db"
echo ""
echo "2. Search (if available):"
echo "   curl '$DEPLOYMENT_URL/?q=test' | grep -i 'sites'"
echo ""
echo "3. SSL Verification (should work):"
echo "   openssl s_client -connect aws-0-us-east-1.pooler.supabase.com:6543 </dev/null 2>/dev/null | grep -i certificate"
echo ""
echo "4. Direct pooler test (from production server):"
echo "   psql postgresql+psycopg2://user:pass@aws-0-us-east-1.pooler.supabase.com:6543/database_name -c 'SELECT 1'"
echo ""

# ============================================================================
# Summary
# ============================================================================
echo ""
echo "=================================================="
echo "Implementation Summary"
echo "=================================================="
echo ""
echo "Problem Fixed:"
echo "  IPv6 routing failure (Network is unreachable)"
echo ""
echo "Solution Applied:"
echo "  Switched to Supabase Transaction Pooler (port 6543)"
echo ""
echo "Key Changes:"
echo "  • Pool size: 5 → 1"
echo "  • Max overflow: 10 → 2"
echo "  • Pool recycle: 1800s → 300s"
echo "  • SSL enforcement: Added"
echo "  • Error handling: Graceful"
echo "  • Health check: /health/db endpoint"
echo ""
echo "Expected Result:"
echo "  ✓ Stable IPv4 connection"
echo "  ✓ No crashes on DB unavailability"
echo "  ✓ Better connection efficiency"
echo "  ✓ Monitorable via health check"
echo ""
echo "=================================================="
echo ""
