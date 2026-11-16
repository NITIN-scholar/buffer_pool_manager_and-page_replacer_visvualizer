
import db
from sqltext import build_sql


class BufferPool:
    def __init__(self, capacity=3):
        self.capacity = capacity
        self.frames = []
        self.clock = 0
        self.clock_hand = 0
        self.hits = 0
        self.requests = 0
        self.disk = db.load_disk()

    def reset(self, clear_logs=True):
        self.frames = []
        self.clock = 0
        self.clock_hand = 0
        self.hits = 0
        self.requests = 0
        self.disk = db.load_disk()

        if clear_logs:
            db.clear_logs()

    def status(self):
        return {
            "capacity": self.capacity,
            "hits": self.hits,
            "faults": self.requests - self.hits,
            "requests": self.requests,
            "hit_ratio": round(self.hits / self.requests, 4)
            if self.requests else 0,
            "frames": self.frames
        }

    def choose_victim(self, algorithm):
        if algorithm == "FIFO":
            return min(self.frames, key=lambda f: f["loaded_at"])

        if algorithm == "LRU":
            return min(self.frames, key=lambda f: f["last_used_at"])

        if algorithm == "LFU":
            return min(
                self.frames,
                key=lambda f: (f["frequency"], f["loaded_at"])
            )

        if algorithm == "CLOCK":
            while True:
                frame = self.frames[self.clock_hand]

                if not frame["reference_bit"]:
                    self.clock_hand = (
                        self.clock_hand + 1
                    ) % self.capacity
                    return frame

                frame["reference_bit"] = False
                self.clock_hand = (
                    self.clock_hand + 1
                ) % self.capacity

        raise ValueError("Invalid replacement algorithm.")

    def request_page(
        self,
        page_id,
        algorithm="LRU",
        operation="READ",
        data=None
    ):
        if isinstance(page_id, bool) or not isinstance(page_id, int):
            raise ValueError("page_id must be an integer.")

        algorithm = algorithm.upper()
        operation = operation.upper()

        if algorithm not in ("FIFO", "LRU", "LFU", "CLOCK"):
            raise ValueError("Algorithm must be FIFO, LRU, LFU, or CLOCK.")

        if operation not in ("READ", "WRITE"):
            raise ValueError("Operation must be READ or WRITE.")

        if operation == "WRITE" and data is None:
            raise ValueError("Provide data for a WRITE request.")

        page_key = str(page_id)

        if page_key not in self.disk:
            raise ValueError(f"Page {page_id} does not exist on disk.")

        frame = next(
            (f for f in self.frames if f["page_id"] == page_id),
            None
        )

        # A hit never touches the database. A fault runs the SELECT that
        # is shown in the live query box.
        fetched_data = None

        if frame is None:
            fetched_data = db.read_page(page_id)

            if fetched_data is None:
                raise ValueError(f"Page {page_id} does not exist on disk.")

            self.disk[page_key] = fetched_data

        self.clock += 1
        self.requests += 1

        result_status = "HIT" if frame else "FAULT"
        evicted_page = None
        dirty_writeback = False
        writeback_data = None

        if frame is None:
            if len(self.frames) < self.capacity:
                frame = {
                    "frame_id": len(self.frames) + 1,
                    "page_id": None,
                    "page_data": None,
                    "is_dirty": False,
                    "loaded_at": None,
                    "last_used_at": None,
                    "frequency": 0,
                    "reference_bit": False
                }
                self.frames.append(frame)
            else:
                frame = self.choose_victim(algorithm)
                evicted_page = frame["page_id"]

                if frame["is_dirty"]:
                    writeback_data = frame["page_data"]
                    db.write_page(frame["page_id"], writeback_data)
                    self.disk[str(frame["page_id"])] = writeback_data
                    dirty_writeback = True

            frame.update({
                "page_id": page_id,
                "page_data": fetched_data,
                "is_dirty": False,
                "loaded_at": self.clock,
                "last_used_at": self.clock,
                "frequency": 1,
                "reference_bit": True
            })
        else:
            self.hits += 1
            frame["last_used_at"] = self.clock
            frame["frequency"] += 1
            frame["reference_bit"] = True

        if operation == "WRITE":
            frame["page_data"] = str(data)
            frame["is_dirty"] = True

        log = {
            "time": db.now_iso(),
            "algorithm": algorithm,
            "page_requested": page_id,
            "operation": operation,
            "status": result_status,
            "evicted_page": evicted_page,
            "dirty_writeback": dirty_writeback,
            "hit_ratio": round(self.hits / self.requests, 4)
        }

        db.append_log(log)

        return {
            "result": log,
            "sql": build_sql(
                page_id,
                result_status,
                frame["frame_id"],
                operation,
                writeback_page=evicted_page if dirty_writeback else None,
                writeback_data=writeback_data
            ),
            "status": self.status()
        }
