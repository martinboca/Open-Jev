"""Background decision client: never blocks the game tick, never queues stale work.

The server serialises every request behind one lock, so a queue would only make
latency compound. Newest state wins; anything older is dropped unsent.
"""
import json
import os
import threading
import time
from http.client import HTTPConnection

# Only the two controls that measured as usable. throttle and jump are heuristics
# in bot.py: the model did not discriminate on either.
QUESTIONS = {
    "steer": {
        "type": "choice",
        "instructions": "Choose the steering input that turns the car toward the ball.",
        "criteria": {"left": "Steer left", "straight": "No steering input", "right": "Steer right"},
    },
    "boost": {"type": "noul", "instructions": "Should the car hold boost now?"},
}

BOOST_THRESHOLD = 0.35  # Measured: the model's boost signal never crosses 0.5.


class JevController:
    def __init__(self, host=None, port=None, questions=None, timeout=10):
        self.host = host or os.environ.get("JEV_HOST", "192.168.0.66")
        self.port = int(port or os.environ.get("JEV_PORT", 8791))
        self.timeout = timeout
        self.questions = questions or QUESTIONS
        self._lock = threading.Lock()
        self._pending = None
        self._decision = {"steer": "straight", "boost": False}
        self._stats = {"sent": 0, "dropped": 0, "errors": 0, "last_ms": 0.0, "age_ms": 0.0}
        self._decided_at = time.perf_counter()
        self._wake = threading.Event()
        self._stop = threading.Event()
        threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, state):
        """Called every game tick. Replaces any state not yet sent."""
        with self._lock:
            if self._pending is not None:
                self._stats["dropped"] += 1
            self._pending = state
        self._wake.set()

    def decision(self):
        """Called every game tick. Returns the newest answer plus its age."""
        with self._lock:
            d = dict(self._decision)
        d["age_ms"] = (time.perf_counter() - self._decided_at) * 1000
        return d

    @property
    def stats(self):
        with self._lock:
            return dict(self._stats)

    def close(self):
        self._stop.set()
        self._wake.set()

    def _worker(self):
        connection = None
        while not self._stop.is_set():
            self._wake.wait(0.5)
            self._wake.clear()
            with self._lock:
                state, self._pending = self._pending, None
            if state is None:
                continue
            try:
                if connection is None:
                    connection = HTTPConnection(self.host, self.port, timeout=self.timeout)
                started = time.perf_counter()
                body = json.dumps({"state": state, "questions": self.questions}).encode()
                connection.request("POST", "/v1/systemone", body,
                                   {"Content-Type": "application/json"})
                answers = json.loads(connection.getresponse().read())["answers"]
                elapsed = (time.perf_counter() - started) * 1000
                decision = {"steer": answers["steer"]["choice"],
                            "boost": answers["boost"]["noul"] > BOOST_THRESHOLD}
                with self._lock:
                    self._decision = decision
                    self._stats["sent"] += 1
                    self._stats["last_ms"] = elapsed
                self._decided_at = time.perf_counter()
            except Exception:
                # A dropped keep-alive is normal; rebuild it and keep the last decision.
                try:
                    connection.close()
                except Exception:
                    pass
                connection = None
                with self._lock:
                    self._stats["errors"] += 1
        if connection is not None:
            connection.close()
