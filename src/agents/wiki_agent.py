"""Wiki Agent — maintenance du vault Obsidian (pattern Karpathy).

Le Wiki Agent est le boucle de maintenance continue du vault :
- Mise à jour de index.md (catalogue des pages)
- Mise à jour de log.md (chronologie des interactions)
- Création/MAJ de pages entities/, concepts/, sources/, synthesis/
- Validation du frontmatter OKF v0.2
- Lint : détection pages orphelines, contradictions, gaps
- Git sidecar auto-commit (cron 1h)
"""

from __future__ import annotations

from src.agents.skills.loader import skill_reference

_SKILL_ROLE = "wiki_agent"


class WikiAgent:
    """Boucle de maintenance du vault Obsidian."""

    def skill_reference(self) -> str:
        """Retourne les règles de lint/frontmatter du vault (SKILL.md Wiki Agent).

        Pas un prompt LLM : référence utilisée par write_page/update_index/
        append_log/lint/validate_frontmatter.
        """
        return skill_reference(_SKILL_ROLE)

    async def write_page(self, path: str, content: str, frontmatter: dict) -> None:
        raise NotImplementedError

    async def update_index(self) -> None:
        raise NotImplementedError

    async def append_log(self, entry: dict) -> None:
        raise NotImplementedError

    async def lint(self) -> dict:
        """Détection : pages orphelines, contradictions, stale, gaps."""
        raise NotImplementedError

    async def validate_frontmatter(self, page_path: str) -> dict:
        """Validation du frontmatter OKF v0.2."""
        raise NotImplementedError


def main() -> None:
    """Point d'entrée pour le conteneur Docker wiki-agent."""
    import asyncio
    asyncio.run(WikiAgent().lint())


if __name__ == "__main__":
    main()
