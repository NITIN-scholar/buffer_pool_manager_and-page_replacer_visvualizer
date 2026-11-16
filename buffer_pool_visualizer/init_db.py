"""Create the tables and sample pages without needing psql installed.

    py init_db.py

Reads DATABASE_URL from the environment or from a .env file.
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

try:
    import psycopg
except ImportError:
    sys.exit("psycopg is not installed. Run: py -m pip install -r requirements.txt")

url = os.environ.get("DATABASE_URL", "").strip()
if not url:
    sys.exit("DATABASE_URL is not set. Copy .env.example to .env and edit it.")

schema = (BASE_DIR / "schema.sql").read_text(encoding="utf-8")

try:
    with psycopg.connect(url, connect_timeout=5) as conn:
        conn.execute(schema)
except Exception as error:
    sys.exit(f"Could not set up the database: {error}")

print("Database ready: disk_storage and memory_logs exist, sample pages loaded.")
