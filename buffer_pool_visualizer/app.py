
from flask import Flask, request, jsonify, render_template
import db
from buffer_pool import BufferPool
from batch_simulator import parse_requests, compare_algorithms

app = Flask(__name__)


@app.errorhandler(db.DatabaseError)
def database_error(error):
    return jsonify({"error": str(error)}), 503

# Existing single-request buffer pool: 3 memory frames.
pool = BufferPool(capacity=3)


# --------------------------------------------------
# HOME PAGE: FRONTEND
# --------------------------------------------------
@app.get("/")
def home():
    return render_template("index.html")


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------
@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "disk_pages": len(pool.disk),
        "max_page_id": max((int(key) for key in pool.disk), default=0),
        "storage": db.status()
    })


# --------------------------------------------------
# GET CURRENT BUFFER POOL STATUS
# --------------------------------------------------
@app.get("/status")
def get_status():
    return jsonify(pool.status())


# --------------------------------------------------
# REQUEST A PAGE: READ OR WRITE
# --------------------------------------------------
@app.post("/request")
def request_page():
    body = request.get_json(silent=True) or {}

    try:
        result = pool.request_page(
            page_id=body.get("page_id"),
            algorithm=body.get("algorithm", "LRU"),
            operation=body.get("operation", "READ"),
            data=body.get("data")
        )

        return jsonify(result)

    except (ValueError, TypeError) as error:
        return jsonify({
            "error": str(error)
        }), 400


# --------------------------------------------------
# BATCH SIMULATION: COMPARE ALL FIVE ALGORITHMS
# --------------------------------------------------
@app.post("/batch")
def batch_request():
    body = request.get_json(silent=True) or {}
    batch_text = body.get("requests", "")

    if not isinstance(batch_text, str):
        return jsonify({
            "error": "requests must be a string."
        }), 400

    try:
        # Parse multiline input into individual page requests.
        requests = parse_requests(batch_text, pool.disk)

        # Simulate each algorithm with four frames.
        # Each simulation gets its own memory and disk copy.
        result = compare_algorithms(
            requests=requests,
            disk=pool.disk,
            capacity=4
        )

        return jsonify(result)

    except (ValueError, TypeError) as error:
        return jsonify({
            "error": str(error)
        }), 400


# --------------------------------------------------
# GET REQUEST HISTORY
# --------------------------------------------------
@app.get("/logs")
def get_logs():
    return jsonify(db.read_logs())


# --------------------------------------------------
# RESET BUFFER POOL AND OPTIONAL LOGS
# --------------------------------------------------
@app.post("/reset")
def reset():
    body = request.get_json(silent=True) or {}
    clear_logs = body.get("clear_logs", True)

    if not isinstance(clear_logs, bool):
        return jsonify({
            "error": "clear_logs must be a boolean"
        }), 400

    pool.reset(clear_logs=clear_logs)

    return jsonify({
        "message": "Buffer pool reset successfully",
        "status": pool.status()
    })


# --------------------------------------------------
# START FLASK SERVER
# --------------------------------------------------
if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )
