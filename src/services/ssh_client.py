"""Wrapper SSH async pour monitoring M2/M3 (asyncssh).

Utilisé par MemoryManager pour :
- M2 : nvidia-smi (RTX 4000 VRAM)
- M3 : free -b, /proc/loadavg (BC-250 unified GDDR6 + règle d'or CPU)

Connexion passwordless via clé privée (déployée par cloud-init Proxmox),
user root/root sur toutes les machines (confirmé 01/08/2026).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import asyncssh

logger = logging.getLogger(__name__)


class SSHClientError(Exception):
    """Erreur générique SSH."""


class SSHConnectionError(SSHClientError):
    """Connexion SSH impossible."""


class SSHCommandError(SSHClientError):
    """Commande SSH échouée (code retour non nul)."""


class SSHClient:
    """Client SSH async : exécute des commandes sur M2/M3."""

    def __init__(
        self,
        host: str,
        user: str,
        key_path: Path | None = None,
        port: int = 22,
        timeout: int = 10,
    ) -> None:
        self.host = host
        self.user = user
        self.key_path = key_path
        self.port = port
        self.timeout = timeout
        self._conn: asyncssh.SSHClientConnection | None = None

    async def connect(self) -> None:
        """Établit la connexion SSH (clé privée ou agent)."""
        if self._conn is not None:
            return
        try:
            connect_kwargs: dict[str, object] = {
                "host": self.host,
                "username": self.user,
                "port": self.port,
                "known_hosts": None,  # LAN de confiance — vérification host key volontairement off
            }
            if self.key_path is not None and self.key_path.exists():
                connect_kwargs["client_keys"] = [str(self.key_path)]
                logger.debug("SSH %s@%s: auth par clé %s", self.user, self.host, self.key_path)
            else:
                logger.warning(
                    "SSH %s@%s: pas de clé %s — tentative agent/autre méthode",
                    self.user,
                    self.host,
                    self.key_path,
                )
            self._conn = await asyncssh.connect(**connect_kwargs)
        except (asyncssh.Error, OSError) as e:
            raise SSHConnectionError(
                f"Connexion SSH impossible {self.user}@{self.host}:{self.port} — {e}"
            ) from e

    async def close(self) -> None:
        """Ferme la connexion SSH."""
        if self._conn is not None:
            self._conn.close()
            await self._conn.wait_closed()
            self._conn = None

    async def execute(self, command: str) -> str:
        """Exécute une commande via SSH, retourne stdout (strippé)."""
        if self._conn is None:
            await self.connect()
        assert self._conn is not None

        try:
            result = await asyncio.wait_for(
                self._conn.run(command, check=False), timeout=self.timeout
            )
        except TimeoutError as e:
            raise SSHCommandError(f"Timeout SSH ({self.timeout}s) sur {command}") from e
        except asyncssh.Error as e:
            raise SSHCommandError(f"Erreur SSH exécution {command}: {e}") from e

        if result.returncode != 0:
            stderr = result.stderr or ""
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")
            raise SSHCommandError(
                f"Commande SSH échouée (rc={result.returncode}) sur {self.host}: {stderr.strip()}"
            )
        stdout = result.stdout or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        return stdout.strip()

    async def __aenter__(self) -> SSHClient:
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
