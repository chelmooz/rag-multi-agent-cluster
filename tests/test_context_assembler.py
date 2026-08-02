"""Tests B3 — ContextAssembler (fusion, tri, fenêtre anti lost-in-the-middle)."""

from __future__ import annotations

from src.agents.context_assembler import (
    MAX_CONTEXT_CHARS,
    AssembledChunk,
    AssembledContext,
    ContextAssembler,
)


def _chunk(source_id: str, text: str, score: float) -> dict:
    return {"id": source_id, "score": score, "payload": {"text": text, "source": source_id}}


def test_assemble_empty_chunks() -> None:
    ctx = ContextAssembler().assemble("q", [])
    assert ctx.chunks == []
    assert ctx.total_chars == 0
    assert ctx.truncated is False


def test_assemble_sorts_by_score_desc() -> None:
    chunks = [
        _chunk("s1", "aaa", 0.3),
        _chunk("s2", "bbb", 0.9),
        _chunk("s3", "ccc", 0.6),
    ]
    ctx = ContextAssembler().assemble("q", chunks)
    assert [c.source_id for c in ctx.chunks] == ["s2", "s3", "s1"]


def test_assemble_preserves_payload_text_and_source() -> None:
    ctx = ContextAssembler().assemble("q", [_chunk("s7", "texte utile", 0.8)])
    assert ctx.chunks[0] == AssembledChunk(source_id="s7", text="texte utile", score=0.8)


def test_assemble_fallback_text_when_payload_missing() -> None:
    ctx = ContextAssembler().assemble(
        "q", [{"id": "s1", "score": 0.5, "payload": {"source": "s1"}}]
    )
    assert ctx.chunks[0].text == ""


def test_assemble_truncates_to_budget() -> None:
    chunks = [_chunk("s1", "x" * 9000, 0.9), _chunk("s2", "y" * 5000, 0.8)]
    ctx = ContextAssembler().assemble("q", chunks, max_chars=10_000)
    assert [c.source_id for c in ctx.chunks] == ["s1"]
    assert ctx.truncated is True


def test_assemble_skips_chunk_larger_than_budget() -> None:
    chunks = [_chunk("s1", "x" * 500, 0.9), _chunk("s2", "y" * 100, 0.5)]
    ctx = ContextAssembler().assemble("q", chunks, max_chars=200)
    assert [c.source_id for c in ctx.chunks] == ["s2"]
    assert ctx.truncated is True


def test_assemble_internal_knowledge_within_budget() -> None:
    chunks = [_chunk("s1", "x" * 500, 0.9)]
    knowledge = ["savoir interne A"]
    ctx = ContextAssembler().assemble("q", chunks, internal_knowledge=knowledge, max_chars=1000)
    assert ctx.internal_knowledge == knowledge
    assert ctx.chunks[0].source_id == "s1"


def test_assemble_internal_knowledge_exceeding_budget_dropped() -> None:
    chunks = [_chunk("s1", "x" * 500, 0.9)]
    knowledge = ["z" * 600]
    ctx = ContextAssembler().assemble("q", chunks, internal_knowledge=knowledge, max_chars=700)
    assert ctx.chunks[0].source_id == "s1"
    assert ctx.internal_knowledge == []


def test_default_budget_is_max_context_chars() -> None:
    assert MAX_CONTEXT_CHARS == 12_000
    ctx = ContextAssembler().assemble(
        "q", [_chunk("s1", "a" * (MAX_CONTEXT_CHARS - 10), 0.9)]
    )
    assert len(ctx.chunks) == 1
    assert ctx.truncated is False


def test_total_chars_property() -> None:
    ctx = ContextAssembler().assemble(
        "q", [_chunk("s1", "abc", 0.9)], internal_knowledge=["de"]
    )
    assert ctx.total_chars == 5
    assert isinstance(ctx, AssembledContext)
