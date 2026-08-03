"""Surveillance mémoire cluster — monitoring centralisé + alerting (V1 lecture seule).

Scope V1 : aucun blocage automatique — snapshot, seuils, alertes structurées.
Intégration :
- Orchestrateur LangGraph : assert_bc250_cpu_idle() avant inférence Générateur (M3)
- Relay évaluation : reserve_m2_gpu_for() avant chargement Judge/Advocate (M2)
- /health/memory : snapshot exposé par l'API

Sources de données :
- M1 (Master) : Qdrant (approximation RAM ~200 B/point), Ollama /api/ps
- M2 (GPU Worker) : nvidia-smi via SSH (RTX 4000), Ollama /api/ps
- M3 (BC-250) : free -b + /proc/loadavg via SSH (unified GDDR6, règle d'or CPU)
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from src.core.settings import get_settings
from src.services.ollama import OllamaClient, OllamaClientPool
from src.services.ssh_client import SSHClient, SSHClientError
from src.services.ssh_client_protocol import SSHClientProtocol
from src.services.vector import VectorService

logger = logging.getLogger(__name__)

_BYTES_PER_POINT_QDRANT = 200  # approximation RAM Qdrant par point indexé


class MemoryManagerError(Exception):
    """Erreur générique MemoryManager."""


@dataclass(frozen=True)
class Alert:
    """Alerte mémoire unique."""

    level: Literal["warning", "critical"]
    machine: Literal["m1", "m2", "m3"]
    metric: str
    current: float
    threshold: float
    message: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class MachineMemoryState:
    """État mémoire d'une machine."""

    machine: Literal["m1", "m2", "m3"]
    timestamp: datetime

    # M1 (Master)
    qdrant_ram_mb: int | None = None
    qdrant_points_count: int | None = None
    embedding_cpu_percent: float | None = None
    loaded_models: list[str] = field(default_factory=list)

    # M2 (GPU Worker RTX 4000)
    rtx4000_vram_mb: int | None = None
    judge_vram_mb: int | None = None
    advocate_vram_mb: int | None = None
    reranker_vram_mb: int | None = None

    # M3 (BC-250)
    bc250_unified_mb: int | None = None
    bc250_unified_percent: float | None = None
    bc250_cpu_load: float | None = None  # /proc/loadavg[0]


@dataclass
class ClusterMemoryState:
    """Vue consolidée du cluster."""

    m1: MachineMemoryState
    m2: MachineMemoryState
    m3: MachineMemoryState
    timestamp: datetime
    alerts: list[Alert] = field(default_factory=list)


class MemoryManager:
    """Surveillance centralisée de la mémoire du cluster (M1/M2/M3)."""

    def __init__(
        self,
        ollama_pool: OllamaClientPool | None = None,
        vector_service: VectorService | None = None,
        ssh_m2: SSHClientProtocol | None = None,
        ssh_m3: SSHClientProtocol | None = None,
    ) -> None:
        self._settings = get_settings()
        self.ollama_pool = ollama_pool or OllamaClientPool()
        self.vector_service = vector_service
        self.ssh_m2 = ssh_m2 or self._create_ssh_client(
            self._settings.m2_ssh_host,
            self._settings.m2_ssh_user,
            self._settings.m2_ssh_key_path,
            self._settings.m2_ssh_port,
        )
        self.ssh_m3 = ssh_m3 or self._create_ssh_client(
            self._settings.m3_ssh_host,
            self._settings.m3_ssh_user,
            self._settings.m3_ssh_key_path,
            self._settings.m3_ssh_port,
        )

    @staticmethod
    def _create_ssh_client(
        host: str,
        user: str,
        key_path: Path | None,
        port: int,
    ) -> SSHClient:
        return SSHClient(
            host=host,
            user=user,
            key_path=key_path,
            port=port,
        )

    async def close(self) -> None:
        """Ferme les connexions SSH (les pools Ollama/Qdrant sont gérés ailleurs)."""
        await asyncio.gather(self.ssh_m2.close(), self.ssh_m3.close(), return_exceptions=True)

    async def __aenter__(self) -> MemoryManager:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # ─────────────────────────────────────────────────────────────
    # Snapshots par machine
    # ─────────────────────────────────────────────────────────────

    async def snapshot_m1(self) -> MachineMemoryState:
        """M1 (Master) : RAM Qdrant (approx points) + modèles chargés."""
        state = MachineMemoryState(machine="m1", timestamp=datetime.now())

        if self.vector_service is not None:
            try:
                stats = await self.vector_service.get_collection_stats()
                count = stats["points_count"]
                state.qdrant_points_count = count
                state.qdrant_ram_mb = count * _BYTES_PER_POINT_QDRANT // (1024 * 1024)
            except Exception as e:
                logger.warning("Qdrant stats M1 indisponibles: %s", e)
        else:
            logger.debug("VectorService non injecté — Qdrant RAM ignoré (M1)")

        state.loaded_models = await self._list_loaded(self.ollama_pool.m1)
        return state

    async def snapshot_m2(self) -> MachineMemoryState:
        """M2 (GPU Worker) : VRAM RTX 4000 (nvidia-smi) + VRAM par modèle."""
        state = MachineMemoryState(machine="m2", timestamp=datetime.now())

        try:
            output = await self.ssh_m2.execute(
                "nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits"
            )
            state.rtx4000_vram_mb = int(output.splitlines()[0].strip())
        except (SSHClientError, ValueError, IndexError) as e:
            logger.warning("nvidia-smi M2 indisponible: %s", e)

        state.judge_vram_mb = await self._vram_for(
            self.ollama_pool.m2, self._settings.judge_model
        )
        state.advocate_vram_mb = await self._vram_for(
            self.ollama_pool.m2, self._settings.advocate_model
        )
        state.reranker_vram_mb = await self._vram_for(
            self.ollama_pool.m2, self._settings.reranker_model
        )
        state.loaded_models = await self._list_loaded(self.ollama_pool.m2)
        return state

    async def snapshot_m3(self) -> MachineMemoryState:
        """M3 (BC-250) : unified GDDR6 (free -b) + CPU load (règle d'or)."""
        state = MachineMemoryState(machine="m3", timestamp=datetime.now())

        try:
            mem_output = await self.ssh_m3.execute("free -b | grep -E '^Mem'")
            parts = mem_output.split()
            total_bytes = int(parts[1])
            used_bytes = int(parts[2])
            state.bc250_unified_mb = used_bytes // (1024 * 1024)
            state.bc250_unified_percent = (
                (used_bytes / total_bytes) * 100.0 if total_bytes else None
            )
        except (SSHClientError, ValueError, IndexError) as e:
            logger.warning("free -b M3 indisponible: %s", e)

        try:
            load_output = await self.ssh_m3.execute("cat /proc/loadavg")
            state.bc250_cpu_load = float(load_output.split()[0])
        except (SSHClientError, ValueError, IndexError) as e:
            logger.warning("/proc/loadavg M3 indisponible: %s", e)

        state.loaded_models = await self._list_loaded(self.ollama_pool.m3)
        return state

    # ─────────────────────────────────────────────────────────────
    # Snapshot global cluster
    # ─────────────────────────────────────────────────────────────

    async def cluster_snapshot(self) -> ClusterMemoryState:
        """Snapshot complet : M1/M2/M3 en parallèle + vérification des seuils."""
        m1, m2, m3 = await asyncio.gather(
            self.snapshot_m1(), self.snapshot_m2(), self.snapshot_m3()
        )
        state = ClusterMemoryState(m1=m1, m2=m2, m3=m3, timestamp=datetime.now())
        state.alerts = await self.check_thresholds(state)
        return state

    # ─────────────────────────────────────────────────────────────
    # Garde-fous
    # ─────────────────────────────────────────────────────────────

    async def assert_bc250_cpu_idle(
        self, max_load: float | None = None, timeout_sec: int | None = None
    ) -> bool:
        """Règle d'or BC-250 : CPU M3 idle avant inférence Générateur.

        Retourne True si charge CPU < seuil, False sinon (log warning).
        Reessaie toutes les 2 s jusqu'au timeout.
        """
        max_load = max_load if max_load is not None else self._settings.m3_bc250_cpu_load_threshold
        timeout = (
            timeout_sec
            if timeout_sec is not None
            else self._settings.m3_bc250_cpu_idle_timeout_seconds
        )

        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            snapshot = await self.snapshot_m3()
            if snapshot.bc250_cpu_load is None:
                logger.error("BC-250 CPU load inrécupérable — garde-fou refusé")
                return False
            if snapshot.bc250_cpu_load < max_load:
                logger.info("BC-250 CPU idle ✓ (load %.2f)", snapshot.bc250_cpu_load)
                return True

            if asyncio.get_running_loop().time() >= deadline:
                logger.warning(
                    "BC-250 CPU NOT idle après %ss: load=%.2f > %.2f",
                    timeout,
                    snapshot.bc250_cpu_load,
                    max_load,
                )
                return False
            await asyncio.sleep(2)

    async def reserve_m2_gpu_for(
        self, stage: Literal["rerank", "judge", "advocate"]
    ) -> bool:
        """Garantit la place suffisante sur RTX 4000 pour charger un modèle 8B.

        Seuil : total VRAM - utilisé >= réserve configurée (m2_rtx4000_vram_reserve_mb).
        Retourne True si place dispo, False sinon (log warning).
        """
        snapshot = await self.snapshot_m2()
        if snapshot.rtx4000_vram_mb is None:
            logger.error("M2 VRAM inrécupérable — réserve refusée")
            return False

        total = self._settings.m2_rtx4000_vram_total_mb
        required = self._settings.m2_rtx4000_vram_reserve_mb
        available = total - snapshot.rtx4000_vram_mb

        if available < required:
            logger.warning(
                "M2 GPU reserve FAILED for %s: need %d MB, available %d MB (used %d/%d)",
                stage,
                required,
                available,
                snapshot.rtx4000_vram_mb,
                total,
            )
            return False

        logger.info(
            "M2 GPU reserved for %s: %d MB available (%d/%d used)",
            stage,
            available,
            snapshot.rtx4000_vram_mb,
            total,
        )
        return True

    # ─────────────────────────────────────────────────────────────
    # Alerting & seuils
    # ─────────────────────────────────────────────────────────────

    async def check_thresholds(
        self, state: ClusterMemoryState | None = None
    ) -> list[Alert]:
        """Parcourt tous les seuils configurés, retourne les alertes actives."""
        if state is None:
            state = await self.cluster_snapshot()

        alerts: list[Alert] = []

        # M1 — Qdrant
        if (
            state.m1.qdrant_ram_mb is not None
            and state.m1.qdrant_ram_mb > self._settings.m1_qdrant_ram_threshold_mb
        ):
            alerts.append(
                self._make_alert(
                    "warning", "m1", "qdrant_ram_mb",
                    state.m1.qdrant_ram_mb, self._settings.m1_qdrant_ram_threshold_mb,
                    f"Qdrant RAM high: {state.m1.qdrant_ram_mb} MB",
                )
            )

        # M2 — RTX 4000
        if (
            state.m2.rtx4000_vram_mb is not None
            and state.m2.rtx4000_vram_mb > self._settings.m2_rtx4000_vram_threshold_mb
        ):
            alerts.append(
                self._make_alert(
                    "critical", "m2", "rtx4000_vram_mb",
                    state.m2.rtx4000_vram_mb, self._settings.m2_rtx4000_vram_threshold_mb,
                    f"RTX4000 VRAM at limit: {state.m2.rtx4000_vram_mb} MB (8 GB max)",
                )
            )

        # M3 — unified GDDR6
        if (
            state.m3.bc250_unified_mb is not None
            and state.m3.bc250_unified_mb > self._settings.m3_bc250_unified_threshold_mb
        ):
            alerts.append(
                self._make_alert(
                    "warning", "m3", "bc250_unified_mb",
                    state.m3.bc250_unified_mb, self._settings.m3_bc250_unified_threshold_mb,
                    f"BC-250 unified memory high: {state.m3.bc250_unified_mb} MB",
                )
            )

        # M3 — CPU load (règle d'or)
        if (
            state.m3.bc250_cpu_load is not None
            and state.m3.bc250_cpu_load > self._settings.m3_bc250_cpu_load_threshold
        ):
            alerts.append(
                self._make_alert(
                    "critical", "m3", "bc250_cpu_load",
                    state.m3.bc250_cpu_load, self._settings.m3_bc250_cpu_load_threshold,
                    f"BC-250 CPU NOT idle: load {state.m3.bc250_cpu_load:.2f}",
                )
            )

        if self._settings.memory_manager_log_alerts:
            for alert in alerts:
                log_fn = logger.critical if alert.level == "critical" else logger.warning
                log_fn("[MemoryAlert] %s/%s: %s", alert.machine, alert.metric, alert.message)

        return alerts

    def _make_alert(
        self,
        level: Literal["warning", "critical"],
        machine: Literal["m1", "m2", "m3"],
        metric: str,
        current: float,
        threshold: float,
        message: str,
    ) -> Alert:
        return Alert(
            level=level,
            machine=machine,
            metric=metric,
            current=current,
            threshold=threshold,
            message=message,
        )

    # ─────────────────────────────────────────────────────────────
    # Helpers privés
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    async def _list_loaded(client: OllamaClient) -> list[str]:
        """Noms des modèles chargés sur un nœud Ollama (/api/ps)."""
        try:
            models = await client.list_models()
        except Exception as e:
            logger.warning("Ollama /api/ps indisponible: %s", e)
            return []
        return [str(m.get("name", "")) for m in models]

    @staticmethod
    async def _vram_for(client: OllamaClient, model: str) -> int | None:
        """VRAM (MB) utilisée par un modèle précis via /api/ps (match par tag complet)."""
        try:
            models = await client.list_models()
        except Exception as e:
            logger.warning("Ollama /api/ps indisponible: %s", e)
            return None
        for m in models:
            if m.get("name") == model:
                size_vram = m.get("size_vram") or m.get("size") or 0
                return int(size_vram) // (1024 * 1024)
        return None
