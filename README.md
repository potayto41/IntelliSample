# Smart Sample Search - FastAPI Backend

A FastAPI application for searching and managing sample websites with automatic enrichment.

## Deployment Options

### 🚀 Render Deployment (Recommended)
See [RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md) for step-by-step Render deployment:
- PostgreSQL database on Render
- Auto-deploy from GitHub
- Health check monitoring
- Free tier available for testing

### ☁️ WSO2 Choreo Deployment
See [DATABASE_CONNECTIVITY_FIX.md](DATABASE_CONNECTIVITY_FIX.md) for Choreo deployment with:
- Supabase Transaction Pooler (IPv4, port 6543)
- Automatic pool size tuning
- Graceful error handling
- Production-ready configuration

## Database Connection

The app automatically detects your database and optimizes connection pooling:

| Database | Host | Pool Settings |
|----------|------|---------------|
| Render | `dpg-*.render.com:5432` | pool_size=5, overflow=10 |
| Supabase Pooler | `aws-*.pooler.supabase.com:6543` | pool_size=1, overflow=2 |
| Supabase Direct | `db.*.supabase.co:5432` | pool_size=5, overflow=10 |
| Local | `localhost:5432` | pool_size=5, overflow=10 |

**DATABASE_URL format:**
```
postgresql://user:password@host:port/database?sslmode=require
```

### Environment Variables

Set in your deployment platform:

```bash
DATABASE_URL=postgresql://user:password@host:port/database?sslmode=require
ENVIRONMENT=production
```

Optional (auto-detected by database type):
```bash
DB_POOL_SIZE=5              # Defaults: 5 for Render, 1 for Supabase pooler
DB_MAX_OVERFLOW=10          # Defaults: 10 for Render, 2 for Supabase pooler
DB_POOL_RECYCLE=3600        # Defaults: 3600 for Render, 300 for Supabase pooler
```

### Container Startup

Production (Render, Choreo, etc.):
```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:8080
```

### Local Development

```bash
python run_server.py
```

Or directly with Uvicorn:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

### Health Check Endpoint

- **URL:** `GET /health/db`
- **Success:** `200 OK` with `{"status": "ok"}`
- **Failure:** `500 Error` with `{"status": "error", "detail": "..."}`

Use this endpoint for:
- Load balancer health checks
- Monitoring and alerting
- Database connectivity verification

### API Endpoints

- `GET /`: Main search interface
- `GET /search`: AJAX search results
- `GET /add-sites`: Add sites interface
- `POST /add-site`: Add single site with enrichment
- **NEW:** `GET /health/db`: Database health check
- `POST /upload-csv`: Bulk upload sites via CSV
- `POST /tag-feedback`: Submit tag suggestions
- `GET /api/suggestions`: Search suggestions

### Container Build

Build the Docker image:

```bash
docker build -t smart-sample-search .
```

Run locally:

```bash
docker run -p 8080:8080 -e DATABASE_URL=your_db_url smart-sample-search
