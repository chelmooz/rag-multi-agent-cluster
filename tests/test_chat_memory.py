"""Tests ChatMemory (L1 sliding window)."""
from __future__ import annotations

from unittest.mock import patch

from src.services.chat_memory import ChatMemory


def _entries(n: int) -> list[dict]:
    return [{"role": "user" if i % 2 == 0 else "assistant",
             "content": f"msg {i} " * 50} for i in range(n)]


def test_empty_history_returns_empty() -> None:
    assert ChatMemory([]).get_window() == []
    assert ChatMemory(None).get_window() == []
    assert ChatMemory([]).get_context_string() is None


def test_single_entry_returns_first_only() -> None:
    entries = [{"role": "user", "content": "hello"}]
    mem = ChatMemory(entries)
    assert mem.get_window() == entries


def test_window_anclage_first_plus_recent() -> None:
    """Avec 22 messages (> 20 = chat_history_max*2), le 1er + 19 derniers."""
    entries = _entries(22)
    mem = ChatMemory(entries)
    window = mem.get_window()
    assert len(window) == 20  # 1 ancre + 19 recent
    assert window[0] == entries[0]  # ancre
    assert window[1] == entries[3]  # 22 - 19 = 3
    assert window[-1] == entries[21]


def test_window_no_troncature_under_limit() -> None:
    """Avec 10 messages (< 20), aucune troncature : historique complet."""
    entries = _entries(10)
    window = ChatMemory(entries).get_window()
    assert window == entries


def test_context_string_planner() -> None:
    mem = ChatMemory([{"role": "user", "content": "BC250 ?"}])
    assert mem.get_context_string() == "BC250 ?"


def test_context_string_empty_returns_none() -> None:
    assert ChatMemory([]).get_context_string() is None
    assert ChatMemory(None).get_context_string() is None


def test_max_chars_budget_truncates() -> None:
    """Si max_chars depassé, troncature en respectant le budget."""
    from src.core.settings import Settings

    fake_settings = Settings()
    fake_settings.chat_max_context_chars = 300
    with patch("src.services.chat_memory.get_settings", return_value=fake_settings):
        entries = [{"role": "user", "content": "x" * 100} for _ in range(10)]
        mem = ChatMemory(entries)
        window = mem.get_window()
    total = sum(len(e["content"]) for e in window)
    assert total <= 300
    assert window[0] == entries[0]


def test_append_and_clear() -> None:
    mem = ChatMemory()
    assert len(mem) == 0
    mem.append("user", "hello")
    assert len(mem) == 1
    mem.clear()
    assert len(mem) == 0


def test_repr() -> None:
    assert repr(ChatMemory([{"role": "user", "content": "x"}])) == (
        "ChatMemory(entries=1)"
    )
