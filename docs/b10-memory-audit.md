# B10 — Audit mémoire : log.md comme mémoire court-terme

## Question

> Vérifier si `log.md` (vault) suffit comme mémoire court-terme pour
> `QueryRewriterAgent` avant d'ajouter de l'infra (D14).

## Réponse

**Non — log.md ne peut pas servir de mémoire court-terme pour le
Rewriter dans son format actuel.** L'analyse ci-dessous explique
pourquoi, et ce qu'il faudrait faire pour y arriver.

## Définition de la mémoire court-terme dont le Rewriter a besoin

- **Format** : `list[dict]` avec chaque élément = `{"role": "user"|"assistant", "content": "<texte complet>"}`.
- **Usage** : passé dans le prompt LLM comme JSON, le modèle voit les échanges précédents et résout les anaphores.
- **Volume** : 5-10 paires max (sliding window, cf. `prompts-agents.md` §6 et `langgraph_orchestrator.py` ligne 99 qui lit `[-4:]` pour le contexte du Planner).

Ce format est standard OpenAI-compatible et déjà câblé dans le code :
`PipelineState.conversation_history` est passé directement à
`rewriter.rewrite()` (ligne 108) et à `generator.generate()` (ligne 158).

## Ce que log.md contient (aujourd'hui)

- **Format** : YAML append-only, clé = timestamp ISO, valeur = dict avec `query` (résumée), `agent`, `decision`, `final_score`.
- **Contenu** : un résumé décisionnel de l'évaluation, pas le texte intégral de la conversation.
- **Usage** : lint (`detecter_lacunes()`) et audit rétrospectif uniquement.

## Écarts rédhibitoires

| Critère | log.md actuel | Attendu par Rewriter |
|---------|---------------|----------------------|
| Contient le texte intégral du message utilisateur | Non (résumé) | Oui |
| Contient la réponse complète de l'assistant | Non (score/decision seulement) | Oui |
| Format exploitable comme `role`/`content` | YAML timestampé | `list[dict]` |
| Rotation / sliding window | Jamais (append-only infini) | Oui (taille bornée) |
| Appelé dans le pipeline | Jamais (`node_wiki` ne l'appelle pas) | N/A |

## Conclusion : YAGNI validé pour Redis/Mem0 — mais log.md ne ferme pas le besoin

Le **vrai mécanisme** de mémoire court-terme existe déjà et fonctionne
sans log.md ni Redis : c'est **`PipelineState.conversation_history`**,
un buffer in-memory passé de l'appelant (`run_pipeline()`, ligne 287)
jusqu'au Rewriter et au Generator.

- La mémoire est **gérée par l'appelant** (l'endpoint `/api/v1/query`
  ou tout client qui invoque `run_pipeline()`).
- Aucune infrastructure supplémentaire (Redis, Mem0) n'est nécessaire
  pour la v1 — le buffer in-memory suffit pour une session unique.
- `log.md` reste un **audit trail** post-hoc, pas une mémoire de
  conversation.

### Cas où log.md ne suffit pas et où Redis serait justifié

1. **Session persistante entre re-déploiements** : si le conteneur API
   redémarre, `conversation_history` est perdu. Un Redis AOF le
   conserverait.
2. **Requêtes concurrentes** : si un même client lance 2 pipelines en
   parallèle, le buffer in-memory n'est pas isolé correctement sans clé
   de session.
3. **Lecture du log.md par le Rewriter** : même si on écrivait
   `conversation_history` dans `log.md`, la relecture inverse (YAML →
   `list[dict]`) n'est pas implémentée et ajouterait une latence I/O à
   chaque requête.

### Recommandation

| Situation | Solution | Priorité |
|-----------|----------|----------|
| Session unique, API stable | `conversation_history` in-memory (déjà fait) | Aujourd'hui |
| Cross-session (après restart) | Redis AOF (B12, différé) | Phase C/D |
| log.md comme audit trail | Écrire `append_log()` dans `node_wiki` (B10.1, coût ~5 lignes) | B10.1 |
| log.md comme mémoire Rewriter | Déconseillé : format incompatible + latence I/O + pas de sliding window natif | **NON** |

## Actions immédiates

1. **Ne pas ajouter Redis/Mem0** (YAGNI/D14 confirmé — B12 différé).
2. **Câbler `append_log`** dans `node_wiki` de l'orchestrateur (B10.1)
   pour que le log serve au moins à l'audit — coût quasi nul, résout
   le gap "log jamais écrit".
3. **Documenter** que `conversation_history` est la responsabilité de
   l'appelant de `run_pipeline()` (API endpoint ou test) — pas du
   pipeline lui-même.
4. Marquer B10 comme **terminé** (audit fait), ajouter B10.1 comme
   micro-tâche séparée.

## Fichiers inspectés

- `src/agents/rewriter.py` : signature `rewrite(original_query, conversation_history)` — attend `list[dict]`.
- `src/agents/langgraph_orchestrator.py` : `PipelineState.conversation_history`, `node_rewrite`, `run_pipeline()`.
- `src/agents/wiki_agent.py` : `append_log()` — existe, testé, jamais appelé.
- `docs/prompts-agents.md` §6 : spécification prompt Rewriter avec few-shots montrant le format exact.