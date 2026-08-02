"""Tests B4 — WikiAgent (vault temporaire tmp_path, I/O réels)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents.skills.loader import load_skill
from src.agents.wiki_agent import (
    PageExistsError,
    WikiAgent,
    WikiAgentError,
    WikiPathTraversalError,
)


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    return tmp_path / "vault"


@pytest.fixture
def agent(vault: Path) -> WikiAgent:
    return WikiAgent(vault)


# ── write_page ─────────────────────────────────────────────────────

async def test_write_page_creates_markdown_with_frontmatter(agent: WikiAgent, vault: Path) -> None:
    await agent.write_page(
        "concepts/bc250.md",
        "Le BC-250 est une carte Vulkan.",
        {"type": "concept", "title": "BC-250"},
    )
    page = (vault / "concepts" / "bc250.md").read_text(encoding="utf-8")
    assert page.startswith("---")
    assert "type: concept" in page
    assert "status: draft" in page
    assert "verified: unverified" in page
    assert "Le BC-250 est une carte Vulkan." in page


async def test_write_page_defaults_frontmatter(agent: WikiAgent, vault: Path) -> None:
    await agent.write_page("page.md", "contenu", {})
    page = (vault / "page.md").read_text(encoding="utf-8")
    assert "type: concept" in page
    assert "title: page" in page


async def test_write_page_requires_overwrite(agent: WikiAgent, vault: Path) -> None:
    await agent.write_page("page.md", "v1", {})
    with pytest.raises(PageExistsError):
        await agent.write_page("page.md", "v2", {})
    await agent.write_page("page.md", "v2", {}, overwrite=True)
    assert "v2" in (vault / "page.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "bad_path",
    ["../escape.md", "/absolu.md", "..\\escape.md", "concepts/../../out.md"],
)
async def test_write_page_rejects_traversal(agent: WikiAgent, bad_path: str) -> None:
    with pytest.raises(WikiPathTraversalError):
        await agent.write_page(bad_path, "x", {})


async def test_write_page_creates_parent_dirs(agent: WikiAgent, vault: Path) -> None:
    await agent.write_page("deep/nested/dir/page.md", "x", {})
    assert (vault / "deep" / "nested" / "dir" / "page.md").is_file()


# ── update_index ───────────────────────────────────────────────────

async def test_update_index_lists_pages(agent: WikiAgent, vault: Path) -> None:
    await agent.write_page("concepts/a.md", "A", {"type": "concept"})
    await agent.write_page("entities/b.md", "B", {"type": "entity"})
    await agent.update_index()
    index = (vault / "index.md").read_text(encoding="utf-8")
    assert "[[concepts/a.md]]" in index
    assert "[[entities/b.md]]" in index
    assert "concept" in index
    assert "entity" in index


async def test_update_index_empty_vault(agent: WikiAgent, vault: Path) -> None:
    await agent.update_index()
    index = (vault / "index.md").read_text(encoding="utf-8")
    assert "vault vide" in index


async def test_update_index_creates_parent(agent: WikiAgent, vault: Path) -> None:
    await agent.update_index()
    assert (vault / "index.md").is_file()


# ── append_log ─────────────────────────────────────────────────────

async def test_append_log_creates_file(agent: WikiAgent, vault: Path) -> None:
    await agent.append_log({"query": "test", "decision": "publish", "final_score": 0.8})
    log = (vault / "log.md").read_text(encoding="utf-8")
    assert "Journal des interactions" in log
    assert "query: test" in log
    assert "decision: publish" in log


async def test_append_log_appends_entries(agent: WikiAgent, vault: Path) -> None:
    await agent.append_log({"query": "q1"})
    await agent.append_log({"query": "q2"})
    log = (vault / "log.md").read_text(encoding="utf-8")
    assert log.count("query: q1") == 1
    assert log.count("query: q2") == 1


# ── validate_frontmatter ───────────────────────────────────────────

async def test_validate_frontmatter_valid(agent: WikiAgent, vault: Path) -> None:
    await agent.write_page(
        "concepts/ok.md",
        "x",
        {"type": "concept", "title": "OK", "status": "published", "verified": "machine-confirmed"},
    )
    result = await agent.validate_frontmatter("concepts/ok.md")
    assert result["valid"] is True
    assert result["issues"] == []


async def test_validate_frontmatter_missing_required(agent: WikiAgent, vault: Path) -> None:
    # write_page remplit les défauts : on écrit un frontmatter incomplet manuellement
    page = vault / "concepts" / "bad.md"
    page.parent.mkdir(parents=True)
    page.write_text("---\ntype: concept\n---\ncontenu\n", encoding="utf-8")
    result = await agent.validate_frontmatter("concepts/bad.md")
    assert result["valid"] is False
    issues = " ".join(result["issues"])
    assert "title" in issues
    assert "status" in issues
    assert "verified" in issues
    assert "created" in issues


async def test_validate_frontmatter_invalid_type(agent: WikiAgent, vault: Path) -> None:
    await agent.write_page("concepts/t.md", "x", {"type": "toto"})
    result = await agent.validate_frontmatter("concepts/t.md")
    assert result["valid"] is False
    assert any("type invalide" in i for i in result["issues"])


async def test_validate_frontmatter_missing_page(agent: WikiAgent) -> None:
    result = await agent.validate_frontmatter("nope.md")
    assert result["valid"] is False
    assert "introuvable" in result["issues"][0]


async def test_validate_frontmatter_invalid_status(agent: WikiAgent, vault: Path) -> None:
    await agent.write_page("concepts/s.md", "x", {"type": "concept", "status": "weird"})
    result = await agent.validate_frontmatter("concepts/s.md")
    assert any("status invalide" in i for i in result["issues"])


# ── lint ───────────────────────────────────────────────────────────

async def test_lint_detects_orphans(agent: WikiAgent, vault: Path) -> None:
    await agent.write_page("concepts/alpha.md", "Voir [[concepts/beta.md]]", {"type": "concept"})
    await agent.write_page("concepts/beta.md", "contenu", {"type": "concept"})
    result = await agent.lint()
    assert "concepts/beta.md" not in result["orphans"]
    assert "concepts/alpha.md" in result["orphans"]


async def test_lint_detects_stale(agent: WikiAgent, vault: Path) -> None:
    await agent.write_page(
        "concepts/old.md",
        "x",
        {"type": "concept", "stale_after": "2000-01-01"},
    )
    result = await agent.lint()
    assert "concepts/old.md" in result["stale"]


async def test_lint_empty_vault(agent: WikiAgent, vault: Path) -> None:
    result = await agent.lint()
    assert result["orphans"] == []
    assert result["stale"] == []
    assert result["gaps"] == []
    assert result["contradictions"] == []


async def test_lint_requires_vault_exists(agent: WikiAgent) -> None:
    result = await agent.lint()
    assert isinstance(result, dict)


# ── skill_reference ────────────────────────────────────────────────

def test_skill_reference_returns_wiki_rules(agent: WikiAgent) -> None:
    assert agent.skill_reference() == load_skill("wiki_agent")
    assert "frontmatter" in agent.skill_reference()
    assert "lint" in agent.skill_reference()


def test_default_vault_from_settings() -> None:
    from src.core.settings import get_settings

    agent = WikiAgent()
    assert agent.vault == get_settings().wiki_vault_path


# ── erreurs ────────────────────────────────────────────────────────

def test_wiki_agent_error_is_exception() -> None:
    assert issubclass(WikiAgentError, Exception)
