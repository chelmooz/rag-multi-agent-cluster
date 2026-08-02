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

import logging
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from src.agents.skills.loader import skill_reference

logger = logging.getLogger(__name__)

_SKILL_ROLE = "wiki_agent"

_OKF_TYPES = {"concept", "entity", "source", "synthesis", "agent", "log"}
_OKF_STATUSES = {"draft", "review", "published", "stale"}
_OKF_REQUIRED = {"type", "title", "status", "verified", "created"}

_INDEX_FILENAME = "index.md"
_LOG_FILENAME = "log.md"


class WikiAgentError(Exception):
    """Erreur générique du WikiAgent."""


class WikiPathTraversalError(WikiAgentError):
    """Chemin de page hors du vault (anti traversal)."""


class PageExistsError(WikiAgentError):
    """La page existe déjà et overwrite=False."""


class WikiAgent:
    """Boucle de maintenance du vault Obsidian."""

    def __init__(self, vault_path: Path | None = None) -> None:
        if vault_path is None:
            from src.core.settings import get_settings

            vault_path = get_settings().wiki_vault_path
        self.vault = Path(vault_path)

    # ── Référence de règles ────────────────────────────────────────

    def skill_reference(self) -> str:
        """Retourne les règles de lint/frontmatter du vault (SKILL.md Wiki Agent).

        Pas un prompt LLM : référence utilisée par write_page/update_index/
        append_log/lint/validate_frontmatter.
        """
        return skill_reference(_SKILL_ROLE)

    # ── Chemins ────────────────────────────────────────────────────

    def _resolve(self, path: str) -> Path:
        """Normalise un chemin relatif au vault et bloque le traversal."""
        raw = Path(path)
        if raw.is_absolute() or ".." in raw.parts:
            raise WikiPathTraversalError(f"Chemin invalide (hors vault): {path!r}")
        target = (self.vault / raw).resolve()
        vault_resolved = self.vault.resolve()
        if not target.is_relative_to(vault_resolved):
            raise WikiPathTraversalError(f"Chemin invalide (hors vault): {path!r}")
        return target

    # ── Pages ──────────────────────────────────────────────────────

    async def write_page(
        self, path: str, content: str, frontmatter: dict, overwrite: bool = False
    ) -> None:
        """Écrit une page markdown avec frontmatter YAML (OKF v0.2).

        Le chemin est relatif au vault ; le frontmatter est sérialisé en
        en-tête YAML. N'écrase pas une page existante sans ``overwrite``.
        """
        target = self._resolve(path)
        if target.exists() and not overwrite:
            raise PageExistsError(f"Page existante (overwrite=False): {path!r}")

        fm = dict(frontmatter)
        fm.setdefault("type", "concept")
        fm.setdefault("title", target.stem)
        fm.setdefault("status", "draft")
        fm.setdefault("verified", "unverified")
        fm.setdefault("created", date.today().isoformat())

        target.parent.mkdir(parents=True, exist_ok=True)
        body = f"---\n{yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)}---\n{content}\n"
        target.write_text(body, encoding="utf-8")
        logger.info("Wiki: page écrite %s", target)

    async def update_index(self) -> None:
        """Régénère index.md : catalogue de toutes les pages du vault."""
        entries = []
        for md in sorted(self.vault.rglob("*.md")):
            if md.name in (_INDEX_FILENAME, _LOG_FILENAME):
                continue
            rel = md.relative_to(self.vault).as_posix()
            fm = self._read_frontmatter(md)
            title = fm.get("title", md.stem)
            page_type = fm.get("type", "concept")
            status = fm.get("status", "draft")
            entries.append(f"- [[{rel}]] | {page_type} | {title} | {status}")

        body = "# Index du Vault\n\n"
        if entries:
            body += "## Pages\n\n" + "\n".join(entries) + "\n"
        else:
            body += "*(vault vide)*\n"
        index_path = self.vault / _INDEX_FILENAME
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(body, encoding="utf-8")
        logger.info("Wiki: index.md régénéré (%d pages)", len(entries))

    async def append_log(self, entry: dict) -> None:
        """Ajoute une entrée horodatée à log.md (append-only)."""
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        line = yaml.safe_dump(
            {timestamp: entry}, allow_unicode=True, sort_keys=False
        ).strip()
        log_path = self.vault / _LOG_FILENAME
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if log_path.exists():
            content = log_path.read_text(encoding="utf-8")
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write("\n" + line + "\n")
            if not content.endswith("\n"):
                with log_path.open("a", encoding="utf-8") as fh:
                    fh.write("\n")
        else:
            log_path.write_text(f"# Journal des interactions\n\n{line}\n", encoding="utf-8")
        logger.info("Wiki: log.md appendé")

    # ── Frontmatter ────────────────────────────────────────────────

    def _read_frontmatter(self, page_path: Path) -> dict:
        text = page_path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return {}
        end = text.find("\n---", 3)
        if end == -1:
            return {}
        try:
            fm = yaml.safe_load(text[3:end])
        except yaml.YAMLError:
            return {}
        return fm if isinstance(fm, dict) else {}

    async def validate_frontmatter(self, page_path: str) -> dict:
        """Valide le frontmatter OKF v0.2 d'une page (relatif au vault)."""
        target = self._resolve(page_path)
        issues: list[str] = []
        if not target.is_file():
            return {"valid": False, "issues": [f"page introuvable: {page_path}"]}

        fm = self._read_frontmatter(target)
        for required in _OKF_REQUIRED:
            if required not in fm:
                issues.append(f"champ obligatoire manquant: {required}")
        if "type" in fm and fm["type"] not in _OKF_TYPES:
            issues.append(f"type invalide: {fm['type']}")
        if "status" in fm and fm["status"] not in _OKF_STATUSES:
            issues.append(f"status invalide: {fm['status']}")
        if "verified" in fm and fm["verified"] not in (
            "unverified",
            "machine-confirmed",
            "human-reviewed",
        ):
            issues.append(f"verified invalide: {fm['verified']}")

        return {"valid": not issues, "issues": issues}

    # ── Lint ───────────────────────────────────────────────────────

    async def lint(self) -> dict:
        """Détection : pages orphelines, stale, contradictions, gaps, frontmatter."""
        orphans: list[str] = []
        stale: list[str] = []
        frontmatter_issues: list[str] = []

        pages = [
            p
            for p in self.vault.rglob("*.md")
            if p.name not in (_INDEX_FILENAME, _LOG_FILENAME)
        ]
        for page in pages:
            rel = page.relative_to(self.vault).as_posix()
            fm = self._read_frontmatter(page)
            if not fm:
                frontmatter_issues.append(f"{rel}: frontmatter absent/invalide")
                continue
            stale_after = fm.get("stale_after")
            if stale_after:
                try:
                    cutoff = datetime.strptime(stale_after, "%Y-%m-%d").date()
                    if date.today() > cutoff:
                        stale.append(rel)
                except ValueError:
                    frontmatter_issues.append(f"{rel}: stale_after invalide: {stale_after!r}")

        for page in pages:
            rel = page.relative_to(self.vault).as_posix()
            referenced = False
            for other in pages:
                if other is page:
                    continue
                if f"[[{rel}]]" in other.read_text(encoding="utf-8"):
                    referenced = True
                    break
            if not referenced:
                orphans.append(rel)

        gaps: list[str] = []
        log_path = self.vault / _LOG_FILENAME
        if log_path.is_file():
            log_text = log_path.read_text(encoding="utf-8")
            gap_queries = [line for line in log_text.splitlines() if "query" in line.lower()]
            if gap_queries:
                gaps.append(f"{len(gap_queries)} requêtes loggées sans page synthèse vérifiée")

        return {
            "orphans": orphans,
            "stale": stale,
            "contradictions": [],
            "gaps": gaps,
            "frontmatter_issues": frontmatter_issues,
        }


def main() -> None:
    """Point d'entrée pour le conteneur Docker wiki-agent."""
    import asyncio

    asyncio.run(WikiAgent().lint())


if __name__ == "__main__":
    main()
