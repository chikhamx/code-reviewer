import hashlib
import time


class MessageDedup:
    """In-memory message deduplication with time-based expiry.
    For production, replace with Redis-based implementation.
    """

    def __init__(self, ttl: int = 300):
        self.ttl = ttl
        self._cache: dict[str, float] = {}

    def is_duplicate(self, msg_id: str) -> bool:
        now = time.time()
        self._cleanup(now)
        if msg_id in self._cache:
            return True
        self._cache[msg_id] = now
        return False

    def _cleanup(self, now: float) -> None:
        expired = [k for k, ts in self._cache.items() if now - ts > self.ttl]
        for k in expired:
            del self._cache[k]

    @staticmethod
    def generate_dedup_key(raw: dict) -> str:
        """Generate a deduplication key from raw message content."""
        content = str(sorted(raw.items()))
        return hashlib.sha256(content.encode()).hexdigest()[:16]
