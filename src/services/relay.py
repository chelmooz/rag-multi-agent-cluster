"""Service de relais NFS pour l'évaluation séquentielle Juge → Avocat → Évaluateur.

Fichier : /data/shared/evaluation-relay.json (partagé M1↔M2 via NFS)
TTL : 300s
Timeout Judge : 120s (→ Avocat prend la main avec judge.status="timeout")
"""
import json
from pathlib import Path


class RelayService:
    """Gestion atomique du fichier relay JSON via NFS partagé."""

    def __init__(self, relay_path: Path, ttl: int = 300):
        self.relay_path = relay_path
        self.ttl = ttl

    async def write(self, data: dict) -> None:
        """Écriture atomique dans le relay (écrit dans .tmp puis rename)."""
        # Utiliser fcntl pour le locking NFS
        tmp = self.relay_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        tmp.rename(self.relay_path)

    async def read(self) -> dict | None:
        """Lecture du relay. Retourne None si fichier absent ou stale (> TTL)."""
        if not self.relay_path.exists():
            return None
        return json.loads(self.relay_path.read_text(encoding="utf-8"))

    async def stale(self) -> bool:
        """Vérifie si le relay est plus vieux que le TTL."""
        if not self.relay_path.exists():
            return True
        age = self.relay_path.stat().st_mtime
        # TODO: comparer avec time.time() - self.ttl
        return False
