# Roadmap — Cluster RAG Multi-Agents (Plan 3 Sprints)

## Sprint 1 — Hygiène & CI (fondations propres)

| # | Tâche | Fichiers |
|---|-------|----------|
| 1.1 | Fix `.gitignore` : `models/` → `/models/` | `.gitignore` |
| 1.2 | Créer `.gitattributes` (eol=lf) + `git add --renormalize .` | `.gitattributes` |
| 1.3 | Supprimer dossier corrompu `src/{api\` | `src/` |
| 1.4 | Fix `pyproject.toml` : `python_version = "3.12"` + `pydantic.mypy` plugin + override asyncpg | `pyproject.toml` |
| 1.5 | Vérifier/corriger `injection_filter.py` : pattern `forget` + newline final | `src/tools/injection_filter.py` |
| 1.6 | Déplacer doublon `test_injection_filter.py` racine → `tests/` (si présent) | `tests/` |
| 1.7 | `ruff check .` → 0 erreurs | tout le repo |
| 1.8 | `mypy src` → 0 bloquantes | `src/` |
| 1.9 | Corriger IPs `.env.example` : `10.10.0.1` → `10.10.0.101` (Qdrant/Postgres/Redis) | `.env.example` |
| 1.10 | Ajouter volume NFS `/data/shared` dans `docker-compose.orchestrator.yml` | `infrastructure/docker/` |
| 1.11 | Créer LXC 105 OMV (update create-lxc-gpu.sh) | `infrastructure/proxmox/` |
| 1.12 | Déployer OMV via Docker dans LXC 105 (docker-compose.omv.yml) | `infrastructure/docker/` |
| 1.13 | Configurer passthrough HDD 2TB vers LXC 105 `/srv/backup` | `infrastructure/proxmox/` |
| 1.14 | Configurer borg repo HDD + clés SSH OMV→M1/M3 | `infrastructure/backup/` |

## Sprint 2 — Backend métier (cœur du projet)

| # | Tâche | Fichiers |
|---|-------|----------|
| 2.1 | `OllamaClient` complet (generate, embed, unload, health) | `src/services/ollama.py` |
| 2.2 | `VectorService` : hybrid_search + upsert + create_collection | `src/services/vector.py` |
| 2.3 | `WikiAgent` : write_page, update_index, append_log, validate_frontmatter | `src/agents/wiki_agent.py` |
| 2.4 | `okf-lint.py` : validation frontmatter OKF v0.2 + détection stale/orphelins | `scripts/okf_lint.py` |
| 2.5 | Endpoints `/api/v1/embed`, `/api/v1/ingest`, `/api/v1/lint` | `src/api/main.py` |
| 2.6 | Endpoints OKF : `/api/v1/okf/validate`, `/list`, `/show` | `src/api/main.py` |
| 2.7 | `Generator`, `Judge`, `Advocate`, `Evaluator` — pipeline multi-agents | `src/agents/*.py` |
| 2.8 | `build_graph()` complet dans LangGraph orchestrator | `src/agents/langgraph_orchestrator.py` |

## Sprint 3 — Finalisation & Tests

| # | Tâche | Fichiers |
|---|-------|----------|
| 3.1 | Créer `.github/workflows/ci.yml` (ruff + mypy + pytest) | `.github/workflows/` |
| 3.2 | Tests d'intégration : Judge → Advocate → Evaluator séquentiel | `tests/` |
| 3.3 | Template `CLAUDE.md` OKF v0.2 | `docs/` |
| 3.4 | Auditer `README.md` + `docs/` → supprimer mentions superflues (nginx, API key, mTLS) | `README.md`, `docs/` |
| 3.5 | Merge → `main` |

## Dépendances

```
Sprint 1 (Hygiène/CI) ──bloquant──► Sprint 2 (Backend métier) ──► Sprint 3 (Finalisation)
```

## Contexte (31/07/2026)

- **Pré-développement** : réflexion sur les actions à mener, pas encore de code métier.
- **Localhost / LAN uniquement** : les IA sont locales (Ollama), pfSense = périmètre de sécurité.
- **Pas d'API key** : pull des modèles fait, pas besoin d'auth applicative.
- **nginx = sur-ingénierie** : pfSense suffit comme reverse proxy/protection. À retirer du stack.
- **Revoir `README.md` + diagrammes Mermaid** : retirer nginx, API key, mTLS, CORS restrictif.