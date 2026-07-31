# Roadmap — Cluster RAG Multi-Agents (Plan 4 Phases, mis à jour 31/07/2026)

> Stratégie de développement (décisions D10-D12, 31/07/2026) :
> **Mock-first** — aucun LLM n'est pullé avant déploiement ; toute la Phase A/B se développe et se teste avec des mocks httpx + Qdrant mocké. Le code de prod (OllamaClient, agents, endpoints) est écrit en production-ready, mais vérifié sans matériel.

```
Phase A (RAG core, mock-first) ──► Phase B (multi-agents, mock-first) ──► Phase C (déploiement hardware) ──► Phase D (CI/finalisation)
```

## Phase A — Pipeline RAG Core (Sprint 2 partie 1 — Hybrid Search)

| # | Tâche | Fichiers |
|---|-------|----------|
| A1 | `OllamaClient` complet (generate, embed, rerank, unload, health + retry/circuit-breaker) — testable via `httpx.MockTransport` | `src/services/ollama.py` |
| A2 | `OllamaClientPool` routing intelligent M1/M2/M3 selon rôle (embed→M1 fallback M2, generate→M3, rerank/judge/advocate→M2, evaluate→M1) | `src/services/ollama.py` |
| A3 | `VectorService` : create_collection (dense 768d + sparse BM25), upsert, hybrid_search, snapshot | `src/services/vector.py` |
| A4 | `IngestionService` : chunking tiktoken, augmentation, embedding batch → Qdrant | `src/services/ingestion.py` |
| A5 | `LexicalSearch` helper : sparse vectors BM25 via Qdrant natif | `src/services/lexical.py` |
| A6 | `RerankerService` : bge-reranker-v2-m3 via Ollama M2 | `src/services/reranker.py` |
| A7 | Endpoints `/api/v1/embed`, `/api/v1/ingest`, `/api/v1/query` (hybrid search) — remplacent les stubs `NotImplementedError` | `src/api/main.py` |
| A8 | Tests d'intégration hybrid search bout-en-bout (mocks) | `tests/test_hybrid_search.py` |

## Phase B — Pipeline Multi-Agents (Sprint 2 partie 2)

| # | Tâche | Fichiers |
|---|-------|----------|
| B1 | `PlannerAgent` : analyse intention + stratégie (outils, variantes SQL/Vision) | `src/agents/planner.py` |
| B2 | `QueryRewriterAgent` : réécriture conversationnelle avec historique | `src/agents/query_rewriter.py` |
| B3 | `ContextAssembler` : fusion chunks rerankés + savoir interne + fenêtre courte | `src/agents/context_assembler.py` |
| B4 | `WikiAgent` : write_page, update_index, append_log, validate_frontmatter, lint | `src/agents/wiki_agent.py` |
| B5 | `Generator` (M3), `Judge` (M2), `Advocate` (M2), `Evaluator` (M1) — pipeline séquentiel via relay.json | `src/agents/*.py` |
| B6 | Boucle d'évaluation **optionnelle** : flag `evaluation_enabled` (défaut OFF, D12) — 1 itération max de feedback Évaluateur → Planner | `src/core/settings.py`, `src/agents/langgraph_orchestrator.py` |
| B7 | `build_graph()` complet dans LangGraph (Planner → Rewriter → HybridSearch → Reranker → ContextAssembler → Generator → [Éval] → WikiUpdate) | `src/agents/langgraph_orchestrator.py` |
| B8 | Endpoints OKF : `/api/v1/okf/validate`, `/list`, `/show` + `/api/v1/lint` + `okf-lint.py` | `src/api/main.py`, `scripts/okf_lint.py` |
| B9 | Tests d'intégration séquentiels (relay mocké, LLM mocké) + smoke 32 scénarios mis à jour (plus de 500 NIE) | `tests/`, `scripts/smoke_test_frontend_api.py` |

## Phase C — Déploiement & Validation Hardware (bloquée : 3 machines à livrer)

| # | Tâche | Fichiers |
|---|-------|----------|
| C1 | Dockerfiles/CMD idempotents (fin du crash-loop : plus d'appel à des stubs NIE au boot) | `infrastructure/docker/*.yml`, `Dockerfile.*` |
| C2 | Volume NFS `/data/shared` dans `docker-compose.orchestrator.yml` | `infrastructure/docker/` |
| C3 | Déployer OMV dans LXC 105 (docker-compose.omv.yml + passthrough HDD 2TB + borg) | `infrastructure/docker/`, `infrastructure/proxmox/` |
| C4 | Pull des modèles (Ollama M1/M2/M3) + lock digests SHA256 dans `.env` | `.env`, docs |
| C4.1 | Résolution Hugging Face exclusive (hf.co/...) pour Générateur (Qwen3-14B), Juge (DeepSeek-R1-Distill-Llama-8B), Avocat (Ministral-8B-2410) — cf. `docs/BRIEF-INTEGRATION-MODELES-Q4-HF.md` | `.env`, `settings.py` |
| C4.2 | Résolution HF étendue aux 7 autres modèles (embedding, reranker, évaluateur, générateur alt, text2sql, vision, fastcheck) — cf. §8 du BRIEF | `.env`, `settings.py` |
| C5 | Glances (`glances -w`) sur BC-250 uniquement (D9) | `infrastructure/bc250/` |
| C6 | Smoke tests bout-en-bout sur le cluster réel + mesure de latence (4 appels LLM si éval activée) | `scripts/smoke_test_frontend_api.py` |

## Phase D — CI & Finalisation (Sprint 3)

| # | Tâche | Fichiers |
|---|-------|----------|
| D1 | Créer `.github/workflows/ci.yml` (ruff + mypy + pytest) | `.github/workflows/` |
| D2 | Template `CLAUDE.md` OKF v0.2 | `docs/` |
| D3 | Runbooks incidents (BC250 boot, RTX OOM, NFS stale, Qdrant corruption, OMV HDD) | `docs/` |
| D4 | Audit final docs + merge → `main` | `README.md`, `docs/` |

## Dépendances

```
Phase A (RAG core) ──bloquant──► Phase B (multi-agents) ──► Phase C (hardware) ──► Phase D (CI)
```

## Contexte & Décisions (31/07/2026)

- **D10 — Mock-first** : aucun LLM pullé avant déploiement (pré-déploiement). Tout se développe avec `httpx.MockTransport` + Qdrant mocké ; les tests passent en CI sans matériel.
- **D11 — Ordre d'exécution** : Phase A (Hybrid RAG + Retrieve-and-rerank) avant Phase B (Multi-Agent RAG) — conforme au ROADMAP Sprint 2 original.
- **D12 — Évaluation optionnelle** : la boucle Judge → Advocate → Evaluator (4 appels LLM/requête) est un flag `evaluation_enabled` défaut OFF, activable par endpoint/requête — évite la latence en phase de validation.
- **D9 — Monitoring allégé** : Prometheus/Grafana/Loki (LXC 103) retirés de la v1 → graphs natifs Proxmox/pfSense + Glances BC-250.
- **D4 — nginx retiré** : pfSense (VM 104) = seul reverse proxy ; `nginx.conf`, service nginx et LXC 102 supprimés.
- **Localhost / LAN uniquement** : les IA sont locales (Ollama), pfSense = périmètre de sécurité.
- **Pas d'API key** : pull des modèles fait, pas besoin d'auth applicative.

## État Sprint 1 — Hygiène & CI ✅ TERMINÉ (31/07/2026)

| # | Tâche | Statut |
|---|-------|--------|
| 1.1 | Fix `.gitignore` (`models/`) | ✅ fait |
| 1.2 | Créer `.gitattributes` (eol=lf) | ✅ fait |
| 1.3 | Supprimer dossier corrompu `src/{api\` | ✅ fait |
| 1.4 | Fix `pyproject.toml` : mypy 3.12 + plugin `pydantic.mypy` + override asyncpg | ✅ fait |
| 1.5 | Fix `injection_filter.py` : StrEnum + newline final | ✅ fait |
| 1.6 | Déplacer doublon `test_injection_filter.py` racine → `tests/` (si présent) | ✅ fait (doublon supprimé, `src/tools/injection_filter.py` est la source) |
| 1.7 | `ruff check .` → 0 erreurs | ✅ fait |
| 1.8 | `mypy src` → 0 bloquantes | ✅ fait |
| 1.9 | Corriger IPs `.env.example` : Qdrant/Postgres/Redis → `10.10.0.101` (LXC 101) | ✅ fait |
| 1.10 | Ajouter volume NFS `/data/shared` dans compose orchestrator | ⏳ déplacé en C2 |
| 1.11 | Créer LXC 105 OMV | ⏳ déplacé en C3 |
| 1.12 | Déployer OMV via Docker (docker-compose.omv.yml) | ⏳ déplacé en C3 |
| 1.13 | Passthrough HDD 2TB → LXC 105 | ⏳ déplacé en C3 |
| 1.14 | Configurer borg repo HDD + clés SSH OMV→M1/M3 | ⏳ déplacé en C3 |

**Bonus nettoyage (session 31/07/2026)** : suppression nginx.conf/certs/ + LXC 102-103 des scripts Proxmox ; `.env.example` réécrit aligné sur `settings.py` (bug `parents[3]` → `parents[2]` corrigé : le `.env` n'était jamais lu) ; doc README/diagrams purgée (D9) ; backlog Phase 1 décocher (rien n'était livré) ; README `/api/embed` statut corrigé (stub, pas "OK").
