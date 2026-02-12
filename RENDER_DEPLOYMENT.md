# Render Deployment Guide

## Quick Start: Deploy to Render

### Prerequisites
- GitHub account (repo connected to Render)
- Render account (free tier available)
- Render Postgres database (existing or new)

---

## Step 1: Get Your Render Database Connection String

### Option A: Using Existing Render Database

1. Go to Render Dashboard → Databases
2. Click your PostgreSQL database
3. Copy the **External Database URL** (looks like):
   ```
   postgresql://user:password@dpg-xxxx.render.com:5432/database_name?sslmode=require
   ```

### Option B: Create New Database on Render

1. Render Dashboard → New → PostgreSQL
2. Choose plan (free or paid)
3. Set name, username, password
4. After creation, get the External Database URL

---

## Step 2: Connect GitHub to Render

1. Go to Render Dashboard → New → Web Service
2. Select "Deploy from GitHub"
3. Authorize GitHub and connect your repository
4. Select repository: `potayto41/IntelliSample` (or your fork)
5. Select branch: `main`

---

## Step 3: Configure Web Service on Render

### Basic Settings
- **Name:** `sample-search` (or your preferred name)
- **Root Directory:** (leave empty if render.yaml is in root)
- **Runtime:** Python 3.11
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn -w 4 -b 0.0.0.0:$PORT app.main:app`

### Environment Variables

Click **Add Environment Variables** and set:

| Key | Value |
|-----|-------|
| `DATABASE_URL` | `postgresql://user:password@dpg-xxxx.render.com:5432/database_name?sslmode=require` |
| `ENVIRONMENT` | `production` |

**Important:** Copy your DATABASE_URL from Render database exactly, including `?sslmode=require`

### Advanced Settings (Optional)
- **Plan:** Standard or Pay-as-you-go
- **Region:** Select closest to your users
- **Health Check Path:** `/health/db` (recommended)

---

## Step 4: Deploy

1. Click **Create Web Service**
2. Render auto-deploys from your GitHub repo
3. Watch logs for: `Database connection check passed`
4. Once deployed, test with: `curl https://your-app-url.onrender.com/health/db`

---

## Verify Deployment

### Check Startup Logs
Render Dashboard → Your Service → Logs

Expected output:
```
Running database schema initialization...
Detected: Render PostgreSQL
Database connection check passed
Enrichment columns ensured
PostgreSQL indexes created
Database schema initialization completed
```

### Test Health Check
```bash
curl https://your-app-url.onrender.com/health/db
# Expected: {"status": "ok"}
```

### Test Search
```bash
curl "https://your-app-url.onrender.com/?q=test"
# Should return HTML with search results
```

---

## DATABASE_URL Format for Different Providers

### Render (Your setup)
```
postgresql://postgres:password@dpg-xxxx.render.com:5432/sampleforge?sslmode=require
```
✅ Recommended format (direct connection, good pooling support)

### Supabase with Transaction Pooler
```
postgresql+psycopg2://postgres.xxxx:password@aws-0-region.pooler.supabase.com:6543/postgres?sslmode=require
```
✅ For Supabase pooler (auto-tunes pool_size=1)

### Supabase Direct Connection
```
postgresql://postgres.xxxx:password@db.xxxx.supabase.co:5432/postgres?sslmode=require
```
⚠️ May cause IPv6 issues in cloud environments

### Local Development
```
postgresql://user:password@localhost:5432/sampleforge
```
✓ SSL not required locally

---

## Connection Pool Auto-Tuning

The app automatically detects your database type and optimizes pooling:

| Database | Pool Size | Overflow | Recycle |
|----------|-----------|----------|---------|
| **Render** | 5 | 10 | 3600s |
| **Supabase Pooler** | 1 | 2 | 300s |
| **Supabase Direct** | 5 | 10 | 3600s |
| **Local** | 5 | 10 | 3600s |

### Override Defaults (if needed)
Add env vars in Render:
```
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_RECYCLE=3600
```

---

## Troubleshooting

### "Database connection check failed"
- **Check:** Is DATABASE_URL set in Render env vars?
- **Check:** Does DATABASE_URL include `?sslmode=require`?
- **Check:** Is the database online in Render?
- Run: `curl https://app/health/db` to see specific error

### App crashes on deploy
- Check startup logs: Render → Your Service → Logs
- If "OperationalError": Database unreachable
  - Verify DATABASE_URL is correct
  - Verify Render database is running
  - Wait 1-2 minutes for database to be ready

### "port 5432: Connection refused"
- Check DATABASE_URL port is `5432` (not `6543`, that's Supabase pooler)
- For Render: Must be port `5432`
- For Supabase Pooler: Must be port `6543`

### Slow queries
- Check DB_POOL_SIZE (Render should be 5)
- Check health: `curl /health/db`
- Monitor logs: Render → Logs

---

## Auto-Deployment from GitHub

Every time you push to `main` branch, Render auto-deploys:

```bash
# Make changes locally
git add .
git commit -m "Update: ..."
git push origin main

# Render automatically:
# 1. Pulls latest code
# 2. Installs dependencies (pip install -r requirements.txt)
# 3. Runs startCommand (gunicorn)
# 4. Deploys new service
```

Monitor in Render Dashboard → Your Service → Deploys

---

## Performance Tips for Render

### 1. Use Standard Plan or Higher
- Free tier has limitations and sleeps
- Standard plan: $7/month (always running)
- Better for production apps

### 2. Connect to Same-Region Database
- If database is in `oregon`, deploy web service to `oregon`
- Reduces latency

### 3. Monitor Health Check
- Render Dashboard → Health Checks
- Shows uptime and response times

### 4. Set Up Error Monitoring
- Render sends logs to Render Dashboard
- Monitor: Render → Your Service → Logs

### 5. Scale if Needed
- If getting rate limit errors, increment concurrency (adjust gunicorn `-w` flag)
- Default `-w 4` = 4 worker processes

---

## Database Backups

### Render PostgreSQL Backups
1. Render Dashboard → Your Database → Backups
2. Multi-day backups included (paid plans)
3. Can restore from UI

### Export Data
```bash
# Export from Render database
pg_dump postgresql://user:password@dpg-xxxx.render.com:5432/database_name > backup.sql

# Import to another database
psql postgresql://user:password@new-host:5432/database_name < backup.sql
```

---

## Cost Breakdown

| Component | Free Tier | Standard Plan |
|-----------|-----------|---------------|
| Web Service | $0 (sleeps) | $7/month |
| PostgreSQL | $0 (limited) | $15/month |
| **Total** | **$0** | **~$22/month** |

Free tier:
- Good for testing and development
- Web service goes to sleep after 15 min inactivity
- Limited database storage (1GB)
- Not recommended for production

Standard tier:
- Always running (no sleep)
- Better for production apps
- Better backups and monitoring

---

## Environment Variables Reference

### Database Configuration
```bash
DATABASE_URL=postgresql://user:pass@host:5432/db?sslmode=require  # REQUIRED
ENVIRONMENT=production                                             # Optional (default: production)
```

### Connection Pooling (auto-detected, usually no need to set)
```bash
DB_POOL_SIZE=5              # For Render (or leave unset for auto)
DB_MAX_OVERFLOW=10
DB_POOL_RECYCLE=3600
```

### Application
```bash
APP_HOST=0.0.0.0            # Default
APP_PORT=8080               # Render sets this automatically
```

---

## Next Steps

1. ✅ Get Render database URL
2. ✅ Connect GitHub to Render
3. ✅ Set DATABASE_URL env variable
4. ✅ Deploy
5. ✅ Test health check: `curl /health/db`
6. ✅ Set up monitoring (optional)
7. ✅ Configure custom domain (optional)

---

## Support

- **Render Docs:** https://render.com/docs
- **PostgreSQL Help:** https://www.postgresql.org/docs/
- **FastAPI Docs:** https://fastapi.tiangolo.com/
- **SQLAlchemy Pools:** https://docs.sqlalchemy.org/en/20/core/pooling.html

---

## Quick Commands

```bash
# Test health locally (before deployment)
python -m uvicorn app.main:app --reload

# Then curl from another terminal:
curl http://localhost:8000/health/db

# View logs in Render
# Dashboard → Your Service → Logs

# Restart service in Render
# Dashboard → Your Service → Settings → Restart
```
