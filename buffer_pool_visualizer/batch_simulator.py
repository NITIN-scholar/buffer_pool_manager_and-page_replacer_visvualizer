
import re

from sqltext import build_sql

ALGORITHMS = ("FIFO", "LRU", "LFU", "CLOCK", "OPTIMAL")


def parse_requests(text, disk):
    """
    Accept either:
      Simple sequence: 1, 2, 3, 4, 1
      Detailed requests:
        1,READ
        3,WRITE,Updated page three
    """
    if not isinstance(text, str):
        raise ValueError("Requests must be entered as text.")

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if not lines:
        raise ValueError("Enter at least one valid page request.")

    # SIMPLE MODE:
    # If the entire input contains only numbers, commas, and whitespace,
    # interpret every number as a READ request.
    if re.fullmatch(r"[\d,\s]+", text):
        page_ids = [
            item
            for item in re.split(r"[\s,]+", text.strip())
            if item
        ]

        requests = []

        for page_text in page_ids:
            page_id = int(page_text)

            if str(page_id) not in disk:
                raise ValueError(
                    f"Page {page_id} is not on disk. "
                    "Enter a page ID available in the simulated disk."
                )

            requests.append({
                "page_id": page_id,
                "operation": "READ",
                "data": None
            })

        if not requests:
            raise ValueError("Enter at least one valid page request.")

        return requests

    # DETAILED MODE:
    # Each line follows PAGE_ID,OPERATION[,DATA].
    requests = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue

        parts = [part.strip() for part in line.split(",", 2)]

        if len(parts) < 2:
            raise ValueError(
                f"Line {line_number}: use PAGE_ID,OPERATION[,DATA], "
                "or enter page numbers separated by commas."
            )

        try:
            page_id = int(parts[0])
        except ValueError:
            raise ValueError(
                f"Line {line_number}: page ID must be an integer."
            )

        operation = parts[1].upper()
        data = parts[2] if len(parts) == 3 else None

        if str(page_id) not in disk:
            raise ValueError(
                f"Line {line_number}: page {page_id} is not on disk."
            )

        if operation not in ("READ", "WRITE"):
            raise ValueError(
                f"Line {line_number}: operation must be READ or WRITE."
            )

        if operation == "WRITE" and not data:
            raise ValueError(
                f"Line {line_number}: WRITE requires data."
            )

        requests.append({
            "page_id": page_id,
            "operation": operation,
            "data": data
        })

    if not requests:
        raise ValueError("Enter at least one valid page request.")

    return requests


def simulate(requests, original_disk, algorithm, capacity=4):
    """Run one algorithm using its own memory and disk copy."""
    if algorithm not in ALGORITHMS:
        raise ValueError("Unknown replacement algorithm.")

    if capacity < 1:
        raise ValueError("Frame capacity must be at least 1.")

    disk = dict(original_disk)
    frames = []
    clock_hand = 0
    hits = 0
    faults = 0
    evictions = 0
    writebacks = 0
    timeline = []

    for step, request in enumerate(requests):
        page_id = request["page_id"]
        operation = request["operation"]
        data = request["data"]

        frame = next(
            (f for f in frames if f["page_id"] == page_id),
            None
        )

        evicted_page = None
        dirty_writeback = False
        writeback_data = None

        if frame is not None:
            result = "HIT"
            hits += 1
            frame["last_used"] = step
            frame["frequency"] += 1
            frame["reference_bit"] = True

        else:
            result = "FAULT"
            faults += 1

            if len(frames) < capacity:
                frame = {
                    "frame_id": len(frames) + 1,
                    "page_id": page_id,
                    "data": disk[str(page_id)],
                    "dirty": False,
                    "loaded_at": step,
                    "last_used": step,
                    "frequency": 1,
                    "reference_bit": True
                }
                frames.append(frame)

            else:
                if algorithm == "FIFO":
                    victim = min(
                        frames,
                        key=lambda f: f["loaded_at"]
                    )

                elif algorithm == "LRU":
                    victim = min(
                        frames,
                        key=lambda f: f["last_used"]
                    )

                elif algorithm == "LFU":
                    victim = min(
                        frames,
                        key=lambda f: (
                            f["frequency"],
                            f["loaded_at"]
                        )
                    )

                elif algorithm == "CLOCK":
                    while True:
                        victim = frames[clock_hand]

                        if not victim["reference_bit"]:
                            break

                        victim["reference_bit"] = False
                        clock_hand = (clock_hand + 1) % capacity

                    clock_hand = (clock_hand + 1) % capacity

                else:
                    # OPTIMAL evicts the page whose next use is farthest
                    # in the future. Pages never used again are preferred.
                    future = requests[step + 1:]

                    def next_use(candidate):
                        for index, upcoming in enumerate(future):
                            if upcoming["page_id"] == candidate["page_id"]:
                                return index

                        return float("inf")

                    victim = max(frames, key=next_use)

                evicted_page = victim["page_id"]
                evictions += 1

                if victim["dirty"]:
                    disk[str(victim["page_id"])] = victim["data"]
                    writeback_data = victim["data"]
                    dirty_writeback = True
                    writebacks += 1

                frame = victim

                frame.update({
                    "page_id": page_id,
                    "data": disk[str(page_id)],
                    "dirty": False,
                    "loaded_at": step,
                    "last_used": step,
                    "frequency": 1,
                    "reference_bit": True
                })

        if operation == "WRITE":
            frame["data"] = data
            frame["dirty"] = True

        timeline.append({
            "step": step + 1,
            "page_id": page_id,
            "operation": operation,
            "result": result,
            "evicted_page": evicted_page,
            "dirty_writeback": dirty_writeback,
            # SQL text only: a batch run never writes to the real database.
            "sql": build_sql(
                page_id,
                result,
                frame["frame_id"],
                operation,
                writeback_page=evicted_page if dirty_writeback else None,
                writeback_data=writeback_data
            ),
            "frames": [
                {
                    "frame_id": f["frame_id"],
                    "page_id": f["page_id"],
                    "data": f["data"],
                    "dirty": f["dirty"],
                    "frequency": f["frequency"]
                }
                for f in frames
            ]
        })

    total = len(requests)

    return {
        "algorithm": algorithm,
        "capacity": capacity,
        "requests": total,
        "hits": hits,
        "faults": faults,
        "hit_ratio": round(hits / total, 4),
        "evictions": evictions,
        "dirty_writebacks": writebacks,
        "timeline": timeline
    }


def compare_algorithms(requests, disk, capacity=4):
    """Compare all algorithms without sharing memory or disk changes."""
    results = [
        simulate(requests, disk, algorithm, capacity)
        for algorithm in ALGORITHMS
    ]

    best = min(
        results,
        key=lambda result: (
            result["faults"],
            result["dirty_writebacks"]
        )
    )

    return {
        "capacity": capacity,
        "results": results,
        "recommendation": {
            "algorithm": best["algorithm"],
            "faults": best["faults"],
            "dirty_writebacks": best["dirty_writebacks"],
            "explanation": (
                "Selected using the fewest page faults, then the fewest "
                "dirty-page write-backs. OPTIMAL is a theoretical benchmark "
                "because it requires knowledge of future requests."
            )
        }
    }
