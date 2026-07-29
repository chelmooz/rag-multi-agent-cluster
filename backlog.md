# Backlog — Cluster RAG Multi-Agents

## Phase 0 — Squelette & Config
- [ ] 0.1 Structure `src/` complète (agents, tools, core, api, services)
- [ ] 0.2 Config centralisée `.env` + `settings.py` (Pydantic Settings)
- [ ] 0.3 Docker Compose VectorDB (Qdrant + PostgreSQL + Redis)
- [ ] 0.4 Docker Compose Orchestrator (FastAPI + workers)
- [ ] 0.5 Scripts Proxmox LXC (master + GPU passthrough RTX 4000)

## Phase 1 — Pipeline RAG Core (Master LXC 100-101)
- [ ] 1.1 Ingestion Service (chunking, augmentation, embedding sur Machine 2 CPU)
- [ ] 1.2 VectorService (Qdrant client, hybrid search)
- [ ] 1.3 LexicalSearch (BM25 via Qdrant sparse)
- [ ] 1.4 Reranker (bge-reranker-v2-m3 sur RTX 4000 - Machine 2)
- [ ] 1.5 API Endpoints (/ingest, /query OpenAI-compat)

## Phase 2 — Orchestrateur & Planificateur (LXC 100 - Machine 1)
- [ ] 2.1 Orchestrator (flux principal)
- [ ] 2.2 Planner (intention + stratégie)
- [ ] 2.3 QueryRewriter (réécriture conversationnelle)
- [ ] 2.4 ContextAssembler (chunks + savoir interne + fenêtre)
- [ ] 2.5 HTTP Client Pool (httpx avec retry/circuit-breaker)

## Phase 3 — Génération + Évaluation Multi-Agents
- [ ] 3.1 Generator (qwen3.5:14b Q4_K_M ou qwen3.5-35b-a3b IQ2_M sur BC250 Vulkan)
- [ ] 3.2 Judge (qwen3.5:7b Q4_K_M sur RTX 4000 - Machine 2 LXC 200)
- [ ] 3.3 Devil's Advocate (mistral-small-3.2:7b Q4_K_M sur RTX 4000 - Machine 2 LXC 201)
- [ ] 3.4 Evaluator (qwen3.5:3b / granite-3.2:2b Q4_K_M sur Machine 1 CPU)

## Phase 4 — Wiki Persistant (Pattern Karpathy)
- [ ] 4.1 WikiTools (read/write/append/index/log via vault Obsidian)
- [ ] 4.2 IngestAgent (source → pages wiki + index.md + log.md)
- [ ] 4.3 Schema AGENTS.md (conventions nommage, frontmatter, structure)
- [ ] 4.4 Endpoint /api/v1/ingest

## Phase 5 — Variantes Avancées
- [ ] 5.1 Text-to-SQL (BC250, qwen3-coder-30b-a3b IQ2_M, contexte 64k)
- [ ] 5.2 Vision (BC250, llava-next:13b / qwen2.5-vl Q4_K_M)
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

## Infrastructure Matérielle Validée (selon README.md)

| Nœud | Rôle | CPU / RAM | GPU / Accélérateur | Virtualisation |
| :--- | :--- | :--- | :--- | :--- |
| **Machine 1** | **Master** (Orchestration, API, VectorDB, Monitoring, Evaluator) | 2× Xeon E5-2699 v4 / **32 GB ECC** | **AMD Radeon RX 580** (8 GB) | Proxmox VE 9.3 (LXC 100, 101, 102, 103) |
| **Machine 2** | **GPU Worker** (Reranker, Judge, Avocat, Embedding batch CPU) | 1× Xeon E5-2698 v4 / **64 GB ECC** | **NVIDIA Quadro RTX 4000** (8 GB VRAM) | Proxmox VE 9.3 (LXC 200 privilégié GPU, 201) |
| **Machine 3** | **BC250 Baremetal** (Generator, Text-to-SQL, Vision, Granite fast-check) | Zen 2 6c/12t / **16 GB GDDR6 unifiée** | **Intégré - Vulkan ONLY** (40 CU unlocked) | Debian Testing/Sid baremetal (Ollama Vulkan natif) |

## Modèles Recommandés par Machine (29/07/2026 - validé échange)

### Machine 1 — Master (32GB ECC, RX 580)
| Rôle | Modèle | Quant | Raison |
|------|--------|-------|--------|
| **Embedding principal** | `nomic-embed-text-v2-moe` (768d) | Q8_0 (CPU) | Xeon 32c/64t idle, batch offline |
| **Évaluateur 3B** | `qwen3.5:3b` / `granite-3.2:2b` | Q4_K_M | Léger, CPU-only, synthèse + décision |
| **Monitoring/fallback** | `qwen2.5:3b` | Q4_K_M | Alertes, log summarization basique |

### Machine 2 — GPU Worker (64GB ECC, RTX 4000 8GB VRAM, Xeon 2698 v4 20c/40t)
| Rôle | Modèle | Quant | VRAM estimée | Raison |
|------|--------|-------|--------------|--------|
| **Reranker** | `bge-reranker-v2-m3` | Q4_K_M | ~4-6 GB | Tient dans RTX 4000 |
| **Judge** | `qwen3.5:7b` | Q4_K_M | ~5 GB | Éval qualité, fort raisonnement |
| **Avocat du diable** | `mistral-small-3.2:7b` | Q4_K_M | ~5 GB | Approche différente → diversité |
| **Embedding batch (backup)** | `nomic-embed-text-v2-moe` | Q8_0 (CPU) | - | 64GB RAM + 40 threads inutilisés si Machine 1 saturée |

> **Note** : 64GB ECC permet de charger **tous les buffers simultanément** (reranker + judge + avocat + ingestion) sans swap.

### Machine 3 — BC250 Baremetal (16GB GDDR6 unifiée, Vulkan-only, 40 CU unlocked)
| Rôle | Modèle | Quant | Raison |
|------|--------|-------|--------|
| **Generator principal** | `qwen3.5:14b` (dense) | Q4_K_M | ~9 GB, 40 CU → ~30 tok/s |
| **Generator alternatif (qualité)** | `qwen3.5-35b-a3b` (MoE) | IQ2_M | ~11 GB, 40 CU → ~78 tok/s (llama.cpp direct) |
| **Text-to-SQL / Code** | `qwen3-coder-30b-a3b` (MoE) | IQ2_M | 3B actifs, 64k contexte, français |
| **Vision (Phase 5.2)** | `llava-next:13b` / `qwen2.5-vl` | Q4_K_M | Même contrainte que Generator 14B |
| **Fast-check lexical skill** | `granite-4.0-h-tiny` (3.4B hybrid Mamba) | Q4_K_M | 40 CU → **129 tok/s**, 128K+ contexte |

---

## Décisions d'architecture (à trancher)

### 29/07/2026 — Embedding sur CPU vs BC250 — **TRANCHÉ**

**Constat** : Le pipeline d'ingestion (chunking → augmentation → embedding → indexation) est un workflow **offline, asynchrone** — pas dans le chemin critique des requêtes utilisateur. Une fois l'ingestion faite, les données existent sous trois formes dans la base :
1. Index lexical (BM25 sparse via Qdrant)
2. Index vectoriel (embeddings 768d)
3. Métadonnées augmentées (contexte, tags, sources)

La latence d'embedding pendant l'ingestion n'impacte donc **aucun utilisateur**. Même un embedding CPU lent (50-100ms/chunk sur Xeon) est acceptable pour un batch job.

**Problème** : La version précédente envisageait d'allouer le BC250 (seul GPU > 8 GB) à l'embedding, ce qui est un **contresens technique**.

#### Démonstration par chaîne de contraintes

**1. Generator 14B n'a qu'un seul hôte possible**

Le modèle critique est Qwen2.5-14B (Phase 3.1). Même en Q4_K_M :
- BC250 (16GB unifié) : ✅ ~12-14 GB dispo → tient
- RTX 4000 (8GB VRAM dédiée) : ❌ pas assez
- Master (0 GPU) : ❌ pas de GPU

→ BC250 est le **seul** hôte capable de faire tourner le Generator 14B.

**2. BC250 = mémoire unifiée, pas VRAM dédiée**

Le BC250 n'a **pas** de VRAM séparée. CPU et GPU partagent le même pool 16GB GDDR6 + la même bande passante mémoire (spécification AMD Cyan Skillfish). Si le CPU BC250 est chargé (embedding batch, traitement lourd) :
- **Contention bande passante mémoire** → le GPU 14B est affamé
- **Pression thermique** → CPU + GPU = jusqu'à 235W TDP dans un format compact → throttling certain
- **VRAM effective réduite** → le modèle 14B perd des ressources critiques

**3. L'embedding tient sur Master sans aucun coût**

Le Master LXC 100 a **2 × Xeon 2699** (16c/32t chacun, 32GB ECC) contre 6c/12t Zen 2 sur BC250 :
- Les Xeon sont **inutilisés** pour le ML (Master n'a pas de GPU)
- L'ingestion est **offline** → pas d'impact latence
- **Aucune contention mémoire** possible (RAM ECC séparée)

**4. Synthèse des placements (version enrichie 29/07/2026)**

| Charge | Contrainte critique | Placement final | Raison |
|--------|---------------------|-----------------|--------|
| Generator 14B / MoE 35B | ≥12 GB VRAM, Vulkan | **BC250 GPU (Machine 3)** | Seul hôte possible (RTX 4000 = 8GB, Master = 0 GPU) |
| Embedding nomic (principal) | CPU-only, batch offline | **Machine 1 (Master LXC 100)** | 2× Xeon 2699 32c/64t idle, 0 contention |
| Embedding nomic (backup) | CPU-only, batch offline | **Machine 2 (GPU Worker LXC 200/201)** | Xeon 2698 v4 20c/40t + 64GB ECC inutilisés |
| Reranker bge | GPU 4-6 GB, VRAM dédiée | **Machine 2 - RTX 4000 (LXC 200)** | Pas de partage mémoire |
| Judge 7B | GPU 5 GB, VRAM dédiée | **Machine 2 - RTX 4000 (LXC 200)** | Évaluation qualité |
| Avocat du diable 7B | GPU 5 GB, VRAM dédiée | **Machine 2 - RTX 4000 (LXC 201)** | Parallèle au Judge, diversité |
| Évaluateur 3B | CPU-only, léger | **Machine 1 (Master LXC 100)** | Xeon idle, pas de GPU nécessaire |
| Text-to-SQL / Vision / Granite | ≥12 GB, Vulkan | **BC250 GPU (Machine 3)** | Même contrainte que Generator, 40 CU unlock |

**5. Règle d'or pour le BC250 (confirmée docs communautaires)**

> **Le CPU du BC250 est le serviteur du GPU.** Toute charge CPU significative sur BC250 est un vol de bande passante mémoire au Generator 14B. Le CPU BC250 (Zen 2 6c/12t) doit rester au repos (ou charge minimale) quand le GPU fait de l'inférence Vulkan.

**Références** :
- [AMD BC250 Documentation](https://elektricm.github.io/amd-bc250-docs/) — Unified Memory Architecture, Vulkan-only, 40 CU unlock
- [akandr/bc250](https://github.com/akandr/bc250) — Ollama + Vulkan benchmarks, GFX1013 specifics, roofline analysis

→ **Décision** : Embedding sur **Machine 1 Master LXC 100 (Xeon CPU)** via Ollama/llama.cpp CPU `nomic-embed-text-v2-moe` 768d. BC250 GPU réservé **exclusivement** au Generator 14B/MoE (Phase 3.1) et aux variantes lourdes (Phase 5 : Text-to-SQL, Vision, Granite fast-check). Machine 2 (64GB + RTX 4000) = Reranker + Judge + Avocat + backup embedding CPU.

**Actions** :
- [ ] Mettre à jour `docs/architecture.svg` — 3 machines, mapping correct des modèles
- [ ] Mettre à jour `src/core/settings.py` — variables `EMBEDDING_HOST=machine1` / `EMBEDDING_MODEL=nomic-embed-text-v2-moe` / `EMBEDDING_MODE=cpu` + endpoints GPU Worker + BC250
- [ ] Mettre à jour `services/vector.py` — configurer client embedding vers endpoint Machine 1 au lieu de BC250
- [ ] Phase 1.1 : changer "embedding BC250" → "embedding Machine 1 CPU (backup Machine 2 CPU)"
- [ ] Phase 3.1 : changer "Qwen2.5-14B sur RTX 4000" → "qwen3.5:14b Q4_K_M / qwen3.5-35b-a3b IQ2_M sur BC250 Vulkan"
- [ ] Phase 3.2/3.3 : préciser Judge sur LXC 200, Avocat sur LXC 201 (même RTX 4000, VRAM partagée 2×5GB OK)
- [ ] Phase 5.1 : préciser qwen3-coder-30b-a3b IQ2_M sur BC250
- [ ] Phase 5.2 : déplacer Vision sur BC250 (pas RTX 4000)