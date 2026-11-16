"""Storage layer: PostgreSQL when available, JSON files otherwise.

Set DATABASE_URL (or put it in a .env file) to use PostgreSQL, e.g.
    postgresql://postgres:password@localhost:5432/buffer_pool_db

If DATABASE_URL is missing, psycopg is not installed, or the database cannot
be reached, the app keeps working with disk_storage.json and memory_logs.json.
status() reports which backend is active and why.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DISK_FILE = BASE_DIR / "disk_storage.json"
LOG_FILE = BASE_DIR / "memory_logs.json"

try:  # optional: lets a .env file supply DATABASE_URL
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

try:
    import psycopg
except ImportError:  # JSON fallback still works without it
    psycopg = None

RETRY_SECONDS = 5

_state = {"ok": None, "error": None, "checked": 0.0}


class DatabaseError(RuntimeError):
    """A PostgreSQL call failed while PostgreSQL was the active backend."""


# ---------------------------------------------------------------- backend

def _database_url():
    return os.environ.get("DATABASE_URL", "").strip()


def _connect():
    return psycopg.connect(_database_url(), connect_timeout=3)


def use_postgres():
    """True when PostgreSQL is configured and answering."""
    if not _database_url():
        _state.update(ok=False, error=None)
        return False

    if psycopg is None:
        _state.update(
            ok=False,
            error="psycopg is not installed (pip install -r requirements.txt)"
        )
        return False

    if _state["ok"]:
        return True

    if _state["ok"] is False and \
            time.monotonic() - _state["checked"] < RETRY_SECONDS:
        return False

    try:
        with _connect() as conn:
            conn.execute("SELECT 1 FROM disk_storage LIMIT 1")
            conn.execute("SELECT 1 FROM memory_logs LIMIT 1")
        _state.update(ok=True, error=None, checked=time.monotonic())
    except Exception as error:
        _state.update(
            ok=False,
            error=str(error).strip().splitlines()[0],
            checked=time.monotonic()
        )

    return _state["ok"]


def status():
    # Re-probe so the health check reflects the database right now.
    _state.update(ok=None, checked=0.0)
    active = use_postgres()
    return {
        "backend": "postgres" if active else "json",
        "database_url_set": bool(_database_url()),
        "error": None if active else _state["error"]
    }


def _run(action):
    """Run one PostgreSQL action; mark the backend down if it fails."""
    try:
        with _connect() as conn:
            return action(conn)
    except Exception as error:
        _state.update(
            ok=False,
            error=str(error).strip().splitlines()[0],
            checked=time.monotonic()
        )
        raise DatabaseError(f"PostgreSQL error: {_state['error']}") from error


# ------------------------------------------------------------- JSON files

def _read_json(path, default):
    if not path.exists():
        _write_json(path, default)
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ pages

def load_disk():
    """Return every page as {"1": "page data", ...}."""
    if use_postgres():
        def action(conn):
            rows = conn.execute(
                "SELECT page_id, page_data FROM disk_storage ORDER BY page_id"
            ).fetchall()
            return {str(page_id): data for page_id, data in rows}
        return _run(action)

    return _read_json(DISK_FILE, {})


def read_page(page_id):
    """Fetch one page from disk (the SELECT shown in the query box)."""
    if use_postgres():
        def action(conn):
            row = conn.execute(
                "SELECT page_data FROM disk_storage WHERE page_id = %s",
                (page_id,)
            ).fetchone()
            return row[0] if row else None
        return _run(action)

    return _read_json(DISK_FILE, {}).get(str(page_id))


def write_page(page_id, data):
    """Write a dirty page back to disk (the UPDATE shown in the query box)."""
    if use_postgres():
        def action(conn):
            conn.execute(
                "UPDATE disk_storage SET page_data = %s, updated_at = now() "
                "WHERE page_id = %s",
                (data, page_id)
            )
        return _run(action)

    disk = _read_json(DISK_FILE, {})
    disk[str(page_id)] = data
    _write_json(DISK_FILE, disk)


# ------------------------------------------------------------------- logs

def append_log(entry):
    """Store one request log (same keys the frontend already reads)."""
    if use_postgres():
        def action(conn):
            conn.execute(
                "INSERT INTO memory_logs (algorithm_used, page_requested, "
                "operation, status, evicted_page, dirty_writeback, "
                "current_hit_ratio) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    entry["algorithm"], entry["page_requested"],
                    entry["operation"], entry["status"],
                    entry["evicted_page"], entry["dirty_writeback"],
                    entry["hit_ratio"]
                )
            )
        return _run(action)

    logs = _read_json(LOG_FILE, [])
    logs.append(entry)
    _write_json(LOG_FILE, logs)


def read_logs():
    """Return logs oldest-first, shaped like the old JSON entries."""
    if use_postgres():
        def action(conn):
            rows = conn.execute(
                "SELECT created_at, algorithm_used, page_requested, "
                "operation, status, evicted_page, dirty_writeback, "
                "current_hit_ratio FROM memory_logs ORDER BY log_id"
            ).fetchall()
            return [
                {
                    "time": created.astimezone().isoformat(timespec="seconds"),
                    "algorithm": algorithm,
                    "page_requested": page,
                    "operation": operation,
                    "status": result,
                    "evicted_page": evicted,
                    "dirty_writeback": writeback,
                    "hit_ratio": float(ratio)
                }
                for (created, algorithm, page, operation, result,
                     evicted, writeback, ratio) in rows
            ]
        return _run(action)

    return _read_json(LOG_FILE, [])


def clear_logs():
    if use_postgres():
        return _run(lambda conn: conn.execute(
            "TRUNCATE memory_logs RESTART IDENTITY"
        ))

    _write_json(LOG_FILE, [])


def now_iso():
    return datetime.now().isoformat(timespec="seconds")
