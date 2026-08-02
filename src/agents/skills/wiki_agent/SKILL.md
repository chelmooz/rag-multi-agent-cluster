# Skill — Wiki Agent (règles de maintenance du vault)

Rôle : boucle de maintenance continue du vault Obsidian (pattern Karpathy).
Ce skill est une **référence de règles** (pas un prompt LLM) : il décrit
les invariants que `WikiAgent.write_page/update_index/append_log/lint/
validate_frontmatter` doivent respecter.

## Frontmatter OKF v0.2 — champs obligatoires

Chaque page du vault porte un frontmatter YAML avec au minimum :

```yaml
---
type: <concept|entity|source|synthesis|agent|log>
title: <titre humain>
status: <draft|review|published>
verified: <unverified|machine-confirmed|human-reviewed>
created: <YYYY-MM-DD>
tags: [<liste>]
---
```

- `verified` : écrit UNIQUEMENT par l'Évaluateur final (`machine-confirmed`)
  ou par un humain (`human-reviewed`). Jamais automatiquement
  `human-reviewed`.
- `status` : `draft` par défaut ; passage à `review`/`published` contrôlé.
- `stale_after` (optionnel) : date après laquelle la page est marquée
  stale par `lint`.

## index.md — catalogue des pages

- `update_index()` régénère `index.md` : liste de toutes les pages
  (chemin, type, title, status, tags), triée par type puis titre.
- Une page absente du disque est retirée de l'index.

## log.md — chronologie des interactions

- `append_log(entry)` ajoute une entrée horodatée `YYYY-MM-DD HH:MM` :
  query (résumée), agent ayant répondu, decision, final_score.
- Entrées append-only : jamais réécrites, jamais supprimées.

## write_page — conventions

- Le contenu body suit le format Obsidian (wikilinks `[[...]]`).
- Ne jamais écraser une page existante sans avoir le flag `overwrite=True`
  explicite.
- Le chemin est relatif au vault (`wiki_vault_path`), normalisé
  (anti `..`/traversal).

## lint — détections

- **Pages orphelines** : aucune page ne référence `[[cette page]]`.
- **Stale** : `stale_after` dépassé → marquer `status: stale` en sortie.
- **Contradictions** : deux pages déclarant des faits contradictoires
  (détection heuristique sur les paires de pages du même type).
- **Gaps** : requêtes précédentes dont aucune page ne porte la trace
  (via log.md).
- **Frontmatter invalide** : `validate_frontmatter()` par page →
  champs manquants / type hors vocabulaire / verified illégal.

## Format de sortie

- `lint()` → dict JSON avec clés `orphans`, `stale`, `contradictions`,
  `gaps`, `frontmatter_issues`.
- `validate_frontmatter(page_path)` → dict avec `valid: bool`,
  `issues: [string]`.
