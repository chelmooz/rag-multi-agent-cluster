"""Agrégation monitoring pour le dashboard CTOS (chat + panneau M1/M2/M3/Cluster).

Sources :
- M1/M2/M3 : MemoryManager (snapshot via SSH + Ollama /api/ps + Qdrant)
- M3 : Glances web API (CPU/RAM/temp — pas de GPU NVIDIA, BC-250 = Vulkan/RADV)
- Cluster : santé Ollama x3, Qdrant, Postgres, Redis, NFS relay (age)

Note : le BC-250 ne supporte ni ROCm ni nvidia-smi. Glances n'expose pas de
stats GPU AMD dédiées — la mémoire unifiée vient du `free -b` SSH
(MemoryManager) et le CPU load du /proc/loadavg.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from src.core.settings import get_settings
from src.services.memory_manager import MachineMemoryState, MemoryManager
from src.services.ollama import OllamaClientPool

logger = logging.getLogger(__name__)

_TIMEOUT = 3.0


@dataclass
class MachineMetric:
    """Métrique unique pour une carte monitoring."""

    label: str
    value: str
    status: str = "ok"  # ok | warn | crit | n/a
    raw: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value,
            "status": self.status,
        }


@dataclass
class MachineCard:
    """Carte monitoring d'une machine (M1/M2/M3/Cluster)."""

    machine: str
    title: str
    status: str = "ok"
    metrics: list[MachineMetric] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "machine": self.machine,
            "title": self.title,
            "status": self.status,
            "metrics": [m.to_dict() for m in self.metrics],
            "timestamp": self.timestamp.isoformat(),
        }


def _status(ok: bool | None) -> str:
    if ok is None:
        return "n/a"
    return "ok" if ok else "crit"


class MonitoringService:
    """Agrège l'état du cluster pour le dashboard (poll JS 10s)."""

    def __init__(
        self,
        ollama_pool: OllamaClientPool | None = None,
        memory_manager: MemoryManager | None = None,
    ) -> None:
        self._settings = get_settings()
        self.ollama_pool = ollama_pool or OllamaClientPool()
        self._memory_manager = memory_manager

    async def close(self) -> None:
        if self._memory_manager is not None:
            await self._memory_manager.close()

    # ─────────────────────────────────────────────
    # API publique
    # ─────────────────────────────────────────────

    async def summary(self) -> dict[str, Any]:
        """Vue JSON agrégée : 4 cartes + alerts + timestamp.

        En mode prédéploiement (MONITORING_OFFLINE=true), retourne
        immédiatement des cartes n/a sans aucun appel réseau (SSH/Ollama/Qdrant).
        """
        if self._settings.monitoring_offline:
            return self._summary_offline()

        mm = self._get_memory_manager()
        try:
            snapshot = await mm.cluster_snapshot()
        except Exception as e:
            logger.warning("MemoryManager snapshot échoué: %s", e)
            snapshot = None

        cards = {
            "m1": self._card_m1(snapshot.m1 if snapshot else None),
            "m2": self._card_m2(snapshot.m2 if snapshot else None),
            "m3": self._card_m3(snapshot.m3 if snapshot else None),
        }
        cluster_card = await self._card_cluster()

        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "cards": {k: v.to_dict() for k, v in cards.items()},
            "cluster": cluster_card.to_dict(),
            "alerts": self._serialize_alerts(snapshot.alerts if snapshot else []),
        }

    def _summary_offline(self) -> dict[str, Any]:
        """Prédéploiement : aucune machine installée, cartes n/a sans réseau."""
        cards: dict[str, MachineCard] = {}
        for key, machine, title in (
            ("m1", "M1 MASTER", "M1 MASTER · LXC 100-101"),
            ("m2", "M2 GPU", "M2 GPU WORKER · RTX 4000"),
            ("m3", "M3 BC-250", "M3 BC-250 · Vulkan"),
        ):
            card = MachineCard(machine=machine, title=title, status="n/a")
            card.metrics.append(MachineMetric("STATE", "prédéploiement", "n/a"))
            cards[key] = card
        cluster = MachineCard(
            machine="cluster", title="CLUSTER · SANTÉ", status="n/a"
        )
        cluster.metrics.append(MachineMetric("SYSTÈME", "non déployé", "n/a"))
        return {
            "status": "degraded",
            "offline": True,
            "timestamp": datetime.now().isoformat(),
            "cards": {k: v.to_dict() for k, v in cards.items()},
            "cluster": cluster.to_dict(),
            "alerts": [
                {
                    "level": "warning",
                    "machine": "cluster",
                    "metric": "deployment",
                    "message": "prédéploiement — machines non installées",
                }
            ],
        }

    # ─────────────────────────────────────────────
    # Cartes par machine
    # ─────────────────────────────────────────────

    def _card_m1(self, state: MachineMemoryState | None) -> MachineCard:
        card = MachineCard(machine="m1", title="M1 MASTER · LXC 100-101")
        if state is None:
            card.status = "crit"
            card.metrics.append(MachineMetric("STATE", "indisponible", "crit"))
            return card

        qdrant = state.qdrant_ram_mb
        card.metrics.append(
            MachineMetric(
                "QDRANT RAM",
                self._fmt_mb(qdrant),
                "warn" if qdrant and qdrant > self._settings.m1_qdrant_ram_threshold_mb else "ok",
                raw=float(qdrant) if qdrant else None,
            )
        )
        card.metrics.append(
            MachineMetric(
                "QDRANT POINTS",
                f"{state.qdrant_points_count:,}" if state.qdrant_points_count else "n/a",
                "ok" if state.qdrant_points_count else "n/a",
            )
        )
        card.metrics.append(
            MachineMetric("MODELS", ", ".join(state.loaded_models) if state.loaded_models else "—")
        )
        card.status = "ok"
        return card

    def _card_m2(self, state: MachineMemoryState | None) -> MachineCard:
        card = MachineCard(machine="m2", title="M2 GPU WORKER · RTX 4000")
        if state is None:
            card.status = "crit"
            card.metrics.append(MachineMetric("STATE", "indisponible", "crit"))
            return card

        vram = state.rtx4000_vram_mb
        total = self._settings.m2_rtx4000_vram_total_mb
        card.metrics.append(
            MachineMetric(
                "VRAM",
                f"{self._fmt_mb(vram)} / {total // 1024} GB",
                "crit" if vram and vram > self._settings.m2_rtx4000_vram_threshold_mb else "ok",
                raw=float(vram) if vram else None,
            )
        )
        for label, mb in (
            ("JUGE", state.judge_vram_mb),
            ("AVOCAT", state.advocate_vram_mb),
            ("RERANK", state.reranker_vram_mb),
        ):
            card.metrics.append(MachineMetric(label, self._fmt_mb(mb), "ok" if mb else "n/a"))
        card.metrics.append(
            MachineMetric("MODELS", ", ".join(state.loaded_models) if state.loaded_models else "—")
        )
        card.status = "ok"
        return card

    def _card_m3(self, state: MachineMemoryState | None) -> MachineCard:
        card = MachineCard(machine="m3", title="M3 BC-250 · Vulkan")
        if state is None:
            card.status = "crit"
            card.metrics.append(MachineMetric("STATE", "indisponible", "crit"))
            return card

        mem = state.bc250_unified_mb
        card.metrics.append(
            MachineMetric(
                "UNIFIED",
                self._fmt_mb(mem),
                "warn" if mem and mem > self._settings.m3_bc250_unified_threshold_mb else "ok",
                raw=float(mem) if mem else None,
            )
        )
        load = state.bc250_cpu_load
        card.metrics.append(
            MachineMetric(
                "CPU LOAD",
                f"{load:.2f}" if load is not None else "n/a",
                (
                    "crit"
                    if load is not None
                    and load > self._settings.m3_bc250_cpu_load_threshold
                    else "ok"
                ),
                raw=load,
            )
        )
        card.metrics.append(
            MachineMetric("MODELS", ", ".join(state.loaded_models) if state.loaded_models else "—")
        )
        card.status = "ok"
        return card

    async def _card_cluster(self) -> MachineCard:
        card = MachineCard(machine="cluster", title="CLUSTER · SANTÉ")
        checks = await self._cluster_checks()
        for label, ok in checks.items():
            card.metrics.append(MachineMetric(label.upper(), "●", _status(ok)))
        card.status = "ok" if all(v for v in checks.values()) else "warn"
        return card

    # ─────────────────────────────────────────────
    # Internes
    # ─────────────────────────────────────────────

    def _get_memory_manager(self) -> MemoryManager:
        if self._memory_manager is None:
            self._memory_manager = MemoryManager(
                ollama_pool=self.ollama_pool,
                vector_service=None,  # Qdrant check direct ci-dessous
            )
        return self._memory_manager

    async def _cluster_checks(self) -> dict[str, bool]:
        async def check(url: str) -> bool:
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
                    r = await c.get(url)
                    return r.status_code < 500
            except Exception:
                return False

        qdrant = check(f"{self._settings.qdrant_url}/healthz")
        ollama_m1 = check(f"{self._settings.ollama_m1_url}/api/tags")
        ollama_m2 = check(f"{self._settings.ollama_m2_url}/api/tags")
        ollama_m3 = check(f"{self._settings.ollama_m3_url}/api/tags")
        glances = check(f"{self._settings.glances_m3_url}/api/3/cpu")
        relay = self._check_relay()

        results = await asyncio.gather(qdrant, ollama_m1, ollama_m2, ollama_m3, glances, relay)
        return {
            "qdrant": bool(results[0]),
            "ollama m1": bool(results[1]),
            "ollama m2": bool(results[2]),
            "ollama m3": bool(results[3]),
            "glances": bool(results[4]),
            "relay": bool(results[5]),
        }

    async def _check_relay(self) -> bool:
        """relay.json présent et pas trop vieux (< RELAY_TTL_SECONDS*3)."""
        import os

        path = self._settings.nfs_relay_path
        try:
            if not os.path.isfile(path):
                return False
            mtime = os.path.getmtime(path)
            age_s = datetime.now().timestamp() - mtime
            return age_s < int(self._settings.relay_ttl_seconds) * 3
        except Exception:
            return False

    @staticmethod
    def _serialize_alerts(alerts: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "level": a.level,
                "machine": a.machine,
                "metric": a.metric,
                "current": a.current,
                "threshold": a.threshold,
                "message": a.message,
            }
            for a in alerts
        ]

    @staticmethod
    def _fmt_mb(mb: int | None) -> str:
        if mb is None:
            return "n/a"
        if mb >= 1024:
            return f"{mb / 1024:.1f} GB"
        return f"{mb} MB"
