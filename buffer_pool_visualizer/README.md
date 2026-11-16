# Buffer Pool Manager & Page Replacement Visualizer

Simulates a buffer pool with FIFO, LRU, LFU, CLOCK and OPTIMAL replacement,
dirty-page write-back, and a live 3-line, full-width box showing the SQL each page request
runs. Backend: Flask. Frontend: plain HTML/JS/CSS. Storage: PostgreSQL, with an
automatic fallback to JSON files.

## Quick start (no database needed)

Requires Python 3.10+.

    py -m venv .venv
    .\.venv\Scripts\Activate.ps1
    py -m pip install -r requirements.txt
    py app.py

Open http://127.0.0.1:5000. Without PostgreSQL the page shows
"Storage: JSON files" and everything still works.

## With PostgreSQL

1. Install PostgreSQL and make sure `psql` works (add its `bin` folder to PATH).
2. Create the database:

       psql -U postgres -c "CREATE DATABASE buffer_pool_db;"

3. Create the tables and 300 sample pages (either one; safe to re-run, and re-running
   adds pages 11-300 to a database that only had the original 10):

       psql -U postgres -d buffer_pool_db -f schema.sql
       py init_db.py          # no psql needed; reads DATABASE_URL

4. Copy `.env.example` to `.env` and put your password in `DATABASE_URL`.
5. Run `py app.py`. The page should say "Storage: PostgreSQL".

## Page range

The page ID field and the batch input accept every page on disk (1-300 by default).
The limit is read from the server, not hardcoded. To go higher, raise the second number in
`generate_series(11, 300)` in `schema.sql` and run it again (JSON mode: add keys to
`disk_storage.json`).

## What touches the database

- A page fault runs `SELECT page_data FROM disk_storage WHERE page_id = ...`.
- A dirty eviction runs `UPDATE disk_storage ...` before the SELECT.
- A hit runs no data query (the box shows a comment).
- Every request is logged to `memory_logs`.
- Batch comparison and playback only generate the SQL text. They never write
  to the real tables.

If PostgreSQL stops responding, requests return an error and `/health` shows
why; once it is back, the app reconnects on its own.

## Files

- `app.py` Flask routes
- `buffer_pool.py` interactive 3-frame buffer pool
- `batch_simulator.py` five-algorithm comparison and playback timeline
- `db.py` PostgreSQL / JSON storage layer
- `sqltext.py` builds the query-box text (lines kept to 32 characters)
- `schema.sql`, `init_db.py` database setup
- `templates/index.html` frontend
