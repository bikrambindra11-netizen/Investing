"""In-memory store of live ticks, read by the browser stream endpoint."""
import threading
from datetime import datetime, timezone


class LiveStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ticks: dict[str, dict] = {}  # key -> {ltp, cp, ltt, seq}
        self._seq = 0
        self.state = "off"  # off | needs_keys | needs_login | connecting | connected | reconnecting | token_rejected
        self.message: str | None = None
        self.last_tick_at: datetime | None = None
        self.segment_status: dict[str, str] = {}

    @property
    def seq(self) -> int:
        return self._seq

    def set_status(self, state: str, message: str | None = None) -> None:
        self.state, self.message = state, message

    def update(self, ticks: dict[str, dict]) -> None:
        with self._lock:
            self._seq += 1
            for k, t in ticks.items():
                self._ticks[k] = {**t, "seq": self._seq}
            self.last_tick_at = datetime.now(timezone.utc)

    def since(self, seq: int) -> tuple[int, dict[str, dict]]:
        """Ticks changed after `seq`, plus the current seq to pass next time."""
        with self._lock:
            changed = {k: v for k, v in self._ticks.items() if v["seq"] > seq}
            return self._seq, changed

    def clear(self) -> None:
        with self._lock:
            self._ticks.clear()


live = LiveStore()
