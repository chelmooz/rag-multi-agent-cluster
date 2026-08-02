"""Validation du frontmatter OKF v0.2 + détection stale/orphelins/contradictions.

CLI sur le WikiAgent (B8) — remplace le stub Phase 0.7.

Flags :
--stale          Pages dont stale_after est dépassé
--orphan         Pages non référencées dans le vault (liens [[...]])
--contradiction  Pages avec des affirmations contradictoires
--validate       Valide le frontmatter de toutes les pages
--fix            Corrige automatiquement les problèmes simples
--wiki-path      Chemin du vault wiki (défaut : settings.wiki_vault_path)

Sans flag : lint complet (orphans + stale + gaps + frontmatter).
Avec --validate : validation frontmatter OKF de chaque page.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from src.agents.wiki_agent import WikiAgent


def _print_section(title: str, items: list[str], prefix: str = "  - ") -> None:
    print(f"{title} ({len(items)})")
    for item in items:
        print(f"{prefix}{item}")


def main() -> int:
    parser = argparse.ArgumentParser(description="OKF Lint — Validation frontmatter wiki")
    parser.add_argument("--stale", action="store_true", help="Lister les pages stale")
    parser.add_argument("--orphan", action="store_true", help="Lister les pages orphelines")
    parser.add_argument("--contradiction", action="store_true", help="Détecter les contradictions")
    parser.add_argument("--validate", action="store_true", help="Valider le frontmatter OKF")
    parser.add_argument("--fix", action="store_true", help="Corriger automatiquement")
    parser.add_argument("--wiki-path", default=None, help="Chemin du vault wiki")
    args = parser.parse_args()

    vault = Path(args.wiki_path) if args.wiki_path else None
    agent = WikiAgent(vault) if vault else WikiAgent()

    if not agent.vault.is_dir():
        print(f"Erreur : vault introuvable — {agent.vault}")
        return 2

    report = asyncio.run(agent.lint())

    any_flag = args.stale or args.orphan or args.contradiction or args.validate
    exit_code = 0

    if not any_flag or args.orphan:
        _print_section("Pages orphelines", report["orphans"])
        if report["orphans"]:
            exit_code = 1
    if not any_flag or args.stale:
        _print_section("Pages stale", report["stale"])
        if report["stale"]:
            exit_code = 1
    if not any_flag or args.contradiction:
        _print_section("Contradictions", report["contradictions"])
        if report["contradictions"]:
            exit_code = 1
    if not any_flag:
        _print_section("Gaps", report["gaps"])
    if args.validate:
        invalid = 0
        for page in asyncio.run(agent.list_pages()):
            result = asyncio.run(agent.validate_frontmatter(page["path"]))
            if not result["valid"]:
                invalid += 1
                print(f"  INVALIDE {page['path']}: {result['issues']}")
        print(f"Frontmatter OKF : {invalid} page(s) invalide(s)")
        if invalid:
            exit_code = 1

    if args.fix and report["stale"]:
        for rel in report["stale"]:
            target = (agent.vault / rel).resolve()
            text = target.read_text(encoding="utf-8")
            text = text.replace("stale_after:", "stale_after: (expiré)")
            target.write_text(text, encoding="utf-8")
        print(f"Fix : {len(report['stale'])} page(s) stale marquées")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
