"""Tests MemoryManager — mocks SSH/Ollama/Qdrant (aucune machine réelle requise)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.settings import get_settings
from src.services.memory_manager import MemoryManager
from src.services.ssh_client import SSHCommandError
from src.services.ssh_client_protocol import SSHClientProtocol


@pytest.fixture
async def memory_manager() -> MemoryManager:
    """Instance MemoryManager avec clients Ollama/Qdrant factices."""
    mm = MemoryManager(
        ollama_pool=AsyncMock(),  # type: ignore[arg-type]
        vector_service=AsyncMock(),  # type: ignore[arg-type]
    )
    yield mm
    await mm.close()


class TestSnapshots:
    async def test_snapshot_m2_vram(self, memory_manager: MemoryManager) -> None:
        """nvidia-smi parsé correctement → rtx4000_vram_mb."""
        memory_manager.ssh_m2.execute = AsyncMock(
            return_value="5000\n"  # nvidia-smi memory.used MB
        )
        memory_manager.ollama_pool.m2.list_models = AsyncMock(return_value=[])

        state = await memory_manager.snapshot_m2()
        assert state.rtx4000_vram_mb == 5000

    async def test_snapshot_m2_ssh_failure_graceful(self, memory_manager: MemoryManager) -> None:
        """SSH KO → état None, pas d'exception."""
        memory_manager.ssh_m2.execute = AsyncMock(
            side_effect=SSHCommandError("Commande SSH échouée (rc=255)")
        )
        memory_manager.ollama_pool.m2.list_models = AsyncMock(return_value=[])

        state = await memory_manager.snapshot_m2()
        assert state.rtx4000_vram_mb is None

    async def test_snapshot_m3_unified_and_load(self, memory_manager: MemoryManager) -> None:
        """free -b + /proc/loadavg parsés → unified_mb + cpu_load."""
        memory_manager.ssh_m3.execute = AsyncMock(
            side_effect=[
                "Mem:  17179869184  8589934592  8589934592  0  0  4294967296",  # free -b
                "0.35 0.28 0.21 1/256 999",  # /proc/loadavg
            ]
        )
        memory_manager.ollama_pool.m3.list_models = AsyncMock(return_value=[])

        state = await memory_manager.snapshot_m3()
        assert state.bc250_unified_mb == 8192  # 8589934592 // 1024 // 1024
        assert state.bc250_unified_percent == pytest.approx(50.0)
        assert state.bc250_cpu_load == pytest.approx(0.35)

    async def test_snapshot_m1_qdrant_approx(self, memory_manager: MemoryManager) -> None:
        """RAM Qdrant approx = points_count * 200 B."""
        memory_manager.ollama_pool.m1.list_models = AsyncMock(return_value=[])
        memory_manager.vector_service.get_collection_stats = AsyncMock(
            return_value={"points_count": 100_000}
        )

        state = await memory_manager.snapshot_m1()
        assert state.qdrant_points_count == 100_000
        assert state.qdrant_ram_mb == 100_000 * 200 // (1024 * 1024)  # ~19 MB

    async def test_snapshot_m1_without_vector_service(self, memory_manager: MemoryManager) -> None:
        """Pas de VectorService injecté → pas d'exception."""
        memory_manager.vector_service = None
        memory_manager.ollama_pool.m1.list_models = AsyncMock(return_value=[])

        state = await memory_manager.snapshot_m1()
        assert state.qdrant_ram_mb is None

    async def test_vram_per_model_match(self, memory_manager: MemoryManager) -> None:
        """Match modèle par tag complet → VRAM du bon modèle."""
        s = get_settings()
        memory_manager.ollama_pool.m2.list_models = AsyncMock(
            return_value=[
                {"name": s.judge_model, "size_vram": 5_500 * 1024 * 1024},
                {"name": s.advocate_model, "size_vram": 4_900 * 1024 * 1024},
            ]
        )
        judge_mb = await MemoryManager._vram_for(memory_manager.ollama_pool.m2, s.judge_model)
        assert judge_mb == 5500


class TestGuards:
    async def test_assert_bc250_cpu_idle_ok(self, memory_manager: MemoryManager) -> None:
        """CPU load < seuil → True immédiatement."""
        memory_manager.ssh_m3.execute = AsyncMock(return_value="0.10 0.20 0.30 1/256 999")
        memory_manager.ollama_pool.m3.list_models = AsyncMock(return_value=[])

        assert await memory_manager.assert_bc250_cpu_idle() is True

    async def test_assert_bc250_cpu_idle_busy(self, memory_manager: MemoryManager) -> None:
        """CPU load > seuil et timeout dépassé → False."""
        memory_manager.ssh_m3.execute = AsyncMock(
            return_value="2.50 2.00 1.50 3/512 111"
        )
        memory_manager.ollama_pool.m3.list_models = AsyncMock(return_value=[])

        assert await memory_manager.assert_bc250_cpu_idle(max_load=0.5, timeout_sec=0) is False

    async def test_reserve_m2_gpu_enough_space(self, memory_manager: MemoryManager) -> None:
        """VRAM utilisée faible → réserve OK."""
        memory_manager.ssh_m2.execute = AsyncMock(return_value="1500")
        memory_manager.ollama_pool.m2.list_models = AsyncMock(return_value=[])

        assert await memory_manager.reserve_m2_gpu_for("judge") is True

    async def test_reserve_m2_gpu_not_enough_space(self, memory_manager: MemoryManager) -> None:
        """VRAM utilisée trop haute → réserve refusée."""
        memory_manager.ssh_m2.execute = AsyncMock(return_value="6000")
        memory_manager.ollama_pool.m2.list_models = AsyncMock(return_value=[])

        assert await memory_manager.reserve_m2_gpu_for("judge") is False


class TestAlerting:
    async def test_cluster_snapshot_collects_alerts(self, memory_manager: MemoryManager) -> None:
        """M2 VRAM au-dessus du seuil → alerte critical."""
        memory_manager.ssh_m2.execute = AsyncMock(return_value="7900")  # > 7680 seuil
        memory_manager.ssh_m3.execute = AsyncMock(
            side_effect=[
                "Mem:  17179869184  8589934592  8589934592  0  0  4294967296",
                "0.10 0.20 0.30 1/256 999",
            ]
        )
        for client in (memory_manager.ollama_pool.m1, memory_manager.ollama_pool.m2,
                       memory_manager.ollama_pool.m3):
            client.list_models = AsyncMock(return_value=[])
        memory_manager.vector_service.get_collection_stats = AsyncMock(
            return_value={"points_count": 0}
        )

        snapshot = await memory_manager.cluster_snapshot()
        assert snapshot.m2.rtx4000_vram_mb == 7900
        assert any(a.metric == "rtx4000_vram_mb" and a.level == "critical" for a in snapshot.alerts)

    async def test_no_alerts_when_healthy(self, memory_manager: MemoryManager) -> None:
        """Tout sous les seuils → aucune alerte."""
        memory_manager.ssh_m2.execute = AsyncMock(return_value="1500")
        memory_manager.ssh_m3.execute = AsyncMock(
            side_effect=[
                "Mem:  17179869184  4294967296  12884901888  0  0  2147483648",
                "0.10 0.20 0.30 1/256 999",
            ]
        )
        for client in (memory_manager.ollama_pool.m1, memory_manager.ollama_pool.m2,
                       memory_manager.ollama_pool.m3):
            client.list_models = AsyncMock(return_value=[])
        memory_manager.vector_service.get_collection_stats = AsyncMock(
            return_value={"points_count": 1000}
        )

        snapshot = await memory_manager.cluster_snapshot()
        assert snapshot.alerts == []


class TestRealSSHInjection:
    """Tests d'injection via constructeur avec spec=SSHClientProtocol (RED §5.6).

    Au lieu de patcher un attribut (``mm.ssh_m2.execute = ...``), on injecte
    un mock `spec=SSHClientProtocol` au constructeur — même contrainte de type
    que l'implémentation réelle. Évite la classe de régression R1 où un
    `MagicMock()` nu masquait une méthode disparue.
    """

    def _make_mocked_ssh(self) -> MagicMock:
        mock: SSHClientProtocol = MagicMock(spec=SSHClientProtocol)
        mock.execute = AsyncMock()
        mock.close = AsyncMock()
        return mock  # type: ignore[return-value]

    def _make_mm_with_mocked_ssh(self) -> MemoryManager:
        return MemoryManager(
            ollama_pool=AsyncMock(),  # type: ignore[arg-type]
            vector_service=AsyncMock(),  # type: ignore[arg-type]
            ssh_m2=self._make_mocked_ssh(),
            ssh_m3=self._make_mocked_ssh(),
        )

    async def test_ssh_injected_via_constructor(self) -> None:
        """Le mock spec=SSHClientProtocol est accepté par le constructeur."""
        mm = self._make_mm_with_mocked_ssh()
        assert isinstance(mm.ssh_m2, SSHClientProtocol)
        assert isinstance(mm.ssh_m3, SSHClientProtocol)

    async def test_snapshot_m2_with_injected_ssh(self) -> None:
        """nvidia-smi parsé via mock injecté (pas d'attribut patqué)."""
        mm = self._make_mm_with_mocked_ssh()
        mm.ssh_m2.execute = AsyncMock(return_value="3500\n")
        mm.ollama_pool.m2.list_models = AsyncMock(return_value=[])

        state = await mm.snapshot_m2()
        assert state.rtx4000_vram_mb == 3500

    async def test_close_calls_close_on_injected_ssh(self) -> None:
        """MemoryManager.close → ssh_m2.close + ssh_m3.close (mocks distincts)."""
        mm = self._make_mm_with_mocked_ssh()

        await mm.close()
        mm.ssh_m2.close.assert_awaited_once()
        mm.ssh_m3.close.assert_awaited_once()
