"""Sliding-window conversation memory (L1 atom layer).

Stateless : reconstruite depuis PipelineState.conversation_history
a chaque node. Remplace les slices [-4:] dispersees.

Layer model (TencentDB inspiration) :
  L1 Atom : {role, content} glissant (ce fichier)
  L2/L3   : extraction scenario/persona -- YAGNI tant non prouve insuffisant
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from src.core.settings import get_settings

ChatEntry = dict[str, str]


class ChatMemory:
    """Fen^etre glissante d'echanges conversationnels (L1).

    Option A : premier message ancre (intent initial) + N derniers
    sous le budget max_chars. chat_history_max = paires, on double
    pour des messages bruts.
    """

    def __init__(self, entries: Sequence[ChatEntry] | None = None) -> None:
        self._entries: list[ChatEntry] = list(entries) if entries else []

    def append(self, role: Literal["user", "assistant"], content: str) -> None:
        self._entries.append({"role": role, "content": content})

    def get_window(self) -> list[ChatEntry]:
        """Fen^etre glissante : premier message ancre + N derniers, sous max_chars."""
        s = get_settings()
        # chat_history_max = paires --> on double pour des messages bruts
        max_messages = s.chat_history_max * 2
        max_chars = s.chat_max_context_chars

        if not self._entries:
            return []

        first = [self._entries[0]]
        if len(self._entries) > max_messages:
            rest = self._entries[-(max_messages - 1) :]
        else:
            rest = self._entries[1:]

        window: list[ChatEntry] = []
        current_chars = 0
        for entry in (first[0], *rest):
            content_len = len(entry.get("content", ""))
            if current_chars + content_len > max_chars and window:
                break
            current_chars += content_len
            window.append(entry)
        return window

    def get_context_string(self) -> str | None:
        """Pour PlannerAgent.plan (attend conversation_context: str | None)."""
        window = self.get_window()
        if not window:
            return None
        text = " ".join(m.get("content", "") for m in window)
        return text or None

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return f"ChatMemory(entries={len(self._entries)})"
