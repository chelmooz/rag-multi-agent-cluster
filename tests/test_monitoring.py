"""Tests MonitoringService — mocks httpx/SSH/Ollama/Qdrant (aucun nœud réel)."""

import os
import tempfile
from collections.abc import Generator
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.settings import get_settings
from src.services.memory_manager import Alert, MachineMemoryState
from src.services.monitoring import (
    MachineCard,
    MachineMetric,
    MonitoringService,
    _status,
)


class TestMachineMetric:
    def test_default_status_ok(self) -> None:
        m = MachineMetric(label="RAM", value="16 GB")
        assert m.status == "ok"
        assert m.raw is None

    def test_to_dict_excludes_raw(self) -> None:
        m = MachineMetric(label="RAM", value="16 GB", status="warn", raw=16384.0)
        d = m.to_dict()
        assert d == {"label": "RAM", "value": "16 GB", "status": "warn"}
        assert "raw" not in d


class TestMachineCard:
    def test_to_dict_includes_timestamp(self) -> None:
        card = MachineCard(machine="m1", title="M1 MASTER", status="ok")
        card.metrics.append(MachineMetric("STATE", "ok"))
        d = card.to_dict()
        assert d["machine"] == "m1"
        assert d["title"] == "M1 MASTER"
        assert d["status"] == "ok"
        assert len(d["metrics"]) == 1
        assert "timestamp" in d

    def test_default_status_ok(self) -> None:
        card = MachineCard(machine="m2", title="M2 GPU")
        assert card.status == "ok"


class TestHelpers:
    def test_status_ok(self) -> None:
        assert _status(True) == "ok"

    def test_status_crit(self) -> None:
        assert _status(False) == "crit"

    def test_status_na(self) -> None:
        assert _status(None) == "n/a"

    def test_fmt_mb_none(self) -> None:
        assert MonitoringService._fmt_mb(None) == "n/a"

    def test_fmt_mb_small(self) -> None:
        assert MonitoringService._fmt_mb(512) == "512 MB"

    def test_fmt_mb_large(self) -> None:
        assert MonitoringService._fmt_mb(2048) == "2.0 GB"

    def test_fmt_mb_exact_gb(self) -> None:
        assert MonitoringService._fmt_mb(1024) == "1.0 GB"


class TestMonitoringServiceOffline:
    @pytest.fixture
    def service(self) -> Generator[MonitoringService, None, None]:
        """Service en mode offline (prédéploiement)."""
        svc = MonitoringService(
            ollama_pool=MagicMock(),
            memory_manager=None,
        )
        original = svc._settings.monitoring_offline
        svc._settings.monitoring_offline = True
        yield svc
        svc._settings.monitoring_offline = original

    async def test_summary_returns_offline_structure(self, service: MonitoringService) -> None:
        result = await service.summary()
        assert result["status"] == "degraded"
        assert result["offline"] is True
        assert "timestamp" in result
        assert set(result["cards"].keys()) == {"m1", "m2", "m3"}
        assert "cluster" in result
        assert len(result["alerts"]) == 1

    async def test_offline_card_has_state_metric(self, service: MonitoringService) -> None:
        result = await service.summary()
        for key in ("m1", "m2", "m3"):
            card = result["cards"][key]
            metrics_labels = [m["label"] for m in card["metrics"]]
            assert "STATE" in metrics_labels
            assert card["status"] == "n/a"

    async def test_offline_cluster_is_na(self, service: MonitoringService) -> None:
        result = await service.summary()
        assert result["cluster"]["status"] == "n/a"
        assert result["cluster"]["metrics"][0]["value"] == "non déployé"

    async def test_close_does_nothing_when_no_memory_manager(
        self, service: MonitoringService
    ) -> None:
        await service.close()


@pytest.fixture
def sample_m1_state() -> MachineMemoryState:
    return MachineMemoryState(
        machine="m1",
        timestamp=datetime.now(),
        qdrant_ram_mb=512,
        qdrant_points_count=10_000,
        loaded_models=["llama3.2:3b", "nomic-embed-text:v1.5"],
    )


@pytest.fixture
def sample_m2_state() -> MachineMemoryState:
    return MachineMemoryState(
        machine="m2",
        timestamp=datetime.now(),
        rtx4000_vram_mb=4096,
        judge_vram_mb=2048,
        advocate_vram_mb=1024,
        reranker_vram_mb=512,
        loaded_models=["llama3.2:3b", "mistral:7b"],
    )


@pytest.fixture
def sample_m3_state() -> MachineMemoryState:
    return MachineMemoryState(
        machine="m3",
        timestamp=datetime.now(),
        bc250_unified_mb=4096,
        bc250_cpu_load=0.45,
        loaded_models=["qwen2.5:7b"],
    )


class TestMonitoringCards:
    @pytest.fixture
    def service(self) -> MonitoringService:
        return MonitoringService(
            ollama_pool=MagicMock(),
            memory_manager=None,
        )

    # ── Card M1 ──────────────────────────────────────

    def test_card_m1_none_state(self, service: MonitoringService) -> None:
        card = service._card_m1(None)
        assert card.status == "crit"
        assert card.metrics[0].value == "indisponible"

    def test_card_m1_normal(
        self, service: MonitoringService, sample_m1_state: MachineMemoryState
    ) -> None:
        card = service._card_m1(sample_m1_state)
        assert card.status == "ok"
        labels = [m.label for m in card.metrics]
        assert "QDRANT RAM" in labels
        assert "QDRANT POINTS" in labels
        assert "MODELS" in labels
        qdrant_ram = next(m for m in card.metrics if m.label == "QDRANT RAM")
        assert "MB" in qdrant_ram.value
        points = next(m for m in card.metrics if m.label == "QDRANT POINTS")
        assert "10,000" in points.value

    def test_card_m1_qdrant_ram_warn(
        self, service: MonitoringService, sample_m1_state: MachineMemoryState
    ) -> None:
        sample_m1_state.qdrant_ram_mb = 30_000  # > seuil 28 GB
        card = service._card_m1(sample_m1_state)
        qdrant_ram = next(m for m in card.metrics if m.label == "QDRANT RAM")
        assert qdrant_ram.status == "warn"

    def test_card_m1_no_points(self, service: MonitoringService) -> None:
        state = MachineMemoryState(machine="m1", timestamp=datetime.now())
        card = service._card_m1(state)
        points = next(m for m in card.metrics if m.label == "QDRANT POINTS")
        assert points.value == "n/a"

    def test_card_m1_no_models(self, service: MonitoringService) -> None:
        state = MachineMemoryState(
            machine="m1",
            timestamp=datetime.now(),
            qdrant_ram_mb=100,
            qdrant_points_count=1,
        )
        card = service._card_m1(state)
        models = next(m for m in card.metrics if m.label == "MODELS")
        assert models.value == "—"

    # ── Card M2 ──────────────────────────────────────

    def test_card_m2_none_state(self, service: MonitoringService) -> None:
        card = service._card_m2(None)
        assert card.status == "crit"
        assert card.metrics[0].value == "indisponible"

    def test_card_m2_normal(
        self, service: MonitoringService, sample_m2_state: MachineMemoryState
    ) -> None:
        card = service._card_m2(sample_m2_state)
        assert card.status == "ok"
        labels = [m.label for m in card.metrics]
        assert "VRAM" in labels
        assert "JUGE" in labels
        assert "AVOCAT" in labels
        assert "RERANK" in labels
        assert "MODELS" in labels

    def test_card_m2_vram_format(
        self, service: MonitoringService, sample_m2_state: MachineMemoryState
    ) -> None:
        total_gb = get_settings().m2_rtx4000_vram_total_mb // 1024
        card = service._card_m2(sample_m2_state)
        vram = next(m for m in card.metrics if m.label == "VRAM")
        assert f"/ {total_gb} GB" in vram.value

    def test_card_m2_vram_crit(
        self, service: MonitoringService, sample_m2_state: MachineMemoryState
    ) -> None:
        sample_m2_state.rtx4000_vram_mb = 99999  # > threshold
        card = service._card_m2(sample_m2_state)
        vram = next(m for m in card.metrics if m.label == "VRAM")
        assert vram.status == "crit"

    def test_card_m2_models_joined(self, service: MonitoringService) -> None:
        state = MachineMemoryState(
            machine="m2",
            timestamp=datetime.now(),
            rtx4000_vram_mb=100,
            judge_vram_mb=100,
            advocate_vram_mb=100,
            reranker_vram_mb=100,
            loaded_models=["a", "b"],
        )
        card = service._card_m2(state)
        models = next(m for m in card.metrics if m.label == "MODELS")
        assert models.value == "a, b"

    # ── Card M3 ──────────────────────────────────────

    def test_card_m3_none_state(self, service: MonitoringService) -> None:
        card = service._card_m3(None)
        assert card.status == "crit"
        assert card.metrics[0].value == "indisponible"

    def test_card_m3_normal(
        self, service: MonitoringService, sample_m3_state: MachineMemoryState
    ) -> None:
        card = service._card_m3(sample_m3_state)
        assert card.status == "ok"
        labels = [m.label for m in card.metrics]
        assert "UNIFIED" in labels
        assert "CPU LOAD" in labels
        assert "MODELS" in labels

    def test_card_m3_unified_warn(
        self, service: MonitoringService, sample_m3_state: MachineMemoryState
    ) -> None:
        sample_m3_state.bc250_unified_mb = 99999
        card = service._card_m3(sample_m3_state)
        unified = next(m for m in card.metrics if m.label == "UNIFIED")
        assert unified.status == "warn"

    def test_card_m3_cpu_load_crit(
        self, service: MonitoringService, sample_m3_state: MachineMemoryState
    ) -> None:
        sample_m3_state.bc250_cpu_load = 99.9  # > threshold
        card = service._card_m3(sample_m3_state)
        cpu = next(m for m in card.metrics if m.label == "CPU LOAD")
        assert cpu.status == "crit"

    def test_card_m3_cpu_load_none(self, service: MonitoringService) -> None:
        state = MachineMemoryState(
            machine="m3",
            timestamp=datetime.now(),
            bc250_unified_mb=100,
            bc250_cpu_load=None,
        )
        card = service._card_m3(state)
        cpu = next(m for m in card.metrics if m.label == "CPU LOAD")
        assert cpu.value == "n/a"
        assert cpu.status == "ok"


class TestSerializers:
    def test_serialize_alerts_empty(self) -> None:
        assert MonitoringService._serialize_alerts([]) == []

    def test_serialize_alerts_multiple(self) -> None:
        alerts = [
            Alert(
                level="warning",
                machine="m2",
                metric="vram",
                current=8000.0,
                threshold=7000.0,
                message="VRAM élevée",
            ),
            Alert(
                level="critical",
                machine="m3",
                metric="cpu_load",
                current=90.0,
                threshold=80.0,
                message="CPU surchargé",
            ),
        ]
        serialized = MonitoringService._serialize_alerts(alerts)
        assert len(serialized) == 2
        assert serialized[0]["metric"] == "vram"
        assert serialized[0]["level"] == "warning"
        assert serialized[1]["metric"] == "cpu_load"
        assert serialized[1]["level"] == "critical"


class TestClusterChecks:
    @pytest.fixture
    def service(self) -> MonitoringService:
        return MonitoringService(
            ollama_pool=MagicMock(),
            memory_manager=None,
        )

    async def test_all_up(self, service: MonitoringService) -> None:
        with (
            patch("src.services.monitoring.httpx.AsyncClient") as mock_client,
            patch.object(service, "_check_relay", AsyncMock(return_value=True)),
        ):
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=MagicMock(status_code=200))
            mock_client.return_value.__aenter__.return_value = instance

            checks = await service._cluster_checks()
            assert all(checks.values())
            assert instance.get.call_count == 5

    async def test_one_down(self, service: MonitoringService) -> None:
        m1_url = str(get_settings().ollama_m1_url)

        with (
            patch("src.services.monitoring.httpx.AsyncClient") as mock_client,
            patch.object(service, "_check_relay", AsyncMock(return_value=True)),
        ):
            instance = AsyncMock()

            async def side_get(url: str) -> MagicMock:
                resp = MagicMock()
                resp.status_code = 500 if url.startswith(m1_url) else 200
                return resp

            instance.get = AsyncMock(side_effect=side_get)
            mock_client.return_value.__aenter__.return_value = instance

            checks = await service._cluster_checks()
            assert checks["qdrant"] is True
            assert checks["ollama m1"] is False
            assert checks["ollama m2"] is True
            assert checks["ollama m3"] is True
            assert checks["glances"] is True
            assert checks["relay"] is True

    async def test_httpx_exception(self, service: MonitoringService) -> None:
        with (
            patch("src.services.monitoring.httpx.AsyncClient") as mock_client,
            patch.object(service, "_check_relay", AsyncMock(return_value=False)),
        ):
            instance = AsyncMock()
            instance.get = AsyncMock(side_effect=Exception("timeout"))
            mock_client.return_value.__aenter__.return_value = instance

            checks = await service._cluster_checks()
            assert not any(v for v in checks.values())

    async def test_card_cluster_all_ok(self, service: MonitoringService) -> None:
        with (
            patch.object(
                service,
                "_cluster_checks",
                AsyncMock(
                    return_value={
                        "qdrant": True,
                        "ollama m1": True,
                        "ollama m2": True,
                        "ollama m3": True,
                        "glances": True,
                        "relay": True,
                    }
                ),
            ),
        ):
            card = await service._card_cluster()
            assert card.status == "ok"
            assert len(card.metrics) == 6
            for m in card.metrics:
                assert m.status == "ok"

    async def test_card_cluster_one_down(self, service: MonitoringService) -> None:
        with (
            patch.object(
                service,
                "_cluster_checks",
                AsyncMock(
                    return_value={
                        "qdrant": True,
                        "ollama m1": True,
                        "ollama m2": False,
                        "ollama m3": True,
                        "glances": True,
                        "relay": True,
                    }
                ),
            ),
        ):
            card = await service._card_cluster()
            assert card.status == "warn"
            metrics_by_label = {m.label: m for m in card.metrics}
            assert metrics_by_label["OLLAMA M2"].status == "crit"


class TestCheckRelay:
    @pytest.fixture
    def service(self) -> MonitoringService:
        return MonitoringService(
            ollama_pool=MagicMock(),
            memory_manager=None,
        )

    async def test_file_missing(self, service: MonitoringService) -> None:
        with patch.object(
            service._settings,
            "nfs_relay_path",
            new=Path(r"C:\nonexistent\relay.json"),
        ):
            result = await service._check_relay()
            assert result is False

    async def test_file_too_old(self, service: MonitoringService) -> None:
        old_time = (datetime.now() - timedelta(hours=2)).timestamp()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
            f.write(b"{}")
            tmp_path = f.name
        try:
            os.utime(tmp_path, (old_time, old_time))
            with patch.object(
                service._settings,
                "nfs_relay_path",
                new=Path(tmp_path),
            ):
                result = await service._check_relay()
                assert result is False
        finally:
            os.unlink(tmp_path)

    async def test_file_recent(self, service: MonitoringService) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
            f.write(b"{}")
            tmp_path = f.name
        try:
            with patch.object(
                service._settings,
                "nfs_relay_path",
                new=Path(tmp_path),
            ):
                result = await service._check_relay()
                assert result is True
        finally:
            os.unlink(tmp_path)

    async def test_file_os_error(self, service: MonitoringService) -> None:
        """Erreur OS pendant le stat → False (jamais d'exception)."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
            f.write(b"{}")
            tmp_path = f.name
        try:
            with (
                patch.object(
                    service._settings,
                    "nfs_relay_path",
                    new=Path(tmp_path),
                ),
                patch("os.path.getmtime", side_effect=OSError("permission")),
            ):
                result = await service._check_relay()
                assert result is False
        finally:
            os.unlink(tmp_path)


class TestIntegrationSummary:
    async def test_summary_with_all_states(self) -> None:
        m1_state = MachineMemoryState(
            machine="m1",
            timestamp=datetime.now(),
            qdrant_ram_mb=256,
            qdrant_points_count=5000,
            loaded_models=["nomic-embed-text:v1.5"],
        )
        m2_state = MachineMemoryState(
            machine="m2",
            timestamp=datetime.now(),
            rtx4000_vram_mb=2048,
            judge_vram_mb=1024,
            advocate_vram_mb=512,
            reranker_vram_mb=256,
            loaded_models=["llama3.2:3b"],
        )
        m3_state = MachineMemoryState(
            machine="m3",
            timestamp=datetime.now(),
            bc250_unified_mb=2048,
            bc250_cpu_load=0.3,
            loaded_models=["qwen2.5:7b"],
        )

        mock_mm = AsyncMock()
        mock_snapshot = AsyncMock()
        mock_snapshot.m1 = m1_state
        mock_snapshot.m2 = m2_state
        mock_snapshot.m3 = m3_state
        mock_snapshot.alerts = [
            Alert(
                level="warning",
                machine="m2",
                metric="vram",
                current=7000.0,
                threshold=6000.0,
                message="test alert",
            )
        ]
        mock_mm.cluster_snapshot = AsyncMock(return_value=mock_snapshot)

        service = MonitoringService(
            ollama_pool=MagicMock(),
            memory_manager=mock_mm,
        )

        with (
            patch.object(
                service,
                "_cluster_checks",
                AsyncMock(
                    return_value=dict.fromkeys(
                        ("qdrant", "ollama m1", "ollama m2", "ollama m3", "glances", "relay"), True
                    )
                ),
            ),
        ):
            result = await service.summary()
            assert result["status"] == "ok"
            assert "offline" not in result
            assert len(result["cards"]) == 3
            assert len(result["alerts"]) == 1
            assert result["alerts"][0]["metric"] == "vram"

    async def test_summary_snapshot_exception(self) -> None:
        mock_mm = AsyncMock()
        mock_mm.cluster_snapshot = AsyncMock(side_effect=Exception("Snapshot failed"))
        service = MonitoringService(
            ollama_pool=MagicMock(),
            memory_manager=mock_mm,
        )

        with (
            patch.object(
                service,
                "_cluster_checks",
                AsyncMock(
                    return_value=dict.fromkeys(
                        ("qdrant", "ollama m1", "ollama m2", "ollama m3", "glances", "relay"), True
                    )
                ),
            ),
        ):
            result = await service.summary()
            assert result["status"] == "ok"
            for card_key in ("m1", "m2", "m3"):
                assert result["cards"][card_key]["status"] == "crit"

    async def test_summary_empty_alerts_when_no_snapshot(self) -> None:
        mock_mm = AsyncMock()
        mock_mm.cluster_snapshot = AsyncMock(side_effect=Exception("Snapshot failed"))
        service = MonitoringService(
            ollama_pool=MagicMock(),
            memory_manager=mock_mm,
        )

        with (
            patch.object(
                service,
                "_cluster_checks",
                AsyncMock(
                    return_value=dict.fromkeys(
                        ("qdrant", "ollama m1", "ollama m2", "ollama m3", "glances", "relay"), True
                    )
                ),
            ),
        ):
            result = await service.summary()
            assert result["alerts"] == []

    async def test_close_with_memory_manager(self) -> None:
        mock_mm = AsyncMock()
        service = MonitoringService(
            ollama_pool=MagicMock(),
            memory_manager=mock_mm,
        )
        await service.close()
        mock_mm.close.assert_awaited_once()

    async def test_get_memory_manager_lazy_init(self) -> None:
        service = MonitoringService(
            ollama_pool=MagicMock(),
            memory_manager=None,
        )
        mm = service._get_memory_manager()
        assert mm is not None
        assert mm is service._memory_manager
