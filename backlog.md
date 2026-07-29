# Backlog — Cluster RAG Multi-Agents

## Phase 0 — Squelette & Config
- [ ] 0.1 Structure `src/` complète (agents, tools, core, api, services)
- [ ] 0.2 Config centralisée `.env` + `settings.py` (Pydantic Settings)
- [ ] 0.3 Docker Compose VectorDB (Qdrant + PostgreSQL + Redis)
- [ ] 0.4 Docker Compose Orchestrator (FastAPI + workers)
- [ ] 0.5 Scripts Proxmox LXC (master + GPU passthrough RTX 4000)

## Phase 1 — Pipeline RAG Core (Master LXC 100-101)
- [ ] 1.1 Ingestion Service (chunking, augmentation, embedding BC250)
- [ ] 1.2 VectorService (Qdrant client, hybrid search)
- [ ] 1.3 LexicalSearch (BM25 via Qdrant sparse)
- [ ] 1.4 Reranker (bge-reranker-v2-m3 sur RTX 4000)
- [ ] 1.5 API Endpoints (/ingest, /query OpenAI-compat)

## Phase 2 — Orchestrateur & Planificateur (LXC 100)
- [ ] 2.1 Orchestrator (flux principal)
- [ ] 2.2 Planner (intention + stratégie)
- [ ] 2.3 QueryRewriter (réécriture conversationnelle)
- [ ] 2.4 ContextAssembler (chunks + savoir interne + fenêtre)
- [ ] 2.5 HTTP Client Pool (httpx avec retry/circuit-breaker)

## Phase 3 — Génération + Évaluation Multi-Agents
- [ ] 3.1 Generator (Qwen2.5-14B sur RTX 4000)
- [ ] 3.2 Judge (Qwen2.5-7B/Mistral-7B sur RTX 4000 ou BC250)
- [ ] 3.3 Devil's Advocate (parallèle au Judge)
- [ ] 3.4 Evaluator (Qwen2.5-3B sur Master CPU, synthèse + décision)

## Phase 4 — Wiki Persistant (Pattern Karpathy)
- [ ] 4.1 WikiTools (read/write/append/index/log via vault Obsidian)
- [ ] 4.2 IngestAgent (source → pages wiki + index.md + log.md)
- [ ] 4.3 Schema AGENTS.md (conventions nommage, frontmatter, structure)
- [ ] 4.4 Endpoint /api/v1/ingest

## Phase 5 — Variantes Avancées
- [ ] 5.1 Text-to-SQL (BC250, Qwen2.5-Coder-14B, contexte 64k)
- [ ] 5.2 Vision (RTX 4000, LLaVA-Next/Qwen2.5-VL)
- [ ] 5.3 Graph RAG (NetworkX + entités wiki)
- [ ] 5.4 Long-term Memory (PostgreSQL conversations + feedback)

## Phase 6 — Intégration Obsidian Vault
- [ ] 6.1 Bind mount /data/wiki sur LXC 100 → partagé NFS/SMB vers client
- [ ] 6.2 Structure vault (index.md, log.md, entities/, concepts/, sources/, synthesis/)
- [ ] 6.3 Webhook file watcher (Obsidian → cluster via web clipper)

## Phase 7 — Observabilité & Hardening
- [ ] 7.1 Prometheus + Grafana (LXC 103)
- [ ] 7.2 Loki + structured logs (correlation ID)
- [ ] 7.3 Health checks agrégés
- [ ] 7.4 Tests integration (smoke_test_frontend_api.py)