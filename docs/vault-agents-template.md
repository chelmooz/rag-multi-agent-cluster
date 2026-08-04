# Template AGENTS.md — vault wiki OKF v0.2

> Item backlog 0.6. Ce fichier est un **template** : la version finale doit être
> copiée à la racine du vault Obsidian (`${WIKI_VAULT_PATH}/AGENTS.md`, cf.
> `settings.wiki_vault_path`). Ce n'est pas un fichier lié à un modèle "Claude" —
> c'est un fichier de conventions pour tout agent (Wiki Agent, IngestAgent,
> Evaluator, ou un humain) qui lit ou écrit dans le vault, sur le même principe
> que l'`AGENTS.md` du dépôt de code pour opencode.

---

## Frontmatter OKF v0.2 obligatoire

Chaque page du vault DOIT porter ces 5 champs (`_OKF_REQUIRED` dans
`src/agents/wiki_agent.py`) :

```yaml
---
type: concept        # concept | entity | source | synthesis | agent | log
title: "Titre de la page"
status: draft         # draft | review | published | stale
verified: unverified  # unverified | machine-confirmed | human-reviewed
created: 2026-08-04
stale_after: 2026-11-04   # optionnel — déclenche le flag stale au lint
---
```

Valeurs autorisées (source de vérité : `src/agents/wiki_agent.py`,
`_OKF_TYPES` / `_OKF_STATUSES`) :

| Champ | Valeurs |
|---|---|
| `type` | `concept`, `entity`, `source`, `synthesis`, `agent`, `log` |
| `status` | `draft`, `review`, `published`, `stale` |
| `verified` | `unverified`, `machine-confirmed`, `human-reviewed` |

## Règle de confiance (verified_tier)

`human-reviewed` ne peut **jamais** être positionné automatiquement par un
agent. `src/agents/evaluator.py` restreint la sortie automatique de
l'Evaluator au `Literal["machine-confirmed", "unverified"]` — toute page
passée en `human-reviewed` doit l'être par une relecture humaine explicite,
jamais par le pipeline. Un agent qui écrit une page se limite donc à
`unverified` ou `machine-confirmed`.

## Structure du vault

```
${WIKI_VAULT_PATH}/
├── index.md          # point d'entrée, liens vers les sections
├── log.md            # journal des runs (append-only, type: log)
├── entities/          # type: entity
├── concepts/          # type: concept
├── sources/           # type: source
└── synthesis/         # type: synthesis — réponses générées par le pipeline
```

## Règles de nommage et sécurité

- Noms de fichiers en minuscules, tirets (`-`) comme séparateur, extension
  `.md`.
- Aucun chemin ne doit sortir du vault (anti path-traversal) : pas de `..`,
  pas de chemin absolu dans les liens `[[...]]`.
- Les liens internes utilisent le **chemin relatif complet depuis la racine du
  vault, avec l'extension `.md`** — `[[concepts/mon-concept.md]]`, pas
  `[[mon-concept]]`. C'est la convention Obsidian standard (`[[nom-de-page]]`
  sans chemin) qui NE s'applique PAS ici : `WikiAgent.update_index()` et le
  détecteur d'orphelins de `lint()` comparent tous deux `page.relative_to(vault)`
  en chaîne exacte (`f"[[{rel}]]"`, `rel` incluant le dossier et `.md`) — un
  lien écrit en syntaxe Obsidian classique ne matchera jamais et la page
  liée sera signalée orpheline à tort.

## Cycle de vie

- `stale_after` (date ISO) déclenche le statut `stale` au prochain
  `scripts/okf_lint.py --stale` une fois la date dépassée.
- `scripts/okf_lint.py` (sans flag) fait un lint complet : orphelins +
  stale + gaps + frontmatter. `--validate` ne vérifie que le frontmatter.
  `--fix` corrige automatiquement les problèmes simples.
- Le Wiki Agent (`src/agents/wiki_agent.py`, service long-running en
  conteneur Docker) exécute ce cycle de maintenance en continu
  (`WIKI_MAINTENANCE_INTERVAL`, 3600s par défaut) — pas de crash-loop (C1).

## Ce qu'un agent doit faire avant d'écrire une page

1. Vérifier que `type`/`status`/`verified` appartiennent aux valeurs
   autorisées ci-dessus.
2. Ne jamais écrire `verified: human-reviewed`.
3. Lier la page aux pages existantes pertinentes (`[[chemin/relatif/page.md]]`,
   voir convention ci-dessus) pour éviter les
   orphelins.
4. Ne pas dupliquer une page déjà indexée avec le même titre normalisé —
   consulter `index.md` avant création.
