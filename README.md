# Smart Sample Search - FastAPI Backend

A FastAPI application for searching and managing sample websites with automatic enrichment.

## Deployment on WSO2 Choreo

This application is configured for container-based deployment on WSO2 Choreo.

### Environment Variables

Set the following environment variables in your Choreo service:

- `DATABASE_URL`: PostgreSQL connection string (e.g., `postgresql://user:pass@host:5432/db`)
- `PORT`: Port for the application to listen on (defaults to 8080)

### Container Startup

The application starts with a single command using Gunicorn with Uvicorn workers:

```bash
gunicorn -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:8080
```

### Database Configuration

- Uses Supabase PostgreSQL
- Connection pooling optimized for long-running services
- `pool_pre_ping=True` for connection health checks
- Pool size: 5, Max overflow: 10

### Local Development

To run locally:

```bash
python run_server.py
```

Or with Uvicorn directly:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

### API Endpoints

- `GET /`: Main search interface
- `GET /search`: AJAX search results
- `GET /add-sites`: Add sites interface
- `POST /add-site`: Add single site with enrichment
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
