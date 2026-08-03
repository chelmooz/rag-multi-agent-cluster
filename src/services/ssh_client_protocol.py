"""Protocoles d'injection de dépendance pour SSH — test sans matériel réel.

Permet de mocker ``SSHClient`` via ``spec`` au lieu de ``MagicMock`` nu,
évitant les régressions comme R1 (§5.8).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SSHClientProtocol(Protocol):
    """Interface minimale pour un client SSH async consommé par MemoryManager.

    Les méthodes contractuelles (``execute``, ``close``) sont celles
    utilisées par ``MemoryManager``. La classe concrète
    ``src.services.ssh_client.SSHClient`` implémente ce protocole
    via duck typing.
    """

    async def execute(self, command: str) -> str: ...

    async def close(self) -> None: ...
