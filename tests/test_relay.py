import json
import tempfile
import time
from pathlib import Path

import pytest

from src.services.relay import RelayService


@pytest.fixture
def relay() -> RelayService:
    tmp = tempfile.mkdtemp()
    return RelayService(Path(tmp) / "relay.json", ttl=0.05)


class TestRelay:
    async def test_write_and_read(self, relay: RelayService) -> None:
        await relay.write({"session_id": "abc", "judge": {"status": "done"}})
        data = await relay.read()
        assert data is not None
        assert data["session_id"] == "abc"
        assert data["judge"]["status"] == "done"

    async def test_read_absent(self, relay: RelayService) -> None:
        data = await relay.read()
        assert data is None

    async def test_stale_fresh(self, relay: RelayService) -> None:
        await relay.write({})
        assert not await relay.stale()

    async def test_stale_expired(self, relay: RelayService) -> None:
        await relay.write({})
        time.sleep(0.06)
        assert await relay.stale()

    async def test_stale_absent(self, relay: RelayService) -> None:
        assert await relay.stale()

    async def test_read_returns_none_when_stale(self, relay: RelayService) -> None:
        await relay.write({"session_id": "abc"})
        time.sleep(0.06)
        data = await relay.read()
        assert data is None

    async def test_write_is_atomic(self, relay: RelayService) -> None:
        large_data = {"key": "x" * 10000}
        await relay.write(large_data)
        assert relay.relay_path.exists()
        assert not relay.relay_path.with_suffix(".tmp").exists()
        content = json.loads(relay.relay_path.read_text(encoding="utf-8"))
        assert content["key"] == large_data["key"]
