"""Loader des Agent Skills — charge les SKILL.md par rôle.

Localisation : ``src/agents/skills/<role>/SKILL.md`` (colocalisé avec le
code Python, cf. B5.4). Chargeur avec cache mémoire (``functools.cache``)
et fail-fast : rôle ou fichier manquant → ``ValueError`` explicite.

Usage :
    from src.agents.skills.loader import load_skill

    skill = load_skill("generator")   # texte brut du SKILL.md
"""

from __future__ import annotations

import functools
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent

ROLES = frozenset(
    {"generator", "judge", "advocate", "evaluator", "wiki_agent", "planner", "rewriter"}
)


@functools.cache
def load_skill(role: str) -> str:
    """Charge et met en cache le contenu du SKILL.md d'un rôle.

    Lève ``ValueError`` si le rôle est inconnu, ``FileNotFoundError`` si
    le fichier SKILL.md du rôle est absent.
    """
    if role not in ROLES:
        raise ValueError(
            f"Rôle inconnu: {role!r}. Rôles disponibles: {sorted(ROLES)}"
        )
    skill_path = _SKILLS_DIR / role / "SKILL.md"
    if not skill_path.is_file():
        raise FileNotFoundError(
            f"SKILL.md introuvable pour le rôle {role!r} (attendu: {skill_path})"
        )
    return skill_path.read_text(encoding="utf-8").strip()


def skill_reference(role: str) -> str:
    """Alias sémantique de ``load_skill`` (règles de référence par rôle)."""
    return load_skill(role)


def clear_cache() -> None:
    """Vide le cache de ``load_skill`` (utile en test)."""
    load_skill.cache_clear()
