"""Validation du frontmatter OKF v0.2 + détection stale/orphelins/contradictions.

STATUT : stub — voir backlog Phase 0.7.

Flags :
--stale          Pages dont stale_after est dépassé
--orphan         Pages non référencées dans index.md
--contradiction  Pages avec des affirmations contradictoires
--validate       Valide le frontmatter de toutes les pages
--fix            Corrige automatiquement les problèmes simples
"""
import argparse


def main():
    parser = argparse.ArgumentParser(description="OKF Lint — Validation frontmatter wiki")
    parser.add_argument("--stale", action="store_true", help="Lister les pages stale")
    parser.add_argument("--orphan", action="store_true", help="Lister les pages orphelines")
    parser.add_argument("--contradiction", action="store_true", help="Détecter les contradictions")
    parser.add_argument("--validate", action="store_true", help="Valider le frontmatter OKF")
    parser.add_argument("--fix", action="store_true", help="Corriger automatiquement")
    parser.add_argument("--wiki-path", default="/data/wiki", help="Chemin du vault wiki")
    parser.parse_args()

    raise NotImplementedError("OKF lint pas encore implémenté — voir backlog Phase 0.7")


if __name__ == "__main__":
    main()
