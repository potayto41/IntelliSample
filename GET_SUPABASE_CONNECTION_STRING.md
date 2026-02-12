# How to Get Your Supabase Transaction Pooler Connection String

## Step 1: Log into Supabase Dashboard

1. Go to https://supabase.com/dashboard
2. Select your project

## Step 2: Navigate to Database Settings

1. Click **Settings** (bottom left nav)
2. Click **Database** tab
3. Look for **Connection String** section

## Step 3: Select Connection Pooler Mode

This is the CRITICAL step that determines IPv4 vs IPv6:

**Dropdown shows:**
- ⚠️ **Direct connection** (This will fail - uses IPv6, port 5432)
- ✅ **Connection pooler** (This is what you need - uses IPv4, port 6543)

**Click the dropdown and select: Connection pooler**

## Step 4: Copy the Connection String

You should see:

```
postgresql://postgres.XXXXXX:PASSWORD@aws-0-[region].pooler.supabase.com:6543/postgres
```

## Step 5: Create the Correct DATABASE_URL Format

Supabase gives you: `postgresql://...`

**You need to convert it to SQLAlchemy format:**

```
# FROM Supabase (copy):
postgresql://postgres.xxxxxx:PASSWORD@aws-0-us-east-1.pooler.supabase.com:6543/postgres

# CONVERT TO this format:
postgresql+psycopg2://postgres.xxxxxx:PASSWORD@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require
```

**The changes:**
1. Replace `postgresql://` with `postgresql+psycopg2://` (SQLAlchemy driver)
2. Add `?sslmode=require` at the end (enforce SSL)

## Step 6: Set in WSO2 Choreo

1. Go to **Choreo Console**
2. Navigate to your **Project**
3. Click **Settings**
4. Click **Environment Variables** tab
5. Click **+ Add Environment Variable**

**Fill in:**
- **Name:** `DATABASE_URL`
- **Value:** `postgresql+psycopg2://postgres.xxxxxx:PASSWORD@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require`

Click **Save**

## Step 7: Redeploy

Your application will automatically use the new DATABASE_URL after redeployment.

---

## Verification Checklist

Your DATABASE_URL should contain ALL of these:

```
✓ Driver: postgresql+psycopg2://
✓ Host: aws-0-*.pooler.supabase.com (pooler, NOT .supabase.co)
✓ Port: 6543 (NOT 5432)
✓ Query string: ?sslmode=require
```

**Example of CORRECT URL:**
```
postgresql+psycopg2://postgres.abcdef123456:myPassword123@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require
```

**Example of WRONG URLs (will fail):**
```
❌ postgresql://...@db.xxxx.supabase.co:5432/...      (direct connection, IPv6, port 5432)
❌ postgresql+psycopg2://...@aws-0-us-east-1.pooler.supabase.com:5432/...  (wrong port)
❌ postgresql+psycopg2://...@aws-0-us-east-1.pooler.supabase.com:6543/...  (missing sslmode=require)
```

---

## Why This Matters

| Component | Direct Connection | Pooler |
|-----------|-------------------|--------|
| DNS Result | IPv6 (2406:da1a:...) | IPv4 |
| Port | 5432 | 6543 |
| Routing in Choreo | ❌ Not supported | ✅ Works |
| Connection Pooling | Client-side (inefficient) | Server-side (efficient) |
| Connection Reuse | Limited | Excellent |

---

## Common Mistakes

### ❌ WRONG: Using direct connection
```
DATABASE_URL=postgresql://user:pass@db.PROJECT.supabase.co:5432/postgres
```
**Problem:** Direct connection uses IPv6, Choreo can't route IPv6

### ❌ WRONG: Missing sslmode=require
```
DATABASE_URL=postgresql+psycopg2://user:pass@aws-0-us-east-1.pooler.supabase.com:6543/postgres
```
**Problem:** Supabase requires SSL/TLS, connection will fail

### ❌ WRONG: Using wrong port
```
DATABASE_URL=postgresql+psycopg2://user:pass@aws-0-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require
```
**Problem:** Port 5432 is direct connection, pooler is on 6543

### ✅ CORRECT: Properly formatted
```
DATABASE_URL=postgresql+psycopg2://user:pass@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require
```

---

## Testing the Connection

### From your machine (debug):

If psql is installed:
```bash
psql postgresql+psycopg2://postgres.XXXX:PASSWORD@aws-0-us-east-1.pooler.supabase.com:6543/postgres
```

Should connect without "Network is unreachable" errors.

### From your Choreo app:

After deployment:
```bash
curl https://your-app-url/health/db
# Should return: {"status": "ok"}
```

---

## Reference: Supabase Pooler Documentation

- Main docs: https://supabase.com/docs/guides/database/connecting-to-postgres#connection-pooler
- Pooler modes: https://supabase.com/docs/guides/database/connecting-to-postgres#pooling-modes
- Connection pooler setup: https://supabase.com/docs/guides/database/postgres/managing-transactions#transaction-pooler

---

## Getting Help

If you can't find Connection Pooler in Supabase:

1. Make sure you have a **Postgres project** (not SQLite)
2. Check your Supabase plan (some legacy plans may not have pooler)
3. Contact Supabase support: https://supabase.com/support

If `postgresql+psycopg2://` isn't connecting:

1. Verify driver: `pip list | grep psycopg`
2. Check credentials (copy-paste fresh from Supabase)
3. Test with curl /health/db endpoint
4. Check application logs for detailed error
