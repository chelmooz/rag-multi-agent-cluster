# Roadmap

État réel au 30/07/2026 : squelette FastAPI fonctionnel (6 agents stubés, config Pydantic, tests unitaires verts, 38 commits). Les cases cochées ci-dessous concernent la documentation et l'infrastructure existante.

**Alignement OKF v0.2** : Frontmatter wiki migré vers format OKF v0.2 (type obligatoire, verified/trust tier, status/stale_after, sources enrichis). CLI `okf` + plugin Obsidian `okf-enforcer` identifiés pour lint futur — pas de dépendance dure tant que pré-1.0.

## Documentation
- [x] README consolidé (architecture, infra, stack, guide d'installation, intégration Obsidian Vault)
- [x] Schéma d'architecture (`docs/architecture.md`, Mermaid)
- [ ] Documentation API (OpenAPI/Swagger)
- [ ] Tutoriel d'installation pas-à-pas testé de bout en bout
- [ ] **Template OKF `docs/claude-md-template.md` → `/data/wiki/CLAUDE.md`** (frontmatter OKF v0.2)
- [ ] **Script `scripts/okf-lint.py` : validation frontmatter OKF + détection stale/orphelins/contradictions** (remplace/partiel `/api/v1/lint`)

## Infrastructure
- [ ] Trancher Debian Testing/Sid vs antiX-26 pour le nœud BC-250 (antiX déjà en place selon les notes de Michel — vérifier que Mesa 25.1.3+ y est disponible avant d'exécuter le script tel quel)
- [ ] Tester `infrastructure/bc250/setup-vulkan-stack.sh` sur le matériel réel (script de référence non validé)
- [ ] Tester `infrastructure/bc250/enable-40cu-unlock.sh`, lancer `cu_map.sh` en premier pour vérifier le harvest pattern du board
- [ ] Vérifier après reboot que `ttm.pages_limit` tient à 4194304 (piège documenté : `systemd-tmpfiles` peut l'écraser après boot)
- [ ] Script `infrastructure/proxmox/create-lxc-master.sh`
- [ ] Script `infrastructure/proxmox/create-lxc-gpu.sh`
- [ ] `infrastructure/docker/docker-compose.orchestrator.yml` (complet : nginx + FastAPI + LangGraph + Wiki Agent)
- [ ] `infrastructure/docker/docker-compose.vector-db.yml` (**Qdrant** — pas Chroma)
- [ ] **Script `infrastructure/proxmox/create-lxc-wiki-agent.sh` (LXC 100 complet)**
- [ ] **3 Dockerfiles : `Dockerfile.api`, `Dockerfile.wiki-agent`, `Dockerfile.langgraph` + `nginx.conf`**

## Backend RAG
- [ ] Pipeline RAG de base (chunking, embedding, indexation)
- [ ] Recherche hybride (lexicale + vectorielle)
- [ ] Reranking
- [ ] Choix orchestrateur d'agents : CrewAI vs LangGraph → **LangGraph tranché**
- [ ] Agents Juge / Avocat du diable / Évaluateur
- [ ] Endpoint `/api/v1/query` (+ versioning `/api/v1/`)
- [ ] Actions WikiTools (read_page, write_page, append_log, update_index, lint)
- [ ] **Endpoints OKF : `/api/v1/okf/validate`, `/api/v1/okf/list`, `/api/v1/okf/show`** (wrappers CLI `okf`)
- [ ] **Endpoint `/api/v1/embed` : bge-m3 dense+sparse unifié + fallback histogramme** (OK → README)
- [ ] **Health checks `/health` + `/ready` sur CHAQUE service → Prometheus scrape dès Phase 0**

## Intégration Obsidian Vault (pattern Karpathy)
- [ ] Bind mount vault partagé (NFS/SMB entre LXC 100 et client)
- [ ] Structure vault : index.md, log.md, entities/, concepts/, sources/, synthesis/
- [ ] Workflow ingestion : source → pages wiki (avec évaluation multi-agents)
- [ ] Workflow query : question → recherche wiki → synthèse avec citations
- [ ] Workflow lint : détection contradictions, orphelins, gaps
- [ ] **Structure OKF : `index.md` (catalogue §8) + `log.md` (chronologie §9) + frontmatter validé**
- [ ] **Concurrency lock vault Obsidian** : NFS `no_root_squash` + `fcntl` locking OU git sidecar auto-commit

## Sécurité
- [x] **Filtre anti-injection Niveau 1 (regex)** : `src/tools/injection_filter.py`, scanne les chunks à l'ingestion, score `injection_risk` en métadonnée (ne bloque pas — la quarantaine passe par le trust tier OKF). Testé (`tests/test_injection_filter.py`, 12 payloads type OWASP LLM01 + faux positifs) — **GREEN**. Limite connue : heuristique regex, contournable par paraphrase/encodage/autre langue.
- [ ] **MCP (Model Context Protocol)** — différé : dépend de WikiAgent concret + mTLS (Phase 0.13). Pas de date cible.

## Fonctionnalités futures
- [ ] Text-to-SQL sur le nœud BC250
- [ ] Dashboard Grafana (tokens/sec par nœud)
- [ ] Mémoire long-terme distribuée
- [ ] Benchmarks comparatifs RTX 4000 vs BC250
- [ ] Support modèles vision (LLaVA)

## Divers à ne pas oublier avant publication GitHub
- [ ] Renseigner l'email de contact dans le README (placeholder actuel à remplacer)
- [ ] Vérifier qu'aucune IP ou mot de passe n'est codé en dur (utiliser `.env`)
- [ ] **Ajouter les tests avant tout premier merge sur `main`** → `scripts/smoke_test_frontend_api.py` (32 scénarios)
- [ ] **Secrets management** : `sops` + `.env.encrypted` ou HashiCorp Vault (Phase 7)
- [ ] **mTLS API interne** : certs auto-signés via pfSense CA (Phase 0.13 — bloquant prod)
- [ ] **Backup Qdrant** : `qdrant snapshot create` cron quotidien → stocké sur M2 (64GB dispo)
- [ ] **Runbooks incidents** : "BC250 ne boot plus", "RTX 4000 OOM", "NFS stale handle", "Qdrant corruption"
- [ ] **Load testing pré-prod** : `hey` / `locust` sur `/api/v1/query` 10-50 RPS
- [ ] **Kernel upgrade hook BC250** : script `rebuild-cu-unlock.sh` déclenché par `apt` hook `kernel-postinst` + `dracut -f`
- [ ] **Ollama model unload séquentiel** : implémenter dans `services/agents/judge.py` + `advocate.py` avec healthcheck VRAM

## Phase 0 — Squelette & Config (FONDATIONS — à faire AVANT tout code métier)
- [ ] 0.1 Structure `src/` complète (agents, tools, core, api, services)
- [ ] 0.2 Config centralisée `.env` + `settings.py` (Pydantic Settings) — **single source of truth**
- [ ] 0.3 Docker Compose VectorDB (**Qdrant** + PostgreSQL + Redis) — **aligner sur README (pas Chroma)**
- [ ] 0.4 Docker Compose Orchestrator (FastAPI + LangGraph workers + Wiki Agent + nginx)
- [ ] 0.5 Scripts Proxmox LXC (master + GPU passthrough RTX 4000)
- [ ] 0.6 **Créer `docs/claude-md-template.md` → template CLAUDE.md pour wiki (frontmatter OKF v0.2)**
- [ ] 0.7 **Créer `scripts/okf-lint.py` : validation frontmatter OKF + détection stale/orphelins/contradictions**
- [ ] 0.8 **Endpoints OKF wrapper : `/api/v1/okf/validate`, `/api/v1/okf/list`, `/api/v1/okf/show`**
- [ ] 0.9 Créer `infrastructure/proxmox/create-lxc-wiki-agent.sh` (LXC 100 complet)
- [ ] 0.10 Créer `infrastructure/docker/orchestrator.yml` + `nginx.conf` + 3 Dockerfiles
- [ ] 0.11 Intégrer healthchecks Ollama M1/M2/M3 dans wiki-agent (retry + fallback)
- [ ] 0.12 Test d'ingestion bout-en-bout : source → embed M1 → index Qdrant → wiki pages → index.md/log.md
- [ ] 0.13 **Configurer mTLS pour API interne (certs auto-signés via pfSense CA) — BLOQUANT PROD**
- [ ] 0.14 **Prometheus exporter custom wiki-agent** (metrics: `wiki_pages_total`, `ingest_duration_seconds`, `query_latency_seconds`, `llm_calls_total`)
- [ ] 0.15 **Git sidecar auto-commit dans LXC 100** (cron 1h) pour versioning wiki hors OMV
- [ ] 0.16 **Secrets management** : `sops` + `.env.encrypted` ou HashiCorp Vault (Phase 7) — **pas de CHANGE_ME en prod**
- [ ] 0.17 **Health checks obligatoires** : `/health` + `/ready` sur CHAQUE service Docker → Prometheus scrape dès Phase 0
- [ ] 0.18 **Script `scripts/smoke_test_frontend_api.py`** (32 scénarios) — CI le fait échouer tant que non implémenté
- [ ] 0.19 **API Versioning** : stratégie URL path `/api/v1/` + header `Accept` dès Phase 1.5
- [ ] 0.20 **Concurrency lock vault Obsidian** : NFS `no_root_squash` + `fcntl` locking OU git sidecar (voir 0.15)
- [ ] 0.21 **Backup Qdrant** : `qdrant snapshot create` cron quotidien → stocké sur M2 (64GB dispo)
- [ ] 0.22 **Runbooks incidents** : "BC250 ne boot plus", "RTX 4000 OOM", "NFS stale handle", "Qdrant corruption"
- [ ] 0.23 **Kernel upgrade hook BC250** : script `rebuild-cu-unlock.sh` déclenché par `apt` hook `kernel-postinst` + `dracut -f`
- [x] 0.24 **BC250 config centralisée** : 15 variables dans `settings.py` + `.env.example` (CU count, core unlock, TTM, governor, GRUB triplet, Mesa, kernel, scripts paths)

---

## 📋 Sprints d'implémentation — Proposition pré-déploiement (31/07/2026)

> **Note** : Ces sprints sont proposés pour consultation tierce. Voir `backlog.md` section "Consultation Tierce" pour les 8 questions Q1–Q8 nécessitant arbitrage avant exécution.

### Sprint 1 — Hygiène & CI (bloquant, ~2-4h)
- [ ] 1.1 Fix `.gitignore` : `models/` → `/models/`
- [ ] 1.2 Créer `.gitattributes` (eol=lf) + `git add --renormalize .`
- [ ] 1.3 Fix `pyproject.toml` : `python_version = "3.12"` + `pydantic.mypy` plugin + override asyncpg
- [ ] 1.4 Fix `src/tools/injection_filter.py` : pattern `forget` + `StrEnum` + newline final
- [ ] 1.5 Déplacer test → `tests/test_injection_filter.py`, supprimer doublons racine (`injection_filter.py`, `test_injection_filter.py`)
- [ ] 1.6 Fix `ruff` sur tout le repo (line length, unused imports, StrEnum)
- **Gate** : `ruff check .` → 0, `mypy src` → 0 bloquantes, `pytest` → 19+ passed

### Sprint 2 — Sécurité API (après Sprint 1, ~3-5h)
- [ ] 2.1 Settings : `api_key`, `api_key_header`, `cors_allow_origins` + `MissingApiKeyConfigError`
- [ ] 2.2 Middleware `require_api_key` dans `main.py` (protège `/query`, `/ingest`, `/embed`, `/okf/*`, `/lint`)
- [ ] 2.3 Fix CORS : `allow_origins=settings.cors_allow_origins` + retirer `allow_credentials=True` si wildcard
- [ ] 2.4 Annotations retour `lifespan` + `not_implemented_handler` (mypy clean)
- [ ] 2.5 Rate limiting nginx : `limit_req_zone` + `limit_req` sur `/api/v1/`
- **Gate** : `pytest tests/test_api.py` → 200 health/ready, 401 sans key ; `nginx -t` valide ; `mypy src/api/main.py` → 0

### Sprint 3 — CI & Secrets (parallélisable Sprint 2, ~2-3h)
- [ ] 3.1 Créer `.github/workflows/ci.yml` (ruff + mypy + pytest + build docker)
- [ ] 3.2 `.env.example` : ajouter `API_KEY`, `API_KEY_HEADER`, `CORS_ALLOW_ORIGINS`
- [ ] 3.3 Secrets management stub : `sops` + `.env.encrypted` (Phase 7)
- **Gate** : Push → GitHub Actions vert ; diff `.env.example` cohérent

### Sprint 4 — Agents & Pipeline (cœur métier, ~2-3 jours)
- [ ] 4.1 `VectorService.hybrid_search` + `upsert_points` + `create_collection`
- [ ] 4.2 `OllamaClient` (generate, embed, rerank, unload_model)
- [ ] 4.3 `WikiAgent` : write_page, update_index, append_log, lint, validate_frontmatter
- [ ] 4.4 `langgraph_orchestrator.build_graph()` complet
- [ ] 4.5-4.8 Judge, Advocate, Generator, Evaluator implémentations réelles
- **Gate** : Smoke test flux complet M1→M3→M2→M1

### Sprint 5 — MCP + Injection N2/N3 (optionnel, après Sprint 4.3)
- [ ] 5.1 Serveur MCP (`src/mcp/server.py`) 7 tools WikiAgent
- [ ] 5.2 Dockerfile MCP + service `orchestrator.yml` + route nginx `/mcp/`
- [ ] 5.3 mTLS sur `/mcp/` (Phase 0.13)
- [ ] 5.4 Niveau 2 : Classifieur ML léger (optionnel, Q7)
- [ ] 5.5 Niveau 3 : Quarantaine trust tiers OKF (`injection_flagged` + `lint()` priorité)

---

## Dépendances entre sprints

```
Sprint 1 (Hygiène/CI)
    ↓ (requis)
Sprint 2 (Sécurité API) ←→ Sprint 3 (CI/Secrets) [parallélisables]
    ↓
Sprint 4 (Agents/Pipeline) — cœur métier
    ↓ (requis pour Sprint 5.1)
Sprint 5 (MCP + Injection N2/N3) [optionnel]
```

---