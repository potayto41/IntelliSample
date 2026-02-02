"""
Quick PostgreSQL connection test.
Usage:
    python test_postgres_connection.py <DATABASE_URL>
Example:
    python test_postgres_connection.py postgresql://user:password@localhost:5432/sample_dispenser
"""

import sys
import os

if len(sys.argv) < 2:
    print("Usage: python test_postgres_connection.py <DATABASE_URL>")
    print("Example: python test_postgres_connection.py postgresql://user:password@localhost:5432/db")
    sys.exit(1)

db_url = sys.argv[1]
print(f"Testing connection to: {db_url.split('@')[1] if '@' in db_url else 'database'}")

try:
    import psycopg2
    from urllib.parse import urlparse
    
    parsed = urlparse(db_url)
    
    conn = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=parsed.path.lstrip('/'),
        user=parsed.username,
        password=parsed.password
    )
    
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    print("✓ Connection successful!")
    print(f"✓ Database: {parsed.path.lstrip('/')}")
    
except Exception as e:
    print(f"✗ Connection failed: {e}")
    sys.exit(1)
