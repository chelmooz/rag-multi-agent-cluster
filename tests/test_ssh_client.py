"""Tests SSHClient — asyncssh mocké, pas de serveur réel (§5.6).

Couvre : connect (succès, key_path absent, erreur connexion),
execute (stdout, timeout, erreur commande, connexion non ouverte),
close, context manager.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.ssh_client import (
    SSHClient,
    SSHCommandError,
    SSHConnectionError,
)


@pytest.fixture
def ssh() -> SSHClient:
    return SSHClient(host="m2.local", user="root", key_path=Path("/tmp/fake_key"), port=22)


class TestConnect:
    async def test_connect_success(self, ssh: SSHClient) -> None:
        """Clé existe → auth par clé, connexion établie."""
        patch_target = "src.services.ssh_client.asyncssh.connect"
        with patch(patch_target, new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = AsyncMock()
            await ssh.connect()
            mock_connect.assert_awaited_once()
            assert ssh._conn is not None

    async def test_connect_idempotent(self, ssh: SSHClient) -> None:
        """connect() ne répare pas si déjà connecté."""
        fake = AsyncMock()
        ssh._conn = fake
        patch_target = "src.services.ssh_client.asyncssh.connect"
        with patch(patch_target, new_callable=AsyncMock) as mock_connect:
            await ssh.connect()
            mock_connect.assert_not_awaited()

    async def test_connect_failure_raises_connection_error(self) -> None:
        """asyncssh.Error → SSHConnectionError."""
        from asyncssh import Error as AsyncsshError

        ssh = SSHClient(host="bad.local", user="root", port=22)
        with patch("src.services.ssh_client.asyncssh.connect", new_callable=AsyncMock) as mock:
            mock.side_effect = AsyncsshError("connect", "network unreachable")
            with pytest.raises(SSHConnectionError, match="Connexion SSH impossible"):
                await ssh.connect()


class TestExecute:
    async def test_execute_without_connection_connects(self, ssh: SSHClient) -> None:
        """execute() auto-connecte si _conn est None."""
        ssh._conn = None
        mock_run = AsyncMock(return_value=MagicMock(returncode=0, stdout="100\n", stderr=""))

        async def _fake_connect(self_) -> None:
            ssh._conn = MagicMock()
            ssh._conn.run = mock_run

        with patch.object(SSHClient, "connect", new=_fake_connect):
            result = await ssh.execute("free -b")
        assert result == "100"

    async def test_execute_success(self, ssh: SSHClient) -> None:
        """stdout strippé retourné."""
        ssh._conn = AsyncMock()
        ssh._conn.run = AsyncMock(
            return_value=MagicMock(returncode=0, stdout=b"  3500  \n", stderr=b"")
        )
        result = await ssh.execute("nvidia-smi")
        assert result == "3500"

    async def test_execute_timeout(self, ssh: SSHClient) -> None:
        """Timeout → SSHCommandError."""
        ssh._conn = AsyncMock()
        ssh._conn.run = AsyncMock(side_effect=TimeoutError("slow"))
        with pytest.raises(SSHCommandError, match="Timeout"):
            await ssh.execute("nvidia-smi")

    async def test_execute_command_error(self, ssh: SSHClient) -> None:
        """rc != 0 → SSHCommandError avec stderr."""
        ssh._conn = AsyncMock()
        ssh._conn.run = AsyncMock(
            return_value=MagicMock(returncode=1, stdout="", stderr="command not found")
        )
        with pytest.raises(SSHCommandError, match="rc=1"):
            await ssh.execute("nvidia-smi --bad-flag")

    async def test_execute_bytes_stderr_converted(self, ssh: SSHClient) -> None:
        """stderr bytes → str decode."""
        ssh._conn = AsyncMock()
        ssh._conn.run = AsyncMock(
            return_value=MagicMock(returncode=2, stdout="", stderr=b"bytes error")
        )
        with pytest.raises(SSHCommandError, match="bytes error"):
            await ssh.execute("fail")


class TestClose:
    async def test_close_releases_connection(self, ssh: SSHClient) -> None:
        """close() libère _conn."""
        mock_conn = MagicMock()  # sync close(), wait_closed() async
        mock_conn.wait_closed = AsyncMock()
        ssh._conn = mock_conn
        await ssh.close()
        mock_conn.close.assert_called_once()
        mock_conn.wait_closed.assert_awaited_once()
        assert ssh._conn is None

    async def test_close_when_none_noop(self, ssh: SSHClient) -> None:
        """close() ne fait rien si pas connecté."""
        ssh._conn = None
        await ssh.close()  # ne doit pas lever


class TestContextManager:
    async def test_aenter_aexit(self) -> None:
        """async with SSHClient() → connect + close."""
        ssh = SSHClient(host="m2.local", user="root", port=22)
        with patch.object(SSHClient, "connect", new_callable=AsyncMock) as mock_conn, \
             patch.object(SSHClient, "close", new_callable=AsyncMock) as mock_close:
            async with ssh as client:
                assert client is ssh
            mock_conn.assert_awaited_once()
            mock_close.assert_awaited_once()
