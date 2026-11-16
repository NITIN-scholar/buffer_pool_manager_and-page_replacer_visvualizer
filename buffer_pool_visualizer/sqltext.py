"""Builds the SQL shown in the 32x3 live query box.

Every statement is a list of at most 3 lines, each at most 32 characters,
so the frontend box never has to wrap or scroll. An event can produce more
than one statement (a dirty eviction writes the old page back, then reads
the new one); the frontend shows them one after another.
"""

WIDTH = 32
LINES = 3


def _fit(lines):
    """Clamp a statement to the box: at most 3 lines of 32 characters."""
    clipped = []
    for line in lines[:LINES]:
        clipped.append(line if len(line) <= WIDTH else line[:WIDTH - 3] + "...")
    return clipped


def _quote(text, room):
    """Escape a value for SQL and shorten it to fit in `room` characters."""
    text = str(text).replace("'", "''")
    if len(text) > room:
        text = text[:max(room - 3, 0)] + "..."
    return text


def select_page(page_id):
    return _fit([
        "SELECT page_data",
        "FROM disk_storage",
        f"WHERE page_id = {page_id};",
    ])


def update_page(page_id, data):
    prefix = "SET page_data = '"
    room = WIDTH - len(prefix) - 1  # closing quote
    return _fit([
        "UPDATE disk_storage",
        prefix + _quote(data, room) + "'",
        f"WHERE page_id = {page_id};",
    ])


def hit_comment(page_id, frame_id, operation):
    second = "-- marked dirty, no disk I/O" if operation == "WRITE" \
        else "-- no disk access"
    return _fit([f"-- HIT: page {page_id} in frame {frame_id}", second])


def build_sql(page_id, result, frame_id, operation,
              writeback_page=None, writeback_data=None):
    """Return the ordered list of statements for one page request."""
    if result == "HIT":
        return [hit_comment(page_id, frame_id, operation)]

    statements = []
    if writeback_page is not None:
        statements.append(update_page(writeback_page, writeback_data))
    statements.append(select_page(page_id))
    return statements
