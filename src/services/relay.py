"""Service de relais NFS pour l'évaluation séquentielle Juge → Avocat → Évaluateur."""
import json
import time
from pathlib import Path


class RelayService:
    def __init__(self, relay_path: Path, ttl: int = 300):
        self.relay_path = relay_path
        self.ttl = ttl

    async def write(self, data: dict) -> None:
        tmp = self.relay_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        tmp.rename(self.relay_path)

    async def read(self) -> dict | None:
        if not self.relay_path.exists():
            return None
        if await self.stale():
            return None
        return json.loads(self.relay_path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    async def stale(self) -> bool:
        if not self.relay_path.exists():
            return True
        mtime = self.relay_path.stat().st_mtime
        return time.time() - mtime > self.ttl
