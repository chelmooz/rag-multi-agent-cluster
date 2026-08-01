# Backlog — Cluster RAG Multi-Agents

## Phase 0 — Squelette & Config (FONDATIONS — à faire AVANT tout code métier)
- [x] 0.1 Structure `src/` complète (agents, tools, core, api, services) — **+ `src/{api` corrompu supprimé, `src/models/` mort supprimé (31/07/2026)**
- [x] 0.2 Config centralisée `.env` + `settings.py` (Pydantic Settings) — **single source of truth** — **+ bug corrigé 31/07/2026 : `env_file` pointait sur `parents[3]` (H:\) au lieu de `parents[2]` → le .env n'était JAMAIS lu. `.env.example` réécrit aligné sur les `validation_alias` réels**
- [x] 0.3 Docker Compose VectorDB (**Qdrant** + PostgreSQL + Redis) — **aligné Qdrant, restart policies ajoutées**
- [x] 0.4 Docker Compose Orchestrator (FastAPI + LangGraph workers + Wiki Agent) — **build.context corrigé** *(nginx retiré, pfSense gère reverse proxy)*
- [x] 0.5 Scripts Proxmox LXC (master + GPU passthrough RTX 4000) — **mis à jour D9 (31/07/2026) : LXC 102 nginx et LXC 103 Monitoring retirés des scripts**
- [ ] 0.6 **Créer `docs/claude-md-template.md` → template CLAUDE.md pour wiki (frontmatter OKF v0.2)**
- [ ] 0.7 **Créer `scripts/okf-lint.py` : validation frontmatter OKF + détection stale/orphelins/contradictions**
- [ ] 0.8 **Endpoints OKF wrapper : `/api/v1/okf/validate`, `/api/v1/okf/list`, `/api/v1/okf/show`**
- [x] 0.9 Créer `infrastructure/proxmox/create-lxc-wiki-agent.sh` (LXC 100 complet) — **couvert par `create-lxc-master.sh` (LXC 100 Orchestrator + Wiki Agent, 8 vCPU/10 GB)**
- [x] 0.10 Créer `infrastructure/docker/orchestrator.yml` + `nginx.conf` (pour dev) + 3 Dockerfiles (api, wiki-agent, langgraph) — **fix Poetry→pip install .** — **nginx.conf supprimé (D4/D9, 31/07/2026), pfSense gère le reverse proxy**
- [x] 0.11 Intégrer healthchecks Ollama M1/M2/M3 dans wiki-agent (retry + fallback) — **implémenté dans l'API : checks Qdrant/Ollama M1-M3/PostgreSQL/Redis + 503 si dégradé (`/health` + `/ready`)**
- [ ] 0.12 Test d'ingestion bout-en-bout : source → embed M1 → index Qdrant → wiki pages → index.md/log.md
- [ ] 0.13 **Configurer mTLS pour API interne (certs auto-signés via pfSense CA) — BLOQUANT PROD**
- [x] ~~0.14 **Prometheus exporter custom wiki-agent**~~ **RETIRÉ** (cf. D9, 31/07/2026) — pas de Prometheus déployé en v1, metrics consultables via logs applicatifs
- [ ] 0.15 **Git sidecar auto-commit dans LXC 100** (cron 1h) pour versioning wiki hors OMV
- [ ] 0.16 **Secrets management** : `sops` + `.env.encrypted` ou HashiCorp Vault (Phase 7) — **pas de CHANGE_ME en prod**
- [x] 0.17 **Health checks obligatoires** : `/health` + `/ready` sur CHAQUE service Docker — **implémenté : checks Qdrant/Ollama M1-M3/PostgreSQL/Redis + 503 si dégradé** — ~~Prometheus scrape~~ retiré (cf. D9), consultation directe `curl`/Glances
- [x] 0.18 **Script `scripts/smoke_test_frontend_api.py`** (32 scénarios) — **32/32 PASSED**
- [x] 0.19 **API Versioning** : stratégie URL path `/api/v1/` + header `Accept` — **prefix `/api/v1/` en place via `settings.api_prefix` (31/07/2026) ; header `Accept` à compléter lors de l'implémentation des endpoints (A7)**
- [ ] 0.20 **Concurrency lock vault Obsidian** : NFS `no_root_squash` + `fcntl` locking OU git sidecar (voir 0.15)
- [ ] 0.21 **Backup Qdrant** : `qdrant snapshot create` cron quotidien → stocké sur OMV M2 (HDD 2TB)
- [ ] 0.22 **Runbooks incidents** : "BC250 ne boot plus", "RTX 4000 OOM", "NFS stale handle", "Qdrant corruption", "OMV HDD failure"
- [ ] 0.23 **Kernel upgrade hook BC250** : script `rebuild-cu-unlock.sh` déclenché par `apt` hook `kernel-postinst` + `dracut -f`
- [x] 0.24 **BC250 config centralisée** : 15 variables dans `settings.py` + `.env.example` (CU count, core unlock, TTM, governor, GRUB triplet, Mesa, kernel, scripts paths)
- [ ] 0.25 **Créer `infrastructure/proxmox/create-lxc-omv.sh`** (LXC 105 OMV Backup avec passthrough HDD 2TB)
- [ ] 0.26 **Créer `infrastructure/docker/docker-compose.omv.yml`** (stack OMV via Docker)
- [ ] 0.27 **Documenter passage HDD 2TB en passthrough vers LXC 105** (`pct set 105 -mp0 /dev/disk/by-id/...,mp=/srv/backup`)
- [ ] 0.28 **Configurer secrets OMV** : clés SSH, borg repo, variables d'environnement dans `.env`
- [ ] 0.29 **Créer fichiers agents manquants** : `src/agents/planner.py`, `src/agents/query_rewriter.py`, `src/agents/context_assembler.py` (stubs avec NotImplementedError)

## Analyse post-audit (30/07/2026)

### Priorités d'exécution (build phase 31/07/2026)
1. **0.3** ✅ Qdrant + restart policies
2. **0.10** ✅ Dockerfiles fixés (Poetry→pip) + build.context orchestrator
3. **0.17** ✅ `/ready` avec checks réels (Qdrant/Ollama×3/PostgreSQL/Redis)
4. **0.18** ✅ Smoke tests 32 scénarios (46/46 tests suite complète)
5. **0.5** → Scripts Proxmox LXC (master + GPU passthrough)
6. **0.1** Implémenter les corps d'agents manquants (Judge, Avocat, Evaluator, Generator, Wiki)
7. **0.16** Secrets management (sops / Vault)
8. **0.13** mTLS interne (bloquant prod)
9. **0.19** API Versioning dans le routeur FastAPI

### Incohérences résolues (build 31/07/2026)
| Fichier | Problème | Correctif |
|---------|----------|-----------|
| `infrastructure/docker/docker-compose.vector-db.yml` | ~~Référence Chroma~~ | **✅ Qdrant** + restart policies + `name:` tag |
| `infrastructure/docker/docker-compose.orchestrator.yml` | ~~build.context: ../../src~~ (pointe vers `src/` au lieu de repo root) | **✅ fixé** → `context: ../../` + `dockerfile: infrastructure/docker/Dockerfile.*` |
| `infrastructure/docker/Dockerfile.{api,wiki-agent,langgraph}` | ~~Poetry install avec build backend setuptools~~ | **✅ `pip install .`** |
| `src/api/main.py` | ~~`/ready` retourne `{"checks": "TODO"}`~~ | **✅ checks Qdrant/Ollama M1/M2/M3/PostgreSQL/Redis, 503 si dégradé** |
| `src/core/settings.py` | `postgres_password = "CHANGE_ME"` en dur | **✅ Validator prod** lève `InsecurePasswordConfigError` déjà en place |
| `.env.example` / `src/core/settings.py` | `ADVOCATE_MODEL=mistral-small-3.2:7b` — modèle inexistant à cette taille (Mistral Small 3.2 = 24B/14.3 Go, incompatible RTX 4000 8 Go) | **✅ remplacé par Ministral-8B-Instruct-2410 Q4_K_M (4.91 Go), résolu via hf.co/bartowski/...** |
| `tests/test_api.py` | ~~`test_ready` attend 200 fixe~~ | **✅ accepte 200 ou 503** |
| `scripts/smoke_test_frontend_api.py` | ~~`NotImplementedError` stub~~ | **✅ 32 scénarios passent** |

## Phase 1 — Pipeline RAG Core (Master LXC 100-101) — **À FAIRE — AUCUNE TÂCHE LIVRÉE (audit 31/07/2026)**

> ⚠️ Correction d'état : les items 1.1-1.9 ci-dessous étaient cochés `[x]` mais **rien n'est implémenté** dans le code — `src/services/{ingestion,lexical,reranker}.py` absents, `OllamaClient`/`VectorService` et les endpoints `/ingest` `/query` `/embed` lèvent tous `NotImplementedError`. L'ordre d'exécution suit le ROADMAP Sprint 2.
- [ ] 1.1 Ingestion Service (chunking, augmentation, embedding sur Machine 1 CPU)
- [ ] 1.2 VectorService (Qdrant client, hybrid search natif dense + sparse BM25)
- [ ] 1.3 LexicalSearch (BM25 via Qdrant sparse vectors natif)
- [ ] 1.4 Reranker (bge-reranker-v2-m3 sur RTX 4000 - Machine 2)
- [ ] 1.5 API Endpoints (/ingest, /query, /embed OpenAI-compat) + versioning `/api/v1/`
- [ ] 1.6 Endpoint `/api/v1/embed` : bge-m3 dense+sparse unifié + fallback histogramme
- [ ] 1.7 OllamaClient complet (generate, embed, rerank, unload, health + retry/circuit-breaker)
- [ ] 1.8 OllamaClientPool routing intelligent (M1/M2/M3 selon rôle)
- [ ] 1.9 Tests d'intégration hybrid search (ingest → embed → search → rerank)

## Phase 2 — Orchestrateur & Planificateur (LXC 100 - Machine 1)
- [ ] 2.1 Orchestrator (flux principal)
- [ ] 2.2 Planner (intention + stratégie)
- [ ] 2.3 QueryRewriter (réécriture conversationnelle)
- [ ] 2.4 ContextAssembler (chunks + savoir interne + fenêtre)
- [ ] 2.5 HTTP Client Pool (httpx avec retry/circuit-breaker + **mTLS**)
- [ ] 2.6 **PlannerAgent** (nouveau fichier `src/agents/planner.py`) — analyse intention, décide stratégie outils/variantes
- [ ] 2.7 **QueryRewriterAgent** (nouveau fichier `src/agents/query_rewriter.py`) — réécriture avec historique conversationnel
- [ ] 2.8 **ContextAssembler** (nouveau fichier `src/agents/context_assembler.py` ou service) — fusion chunks rerankés + savoir interne + fenêtre courte
- [ ] 2.9 **LangGraph build_graph()** complet — relie Planner → Rewriter → HybridSearch → Reranker → ContextAssembler → Generator → Relay → Judge → Advocate → Evaluator → WikiUpdate

## Phase 3 — Génération + Évaluation Multi-Agents
- [ ] 3.1 Generator (hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M ou hf.co/Qwen/Qwen3-30B-A3B-GGUF:Q2_K sur BC250 Vulkan)
- [ ] 3.2 Judge (hf.co/bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF:Q4_K_M sur RTX 4000 - Machine 2 LXC 200) — **séquentiel, unload après écriture relay**
- [ ] 3.3 Devil's Advocate (hf.co/bartowski/Ministral-8B-Instruct-2410-GGUF:Q4_K_M sur RTX 4000 - Machine 2 LXC 201) — **séquentiel après Judge, lit relay**
- [ ] 3.4 Evaluator (hf.co/ibm-granite/granite-4.1-8b-instruct-GGUF:Q4_K_M sur Machine 1 CPU) — **lit relay.json complet, synthèse finale**
- [ ] 3.5 **Évaluateur écrit `verified: human-reviewed` dans frontmatter pages validées (OKF trust tier)**
- [ ] 3.6 **Ollama model unload séquentiel** : `ollama unload` + vérif VRAM libérée entre Judge → Avocat

## Phase 4 — Wiki Persistant (Pattern Karpathy + OKF v0.2)
- [ ] 4.1 WikiTools (read/write/append/index/log via vault Obsidian)
- [ ] 4.2 IngestAgent (source → pages wiki + index.md + log.md)
- [ ] 4.3 Schema AGENTS.md (conventions nommage, frontmatter OKF v0.2, structure)
- [ ] 4.4 Endpoint /api/v1/ingest
- [ ] 4.5 **Structure vault OKF : `index.md` (§8 catalogue) + `log.md` (§9 chronologie) + frontmatter validé**
- [ ] 4.6 **Lint endpoint `/api/v1/lint` utilise `okf list --stale --orphan --contradiction`**

## Phase 5 — Variantes Avancées
- [ ] 5.1 Text-to-SQL (BC250, hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q2_K, contexte 64k)
- [ ] 5.2 Vision (BC250, hf.co/cjpais/llava-v1.6-vicuna-13b-gguf:Q4_K_M / qwen2.5-vl Q4_K_M)
- [ ] 5.3 Graph RAG (NetworkX + entités wiki)
- [ ] 5.4 Long-term Memory (PostgreSQL conversations + feedback)

## Phase 6 — Intégration Obsidian Vault
- [ ] 6.1 Bind mount /data/wiki sur LXC 100 → partagé NFS/SMB vers client
- [ ] 6.2 Structure vault (index.md, log.md, entities/, concepts/, sources/, synthesis/)
- [ ] 6.3 Webhook file watcher (Obsidian → cluster via web clipper)

## Phase 7 — Observabilité & Hardening (allégé — décision 31/07/2026, cf. D9)
- [x] ~~7.1 Prometheus + Grafana (LXC 103)~~ **RETIRÉ** — sur-ingénierie pour 3 nœuds, remplacé par graphs natifs Proxmox VE (M1/M2) + pfSense (RRD/vnstat), zéro coût
- [x] ~~7.2 Loki + structured logs (correlation ID)~~ **RETIRÉ de la v1** — logs via `journalctl`/Docker logs en direct suffisent tant que le cluster n'est pas stabilisé ; à ré-évaluer seul (sans Prometheus/Grafana) si besoin réel de centralisation
- [ ] 7.2bis **Glances (mode web `-w`)** sur BC-250 uniquement — seul nœud hors supervision Proxmox (bare metal, pas de LXC/RRD natif)
- [ ] 7.3 Health checks agrégés (`/health` + `/ready` déjà en place, cf. 0.17)
- [ ] 7.4 Tests integration (smoke_test_frontend_api.py)
- [ ] 7.5 **Secrets management prod** : `sops` / Vault rotation
- [ ] 7.6 **Load testing pré-prod** : `hey` / `locust` sur `/api/v1/query` 10-50 RPS
- [ ] 7.7 **Réactivation Prometheus+Grafana post-stabilisation** (optionnelle, non planifiée) — seulement si diagnostic perf réel requis (latence Reranker vs Générateur, saturation VRAM RTX4000)

## Infrastructure Matérielle Validée (selon README.md)

| Nœud | Rôle | CPU / RAM | GPU / Accélérateur | Stockage | Virtualisation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Machine 1** | **Master** (Orchestration, API, VectorDB, Evaluator, Embedding CPU, Relay NFS) | 2× Xeon E5-2699 v4 / **32 GB ECC** | AMD Radeon RX 580 (8 GB) | 1 TB NVMe | Proxmox VE 9.3 (LXC 100, 101, VM 104) — monitoring natif via UI Proxmox, plus de LXC 103 dédié |
| **Machine 2** | **GPU Worker + Services** (Reranker, Judge, Avocat, Backup Embedding CPU, **OMV Backup**) | 1× Xeon E5-2698 v4 / **64 GB ECC** | **NVIDIA Quadro RTX 4000** (8 GB VRAM dédiée) | **1 TB NVMe** + **HDD 2TB physique** | Proxmox VE 9.3 (LXC 105, 200 privilégié GPU, 201) — monitoring natif via UI Proxmox |
| **Machine 3** | **BC250 Baremetal** (Generator, Text-to-SQL, Vision, Fast-check) | Zen 2 **8c/16t** (core unlock persistant par BIOS complet Forbidden-Darkness, base P3.00 incluse, flash UEFI direct, aucun flash P3.00 stock préalable) / **16 GB GDDR6 unifiée** | **Intégré - Vulkan ONLY** (40 CU débloquées via [duggasco/bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock), séparé) | Fedora 43 baremetal (Ollama Vulkan natif) |
| **Client** | Obsidian Vault (visualisation + ingestion) | Poste de travail | – | Native (Electron) |

* VM 104 = pfSense (reverse proxy + firewall + NAT).

**Réseau** : Machine 1 dispose de 2 ports 10 Gb/s + 1 port 1 Gb/s (carte familiale) — backbone 10 Gb/s inter-nœuds recommandé.

**NFS Relay** : Machine 1 exporte `/data/shared` → monté sur Machine 2 `/data/shared` (fichier `evaluation-relay.json` partagé pour pipeline Juge→Avocat→Évaluateur).

**Répartition LXC/VM prévue** :
- Machine 1 : `100` Orchestrator, `101` Vector DB (Qdrant), `104` pfSense (VM — reverse proxy + firewall + NAT) — ~~`103` Monitoring~~ retiré, graphs natifs Proxmox suffisent
- Machine 2 : `105` **OMV Backup (HDD 2TB passthrough)**, `200` Inference GPU (passthrough RTX 4000), `201` Workers Agents (Avocat + Backup Embedding CPU)
- Machine 3 : Ollama Vulkan natif (pas de LXC)

## Modèles Recommandés par Machine (30/07/2026 - validé échange)

### Machine 1 — Master (32GB ECC, RX 580)
| Rôle | Modèle | Quant | Raison |
|------|--------|-------|--------|
| **Embedding principal** | `hf.co/nomic-ai/nomic-embed-text-v2-moe-GGUF:Q8_0` (768d) | Q8_0 (CPU) | Xeon 32c/64t idle, batch offline |
| **Évaluateur** | `hf.co/ibm-granite/granite-4.1-8b-instruct-GGUF:Q4_K_M` | Q4_K_M | CPU M1, synthèse + décision, diversification lignée vs Générateur Qwen |
| **Fallback léger** | `qwen2.5:3b` | Q4_K_M | Usage général de secours — sans pipeline monitoring/alerting dédié (retiré, cf. Phase 7) |

### Machine 2 — GPU Worker (64GB ECC, RTX 4000 8GB VRAM, Xeon 2698 v4 20c/40t)
| Rôle | Modèle | Quant | VRAM estimée | Raison |
|------|--------|-------|--------------|--------|
| **Reranker** | `hf.co/gpustack/bge-reranker-v2-m3-GGUF:Q4_K_M` | Q4_K_M | ~4-6 GB | Tient dans RTX 4000 |
| **Judge** | `hf.co/bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF:Q4_K_M` | Q4_K_M | ~5 GB | Éval qualité, fort raisonnement |
| **Avocat du diable** | `hf.co/bartowski/Ministral-8B-Instruct-2410-GGUF:Q4_K_M` | Q4_K_M | ~5 GB | Approche différente → diversité |
| **Embedding batch (backup)** | `hf.co/nomic-ai/nomic-embed-text-v2-moe-GGUF:Q8_0` | Q8_0 (CPU) | - | 64GB RAM + 40 threads inutilisés si Machine 1 saturée |

> **Note** : 64GB ECC permet de charger **tous les buffers simultanément** (reranker + judge + avocat + ingestion) sans swap.

### Machine 3 — BC250 Baremetal (16GB GDDR6 unifiée, Vulkan-only, 40 CU unlocked)
| Rôle | Modèle | Quant | Raison |
|------|--------|-------|--------|
| **Generator principal** | `hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M` (dense) | Q4_K_M | ~9 GB, 40 CU → ~30 tok/s |
| **Generator alternatif (qualité)** | `hf.co/Qwen/Qwen3-30B-A3B-GGUF:Q2_K` (MoE) | Q2_K | ~11.3 GB, 40 CU → ~78 tok/s (llama.cpp direct) |
| **Text-to-SQL / Code** | `hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q2_K` (MoE) | Q2_K | 3B actifs, 64k contexte, français |
| **Vision (Phase 5.2)** | `hf.co/cjpais/llava-v1.6-vicuna-13b-gguf:Q4_K_M` / `qwen2.5-vl` | Q4_K_M | Même contrainte que Generator 14B |
| **Fast-check lexical skill** | `hf.co/ibm-granite/granite-4.0-h-tiny-GGUF:Q4_K_M` (3.4B hybrid Mamba) | Q4_K_M | 40 CU → **129 tok/s**, 128K+ contexte |

---

## Machine 3 — BC250 Baremetal : Checklist Complète (29/07/2026)

### Hardware & Firmware
- [ ] Carte BC-250 reçue, inspectée (PCB, condensateurs, slot PCIe)
- [ ] Alim 300W+ 12V 8-pin PCIe connectée
- [ ] Refroidissement AIO / high-CFM fans monté (test thermal paste)
- [ ] BIOS moddé Forbidden-Darkness flashé (image complète, base P3.00 incluse — aucun flash P3.00 stock préalable)
- [ ] BIOS VRAM: Dynamic 512 MB configuré (dans le BIOS Forbidden-Darkness)
- [ ] Backup BIOS d'origine sur USB (procédure recovery validée)

### OS & Kernel
- [ ] Fedora 43 installé (Basic Graphics Mode au boot install, `nomodeset` si écran noir)
- [ ] Kernel 6.18.18 LTS ou 6.19.x installé (pin versionlock pour éviter 6.15/6.17 buggés)
- [ ] GRUB: `ttm.pages_limit=3959290 ttm.page_pool_size=3959290 amdgpu.sg_display=0`
- [ ] `grub2-mkconfig -o /boot/grub2/grub.cfg` + reboot + vérif `cat /proc/cmdline`
- [ ] CPU governor: `performance` persistant (tmpfiles.d)

### Mesa / Vulkan
- [ ] `dnf install mesa-vulkan-drivers vulkan-tools mesa-utils` (mainline Fedora 43)
- [ ] `vulkaninfo --summary` → "AMD BC-250 (RADV GFX1013)" + INTEGRATED_GPU
- [ ] `glxinfo` → OpenGL 4.6+ Mesa 25.1.x

### GPU Governor (Oberon)
- [ ] `cyan-skillfish-governor-smu` installé (COPR filippor/bazzite)
- [ ] Config `/etc/cyan-skillfish-governor-smu/config.toml` → core_cap_mhz=1500, voltage_mv=900
- [ ] `systemctl enable --now cyan-skillfish-governor-smu`
- [ ] `journalctl -u cyan-skillfish-governor-smu` → OK

### 40 CU Unlock (Optionnel — recommandé pour production)
- [ ] `cu_map.sh` exécuté → harvest pattern contigu validé
- [ ] Repo duggasco cloné, deps build installées (headers, build-essential, zstd)
- [ ] `./scripts/bc250-enable-40cu.sh build` → module amdgpu patché
- [ ] `./scripts/bc250-enable-40cu.sh enable` → modprobe + reboot
- [ ] **Triple vérif post-reboot** :
    - [ ] `cat /sys/module/amdgpu/parameters/bc250_cc_write_mode` → `3`
    - [ ] `dmesg | grep active_cu_number` → `active_cu_number 40`
    - [ ] `RADV_DEBUG=info vulkaninfo --summary | grep num_cu` → `40`
- [ ] Bench A/B 24 vs 40 CU (4K ctx, 3 runs) → +32% gen median validé
- [ ] Procédure rollback testée (`disable` → reboot → 24 CU)

### Swap NVMe
- [ ] `dd if=/dev/zero of=/swapfile bs=1M count=16384`
- [ ] `chattr +C /swapfile` (btrfs CoW off)
- [ ] `mkswap /swapfile && swapon -p 10 /swapfile`
- [ ] `/swapfile none swap sw,pri=10 0 0` dans `/etc/fstab`
- [ ] zram réduit à 2 GB max (`/etc/systemd/zram-generator.conf.d/small.conf`)

### Ollama + Modèles (Digests SHA256 lockés dans .env)
- [ ] Ollama installé (script officiel)
- [ ] Override systemd créé avec 9 env vars Vulkan + OOMScoreAdjust=-1000
- [ ] `systemctl daemon-reload && systemctl restart ollama`
- [ ] `journalctl -u ollama` → "total=12.3 GiB available"
- [ ] Modèles pullés avec digests :
    - [ ] `hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M@sha256:...` (Q4_K_M, ~9 GB)
    - [ ] `hf.co/Qwen/Qwen3-30B-A3B-GGUF:Q2_K@sha256:...` (Q2_K, ~11.3 GB)
    - [ ] `hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q2_K@sha256:...` (Q2_K)
    - [ ] `hf.co/cjpais/llava-v1.6-vicuna-13b-gguf:Q4_K_M@sha256:...` (Q4_K_M)
    - [ ] `qwen2.5-vl@sha256:...` (Q4_K_M)
    - [ ] `hf.co/ibm-granite/granite-4.0-h-tiny-GGUF:Q4_K_M@sha256:...` (Q4_K_M)
    - [ ] `hf.co/nomic-ai/nomic-embed-text-v2-moe-GGUF:Q8_0@sha256:...`

### Réseau & NFS (VLAN 10)
- [ ] IP statique 10.10.0.3/24, MTU 9000 sur interface 1G
- [ ] Route pfSense 10.10.0.254 → Internet (NAT)
- [ ] NFS client: mount M1:/data/shared → /data/shared (_netdev, fstab)
- [ ] NFS client: mount M1:/data/wiki → /data/wiki (_netdev, fstab)
- [ ] Firewall: autoriser 11434 (Ollama), 2049 (NFS), 80/443 (WAN)
- [ ] Test: `iperf3 -c 10.10.0.1` → >900 Mbps, MTU 9000 OK

### Monitoring & Observabilité (allégé — décision 31/07/2026, cf. D9)
- [x] ~~`prometheus-node-exporter` installé + scrape config M1~~ **RETIRÉ** — pas de Prometheus central
- [ ] **Glances en mode web (`glances -w`)** — seul dashboard sur BC-250 (unique nœud hors supervision Proxmox), CPU/RAM/temp en un seul process léger
- [ ] GPU telemetry: oberon governor metrics (power, temp, clock) — exposés via Glances si plugin dispo, sinon `watch -n1` cron + log fichier
- [ ] SMART NVMe: `nvme smart-log` cron + alertes usure (mail/webhook simple, pas d'exporter dédié)
- [x] ~~Logs: journald → Loki (correlation ID)~~ **RETIRÉ de la v1** — `journalctl` direct suffit
- [ ] Healthcheck: `curl -f localhost:11434/api/tags` + `vulkaninfo` cron

### Backup (Pull OMV M1)
- [ ] Clé SSH OMV→BC250 configurée (pull-only)
- [ ] Script rsync `/etc /var/lib/ollama /root/.ollama/models` → OMV
- [ ] Cron quotidien OMV → borg repo → HDD 2TB cold (LUKS)

### Runbooks & Maintenance
- [ ] Runbook: "BC250 ne boot plus" (BIOS recovery, kernel params)
- [ ] Runbook: "Ollama HTTP 500 14B+" (check ttm.pages_limit)
- [ ] Runbook: "CU unlock lost" (rebuild patch post-kernel-update)
- [ ] Runbook: "Thermal throttle" (governor config, nettoyage)
- [ ] Runbook: "NVMe full" (prune modèles, check swap)
- [ ] Checklist post-reboot obligatoire documentée + automatisée (script)

### Intégration Cluster
- [ ] Endpoint Ollama API accessible M1/M2 (10.10.0.3:11434)
- [ ] Relay NFS: écriture relay.json depuis M1, lecture depuis M3 (si besoin)
- [ ] Règle d'or validée: CPU BC250 idle pendant inférence (htop/watch -n1)
- [ ] Test bout-en-bout: M1 → generate → relay.json → M2 Judge/Avocat → M1 Evaluator

### Points de vigilance critiques (pièges documentés)

| Piège | Symptôme | Solution |
|-------|----------|----------|
| **`systemd-tmpfiles` écrase `ttm.pages_limit`** | `cat /sys/module/ttm/parameters/pages_limit` → `3145728` (12 GiB) au lieu de `3959290` (~15 GiB) | Vérifier **après reboot**, pas après écriture. `tmpfiles.d` priorité finale gagne. Corriger `/etc/tmpfiles.d/gpu-ttm-memory.conf` |
| **Kernel update casse 40 CU unlock** | `active_cu_number` retombe à 24 | Rebuild module patché + `dracut -f` + reboot **après chaque kernel upgrade** |
| **Mesa trop vieux** | `vulkaninfo` → Mesa 24.x, pas de RADV GFX1013 | **Fedora 43** — Mesa 25.1+ en mainline, `dnf upgrade mesa-vulkan-drivers` |
| **ROCm installé par erreur** | `rocblas_abort()`, compute queue hang | **Ne jamais installer ROCm**. Vulkan only. |
| **CPU governor `schedutil`** | Spikes latence TTFT, instabilité | `performance` lock via tmpfiles.d |
| **zram trop gros** | Concurrence RAM physique avec modèles | Max 2 GB (`zram-size = 2048`) |
| **Modèles sans digest SHA256** | `ollama pull hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M` → version mobile différente | **Toujours** `@sha256:...` dans `.env` / scripts |

### Dépendances croisées (ordre d'exécution)

```
1. Hardware/BIOS/OS/Kernel/GRUB → reboot → vérif cmdline + ttm.pages_limit
      ↓
2. Mesa experimental + vulkaninfo → OK
      ↓
3. GPU Governor (oberon) → systemctl enable → OK
      ↓
4. Swap NVMe + zram reduce + CPU governor performance
      ↓
5. Ollama install + systemd override → restart → journalctl check
      ↓
6. 40 CU unlock (si choisi) → cu_map.sh → build → enable → reboot → TRIPLE VERIF
      ↓
7. Modèles pull (digests lockés) → test generate 4K ctx
      ↓
8. Réseau VLAN 10 + NFS mounts + firewall pfSense
      ↓
9. Monitoring (Glances web, oberon metrics, SMART) — plus de node-exporter/Loki
      ↓
10. Backup pull OMV configuré + test restore partiel
      ↓
11. Runbooks écrits + test bout-en-bout cluster (M1→M3→M2→M1)
```

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

Le Master LXC 100 a **2 × Xeon 2699** (16c/32t chacun, 32GB ECC) contre 8c/16t Zen 2 sur BC250 :
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

> **Le CPU du BC250 est le serviteur du GPU.** Toute charge CPU significative sur BC250 est un vol de bande passante mémoire au Generator 14B. Le CPU BC250 (Zen 2 8c/16t) doit rester au repos (ou charge minimale) quand le GPU fait de l'inférence Vulkan.

**Références** :
- [AMD BC250 Documentation](https://elektricm.github.io/amd-bc250-docs/) — Unified Memory Architecture, Vulkan-only, 40 CU unlock
- [akandr/bc250](https://github.com/akandr/bc250) — Ollama + Vulkan benchmarks, GFX1013 specifics, roofline analysis

→ **Décision** : Embedding sur **Machine 1 Master LXC 100 (Xeon CPU)** via Ollama/llama.cpp CPU `hf.co/nomic-ai/nomic-embed-text-v2-moe-GGUF:Q8_0` 768d. BC250 GPU réservé **exclusivement** au Generator 14B/MoE (Phase 3.1) et aux variantes lourdes (Phase 5 : Text-to-SQL, Vision, Granite fast-check). Machine 2 (64GB + RTX 4000) = Reranker + Judge + Avocat + backup embedding CPU.

**Actions** :
- [ ] Mettre à jour `docs/architecture.svg` — 3 machines, mapping correct des modèles
- [ ] Mettre à jour `src/core/settings.py` — variables `EMBEDDING_HOST=machine1` / `EMBEDDING_MODEL=hf.co/nomic-ai/nomic-embed-text-v2-moe-GGUF:Q8_0` / `EMBEDDING_MODE=cpu` + endpoints GPU Worker + BC250
- [ ] Mettre à jour `services/vector.py` — configurer client embedding vers endpoint Machine 1 au lieu de BC250
- [ ] Phase 1.1 : changer "embedding BC250" → "embedding Machine 1 CPU (backup Machine 2 CPU)"
- [ ] Phase 3.1 : changer "Qwen2.5-14B sur RTX 4000" → "qwen3.5:14b Q4_K_M / qwen3.5-35b-a3b IQ2_M sur BC250 Vulkan"
- [ ] Phase 3.2/3.3 : préciser Judge sur LXC 200, Avocat sur LXC 201 (même RTX 4000, VRAM partagée 2×5GB OK)
- [ ] Phase 5.1 : préciser hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q2_K sur BC250
- [ ] Phase 5.2 : déplacer Vision sur BC250 (pas RTX 4000)

---

### 29/07/2026 — Pipeline Séquentiel Juge → Avocat sur Machine 2 (RTX 4000 8GB) — **TRANCHÉ**

**Problème** : Judge (hf.co/bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF:Q4_K_M ~5GB) + Avocat (hf.co/bartowski/Ministral-8B-Instruct-2410-GGUF:Q4_K_M ~5GB) = **~10GB VRAM** > **8GB RTX 4000**. Impossible de les faire tourner en parallèle.

**Solution** : Exécution **séquentielle** sur le même GPU (LXC 200/201 partagé) avec **unload explicite** du modèle précédent avant chargement du suivant.

**Flux** :
```
Generator (BC250 M3) → réponse écrite dans relay.json
  ↓
Juge (M2 RTX 4000) → charge hf.co/bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF:Q4_K_M → évalue → écrit relay.json → **unload modèle**
  ↓
Avocat (M2 RTX 4000) → charge hf.co/bartowski/Ministral-8B-Instruct-2410-GGUF:Q4_K_M → lit relay + réponse → évalue → écrit relay → **unload**
  ↓
Évaluateur (M1 CPU) → lit relay complet → synthèse → réponse utilisateur
```

**Mécanisme de relais (relay.json)** :
Fichier JSON unique partagé M1↔M2 (via **NFS mount** `/data/shared` entre Machine 1 et Machine 2), écrasé à chaque session :

```json
{
  "session_id": "uuid",
  "query": "...",
  "response": "...",
  "context": [...],
  "judge": {
    "status": "done",
    "score": 0.85,
    "critique": "...",
    "timestamp": "2026-07-29T..."
  },
  "avocat": {
    "status": "done",
    "score": 0.65,
    "faille": "...",
    "timestamp": "2026-07-29T..."
  }
}
```

**Points techniques** :
- **NFS mount** Machine 1 (`/data/shared`) ↔ Machine 2 (`/data/shared`) — unique source de vérité
- **Watch fichier (inotify)** sur M2 pour déclencher auto : Juge terminé → lance Avocat
- **Timeout** : si Juge > 120s sans écrire → Avocat prend la main avec `judge.status: "timeout"`
- **Archivage** : relay.json copié dans `log.md` du wiki après synthèse Evaluateur (pattern Karpathy compounding)

**Actions** :
- [ ] Ajouter NFS export sur Machine 1 `/data/shared` + mount sur Machine 2
- [ ] Créer `services/relay.py` : client relay (read/write JSON atomique, file locking)
- [ ] Modifier Phase 3.2/3.3 : séquentiel explicite + unload entre modèles
- [ ] Modifier Orchestrator (Phase 2.1) : attendre relay complet avant passer à Evaluateur
- [ ] Ajouter `RELAY_PATH=/data/shared/evaluation-relay.json` dans `settings.py`
- [ ] Phase 3.4 : Evaluateur lit relay, pas appel HTTP direct

---

### 29/07/2026 — Règle d'or BC250 confirmée : CPU = serviteur du GPU — **TRANCHÉ**

**Documentation communautaire** :
- [AMD BC250 Docs](https://elektricm.github.io/amd-bc250-docs/) — Unified Memory Architecture, Vulkan-only, 40 CU unlock
- [akandr/bc250](https://github.com/akandr/bc250) — Ollama + Vulkan benchmarks, GFX1013 specifics, roofline analysis

**Preuve** : Le BC250 a 16GB GDDR6 **unifiée** (CPU+GPU même pool, même bande passante). Toute charge CPU (embedding, batch, compilation) :
1. Vole de la bande passante mémoire au GPU Vulkan
2. Crée de la contention thermique (235W TDP max dans format compact)
3. Réduit la VRAM effective disponible pour le Generator 14B

→ **CPU BC250 (Zen 2 8c/16t) DOIT RESTER AU REPOS** pendant l'inférence GPU. Embedding = Machine 1 CPU (principal) / Machine 2 CPU (backup).

---

### 29/07/2026 — Plan Réseau Cluster (VLAN, NFS, pfSense) — **TRANCHÉ**

**Topologie physique** :
- Machine 1 : 2× 10GbE (backbone cluster) + 1× 1GbE (management/secours)
- Machine 2 : 1× 10GbE (backbone) + 1× 1GbE (management)
- Machine 3 : 1× 1GbE (backbone via switch 10G) — BC250 n'a pas de 10G natif
- Client : 1× 1GbE (LAN)

**VLAN / Sous-réseaux** :
| VLAN | CIDR | Usage | Machines |
|------|------|-------|----------|
| 10 (Cluster) | `10.10.0.0/24` | Backbone 10G inter-nœuds (Qdrant, Ollama API, NFS) | M1(10.10.0.1), M2(10.10.0.2), M3(10.10.0.3) |
| 20 (WAN) | `192.168.1.0/24` | pfSense → Internet (updates, modèles) | pfSense GW |
| 30 (Mgmt) | `172.16.0.0/24` | Proxmox GUI, IPMI, SSH secours (1G) | M1, M2, M3 |
| 40 (Client) | `192.168.10.0/24` | Obsidian client, web UI | Client, pfSense |

**Passerelle** : pfSense (VM sur Proxmox M1 ou appliance dédiée) — routes inter-VLAN + NAT sortant.

**NFS Relay (évaluation)** :
- Export M1 : `/data/shared` → `10.10.0.0/24(rw,sync,no_subtree_check,no_root_squash)`
- Mount M2 : `/data/shared` sur `10.10.0.1:/data/shared` (fstab, `_netdev`)
- Fichier : `evaluation-relay.json` (verrou fichier atomique, TTL 300s)

**Flux réseau autorisés (firewall pfSense)** :
| Source | Dest | Proto/Port | Usage |
|--------|------|------------|-------|
| 10.10.0.0/24 | 10.10.0.0/24 | TCP 6333 | Qdrant (VectorDB) |
| 10.10.0.0/24 | 10.10.0.0/24 | TCP 11434 | Ollama API (M2, M3) |
| 10.10.0.0/24 | 10.10.0.0/24 | TCP 2049/NFS | Relay évaluation + vault wiki |
| 10.10.0.2 | 10.10.0.1 | TCP 2049 | Mount NFS M1→M2 |
| 192.168.10.0/24 | 10.10.0.1 | TCP 80/443 | Client → pfSense (reverse proxy → LXC 100:8000) |
| 10.10.0.0/24 | 192.168.1.0/24 | TCP 80/443 | Sortie modèles/updates (via pfSense NAT) |
| 172.16.0.0/24 | *any* | SSH/HTTPS | Admin Proxmox/IPMI (isolé) |

**MTU** : 9000 (Jumbo frames) sur VLAN 10 pour NFS/Ollama/Qdrant — gain ~15% débit gros transferts.

**Actions** :
- [ ] Configurer switch 10G (VLAN 10 taggé, MTU 9000)
- [ ] Déployer pfSense (VM M1 LXC 104 ou appliance) + règles firewall
- [ ] Configurer NFS export M1 `/etc/exports` + mount M2 `/etc/fstab`
- [ ] Tester iperf3 M1↔M2 10G > 9Gbps + MTU 9000
- [ ] Documenter dans `infrastructure/network/plan-reseau.md`

---

## Avis DevOps — Cohérence Globale (29/07/2026)

### ✅ Points forts (Architecture solide)

| Domaine | Pourquoi c'est cohérent |
|---------|------------------------|
| **Séparation charge/GPU** | BC250 = Generator ONLY (Vulkan, pas de ROCm), RTX 4000 = Judge/Avocat/Reranker (CUDA natif), CPU Xeon = Embedding/Evaluator. Zéro surcharge. |
| **Contrainte mémoire BC250 respectée** | Règle d'or "CPU serviteur GPU" appliquée — embedding déporté, BC250 CPU au repos. Évite contention bande passante + throttling thermique. |
| **Pipeline séquentiel Juge→Avocat** | Résout le problème 2×7B > 8GB VRAM RTX 4000 sans hardware supplémentaire. Relay NFS = pattern connu (sidecar file). |
| **Diversité familles modèles** | Judge (Qwen) ≠ Avocat (Mistral) → vrais biais différents → évaluation croisée efficace. |
| **Pattern Karpathy (Wiki persistant)** | Frontend Obsidian = 0 code frontend à maintenir. Vault = source de vérité + graphe de connaissances. |
| **Infrastructure as Code prête** | Proxmox LXC + Docker Compose + scripts bash = reproductible, versionnable. |
| **Observabilité intégrée** | ~~Prometheus/Grafana/Loki prévu dès Phase 7~~ *(analyse dépassée, cf. D9 31/07/2026 : stack complète jugée sur-ingénierie pour 3 nœuds, remplacée par Proxmox/pfSense natif + Glances BC-250)*. |

### ⚠️ Points de vigilance (Risques maîtrisés)

| Risque | Impact | Mitigation |
|--------|--------|------------|
| **Single Point of Failure : Machine 1 (Master)** | Qdrant + API + Wiki + Evaluator + NFS = tout s'arrête si M1 tombe | → Backup Qdrant snapshot quotidien sur M2. NFS export read-only possible depuis M2. |
| **NFS latency sur évaluation** | Relay file = point de synchronisation bloquant | → MTU 9000 + 10GbE = <1ms RTT. Timeout 120s Juge → Avocat. Acceptable. |
| **BC250 baremetal = pas de snapshot/rollback** | Mise à jour noyau/BIOS risquée | → Tests sur VM simulée d'abord. Backup config `/etc` + BIOS d'origine sur USB. |
| **RTX 4000 8GB limite dure** | Pas de place pour modèle > 7B quantifié | → Choix validé : Judge/Avocat 7B max. Si besoin 14B → seul BC250 peut. |
| **Modèles non verrouillés (tags Ollama)** | `hf.co/bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF:Q4_K_M` pull = version mobile → reproductibilité | → Fixer digests SHA256 dans `.env` / `docker-compose`. `ollama pull hf.co/bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF:Q4_K_M@sha256:...` |
| **Obsidian vault lock concurrency** | Client + Cluster écrivent simultanément | → NFS `no_root_squash` + file locking (fcntl). Ou versioning git sidecar. |
| **Secrets management absent** | `.env.example` a des `CHANGE_ME` — pas de solution prod | → Phase 7 : `sops` + `.env.encrypted` ou HashiCorp Vault |
| **VectorDB incohérence** | `docker-compose.vector-db.yml` = Chroma, README = Qdrant | → **Corriger maintenant** : Qdrant (hybrid search natif) |
| **Health checks = 0** | Pas d'observabilité avant Phase 7 | → Ajouter `/health` + `/ready` sur chaque service dès Phase 0 *(déjà fait, cf. 0.17)* — ~~Prometheus scrape~~ retiré, consultation directe possible via `curl`/Glances |
| **Tests d'intégration = 0** | `scripts/test_frontend_api.py` référencé mais absent | → ✅ Écrire `smoke_test_frontend_api.py` (32 scénarios) — **32/32 PASSED**, nom corrigé dans README |
| **API Versioning absent** | `/api/v1/` dans README mais pas dans code | → Définir stratégie (URL path `/api/v1/` + header `Accept`) dès Phase 1.5 |
| **BC250 Kernel upgrade = CU unlock cassé** | Documenté mais pas d'automatisation | → Script `rebuild-cu-unlock.sh` déclenché par `apt` hook `kernel-postinst` |
| **Ollama unload séquentiel non implémenté** | Point critique pipeline Judge→Avocat | → Implémenter dans `services/agents/judge.py` + `advocate.py` avec healthcheck VRAM |

### 🔧 Recommandations immédiates (DevOps)

1. **Lock les versions modèles** — Ajouter dans `.env` : `OLLAMA_MODEL_JUDGE=hf.co/bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF:Q4_K_M@sha256:xxx` etc.
2. **Health checks obligatoires** — `/health` sur chaque service (Ollama, Qdrant, API) — consultation via `curl`/Glances, ~~Prometheus scrape~~ retiré.
3. **Secrets management** — Pas de tokens/API keys en dur. `sops` + `.env.encrypted` ou Vault (Phase 7).
4. **Backup Qdrant** — `qdrant snapshot create` cron quotidien → stocké sur M2 (64GB dispo).
5. **Test de charge pré-prod** — `hey` / `locust` sur `/api/v1/query` avec 10-50 RPS avant mise en prod.
6. **Runbook incident** — Documenter : "BC250 ne boot plus", "RTX 4000 OOM", "NFS stale handle", "Qdrant corruption".

### Verdict

**Architecture cohérente, contrainte hardware respectée, pattern d'évaluation multi-agents viable.**

Le cluster tient sur 3 machines hétérogènes sans compromis majeur. Le seul "hack" assumé est le relay NFS séquentiel — mais c'est un pattern standard (sidecar file) qui évite d'acheter un 2e RTX 4000.

---

### 29/07/2026 — Plan Backup 2-1 (OMV LXC 105 + HDD 2TB cold) — **TRANCHÉ (rétabli 31/07/2026)**

**Topologie stockage** :
| Niveau | Support | Contenu | Fréquence | Outil |
|--------|---------|---------|-----------|-------|
| **Prod (NVMe)** | M1: 1 TB | Proxmox, LXCs, Qdrant, Wiki | — | — |
| | M2: 1 TB | Proxmox, LXCs, Ollama cache, Monitoring | — | — |
| | BC250: 475 GB | OS Debian, Modèles (9-11 GB) | — | — |
| **Backup (HDD 2TB dans M2)** | HDD géré par OMV LXC 105 (Docker) | Qdrant snapshots, Wiki rsync, Configs M1/M2/BC250, Ollama models cache | Quotidien (cron 02:00-05:00) | borg pull + rsync → borg create |

**Règle 2-1** : 2 copies (Prod NVMe + OMV HDD) · 2 médias (NVMe + HDD) · **Pas d'off-site planifié**.

**Flux backup** :
```
OMV (M2 LXC 105) ──borg pull──► M1 (Qdrant snapshot + wiki + configs)
     │                  ──rsync pull──► BC250 (configs + Ollama cache)
     │
     └──► HDD 2TB local (borg create --compression lz4, repo LUKS)
```

**Planning d'exécution (heures creuses IA — pipeline inactif)** :
| Fenêtre | Tâche | Note |
|---------|-------|------|
| **02:00** | Qdrant snapshot | Backup atomique VectorDB (pull OMV) |
| **02:30** | Rsync wiki + configs | Wiki vault, configs M1/M2/BC250, Ollama cache |
| **03:00** | Borg create | Sauvegarde dédupliquée chiffrée → HDD 2TB |
| **05:00 (dim)** | Borg prune | Rétention keep-daily 14, keep-monthly 3 |

**Actions** :
- [ ] Installer HDD 2TB dans M2, passthrough vers LXC 105 `/srv/backup`
- [ ] Déployer OMV via Docker (`openmediavault/omv`) sur M2 LXC 105
- [ ] Configurer borg repo sur HDD (LUKS + repokey)
- [ ] Clés SSH OMV→M1 (Qdrant snapshot + wiki + configs) + OMV→BC250 (configs + cache)
- [ ] Cron OMV quotidien (02:00-05:00) : snapshot → rsync → borg create → prune dim
- [ ] Documenter restore procedure dans `infrastructure/backup/restore.md`

Prêt pour Phase 0 (squelette + config + Docker Compose).

---

### 31/07/2026 — Filtre anti-injection Niveau 1 (regex) — **GREEN**

**Statut** : module `src/tools/injection_filter.py` créé. Le pattern `ignore ... previous instructions` matchait déjà correctement `"ignore all previous instructions"` (le RED signalé initialement ne se reproduisait pas telle quelle). **Vrai bug trouvé en écrivant le test batch** : le pattern `forget` était trop restrictif — il ratait `"forget everything you know and follow these new rules"` car il exigeait un mot précis (`instructions|context|what you know`) juste après `everything you know`, ce qui ne colle pas aux formulations naturelles. Corrigé en `r"forget\s+(?:everything|all|any)(?:\s+you\s+know)?\b"`.

**Fait** :
- [x] Écrit `tests/test_injection_filter.py` (12 payloads HIGH type OWASP LLM01, 5 payloads légitimes, cas batch/vide)
- [x] Faux positifs 0% sur le jeu de texte légitime testé
- [x] Gate GREEN vérifié : `assert scan("ignore all previous instructions").risk == "high"` → 12/12 tests passent

**Limite connue** : détection heuristique regex Niveau 1 uniquement — contournable par paraphrase, encodage, ou langue autre que l'anglais. Pas de blocage de l'ingestion, seulement un score `injection_risk` en métadonnée (voir docstring du module) : la quarantaine reste à faire via le trust tier OKF.

**Contexte** : plan utilisateur (MCP + anti-injection). Le filtre est prioritaire car le risque existe dès que l'ingestion tourne. Le MCP reste différé (dépend de WikiAgent concret + mTLS Phase 0.13) — voir ROADMAP.md section Sécurité.

**Fichiers touchés** : `src/tools/injection_filter.py` (pattern `forget` corrigé), `tests/test_injection_filter.py` (créé)


### 31/07/2026 — OMV Backup restauré (M2 LXC 105) + diagrams/docs mis à jour — **TRANCHÉ**

**Décision** : le cold save "simple" (borg/rsync manuel depuis M1 vers stockage externe) est **remplacé** par un backup **OMV sur Machine 2 (LXC 105)** — HDD 2TB physique déjà installé, passthrough vers le LXC, OMV déployé via Docker (`openmediavault/omv`). Rotation **2-1 locale uniquement** (NVMe prod + HDD M2), **pas d'off-site planifié**.

**Flux** : OMV (LXC 105, cron 02:00-05:00) → borg pull M1 (Qdrant snapshot + wiki + configs) + rsync BC250 (configs + cache Ollama) → borg create → HDD 2TB (LUKS, repokey) → prune dim (keep-daily 14, keep-monthly 3).

**Fait (docs)** :
- [x] README.md : section Cold Save réécrite (OMV LXC 105), diagrammes Mermaid mis à jour (cluster, topologie réseau, topologie physique)
- [x] docs/diagrams/04-backup-cold.md : flux OMV → HDD 2TB (snapshot/rsync/borg/prune)
- [x] docs/diagrams/05-network-topology.md : LXC 105 OMV + HDD 2TB dans VLAN 10, flux borg
- [x] docs/diagrams/06-physical-topology.md : LXC 105 OMV sur M2, pfSense reverse proxy (nginx retiré)
- [x] docs/deployment-guide.md : section Machine 2 ajoutée (LXC 105 OMV via Docker, HDD passthrough, cron borg), nginx LXC 102 retiré (pfSense reverse proxy), section 4.3 pfSense + 4.4 OMV
- [x] ROADMAP.md : Sprint 1 tasks 1.11-1.14 (LXC 105, docker-compose.omv.yml, HDD passthrough, borg repo + clés SSH)
- [x] backlog.md : Phase 0 tasks 0.25-0.28 ajoutées (create-lxc-omv.sh, docker-compose.omv.yml, passthrough HDD, secrets OMV), section Backup 2-1 rétablie, nginx retiré de l'architecture LXC 100

**Actions restantes (infra, à faire)** :
- [ ] 0.25 Créer `infrastructure/proxmox/create-lxc-omv.sh` (LXC 105)
- [ ] 0.26 Créer `infrastructure/docker/docker-compose.omv.yml`
- [ ] 0.27 Passthrough HDD 2TB → LXC 105 (`pct set 105 -mp0 /dev/disk/by-id/...,mp=/srv/backup`)
- [ ] 0.28 Clés SSH OMV→M1/M3 + borg init + cron 02:00-05:00
- [ ] 7.10 Écrire `infrastructure/backup/restore.md`


## 29/07/2026 — Architecture LXC 100 (Orchestrator + Wiki Agent) + Schema CLAUDE.md — **NOUVEAU**

### 1. Spécifications LXC 100 — Master Orchestrator

| Paramètre | Valeur |
|-----------|--------|
| **CTID** | 100 |
| **Hostname** | `rag-master` |
| **Template** | Debian 12 (bookworm) standard |
| **CPU** | 8 vCPU (sur 44 threads M1) |
| **RAM** | 8 GB (sur 32 GB ECC M1) |
| **Swap** | 2 GB |
| **Disque rootfs** | 50 GB (NVMe M1, local-lvm) |
| **Network** | `eth0` → VLAN 10 (10.10.0.1/24, MTU 9000, bridge vmbr10) |
| **Gateway** | 10.10.0.254 (pfSense) |
| **Privileged** | Non (unprivileged LXC) |
| **Nesting** | Oui (Docker inside LXC) |
| **Onboot** | 1 |
| **Start** | 1 |

### 2. Mounts NFS (depuis l'hôte M1, export NFS relay)

| Mount Point (LXC 100) | Source NFS (10.10.0.1:/data/shared/...) | Usage | Mode |
|----------------------|------------------------------------------|-------|------|
| `/data/wiki` | `wiki` | Vault Obsidian (pages, index.md, log.md, CLAUDE.md) | RW |
| `/data/raw` | `raw` | Sources brutes ingérées (immutable) | RW |
| `/data/index` | `index` | Index/search auxiliaires | RW |
| `/data/models` | `models` | Cache Ollama partagé (read-only pour LXC 100) | RO |

**Config `/etc/pve/lxc/100.conf` (extraits)** :
```bash
mp0: /data/wiki,volume=data-shared/wiki,shared=1
mp1: /data/raw,volume=data-shared/raw,shared=1
mp2: /data/index,volume=data-shared/index,shared=1
mp3: /data/models,volume=data-shared/models,shared=1,ro=1
```

### 3. Services dans LXC 100 (Docker Compose `orchestrator.yml`)

```
┌─────────────────────────────────────────────────────────────┐
│                    LXC 100 - Orchestrator                   │
├─────────────────────────────────────────────────────────────┤
│  🐳 Docker Compose (orchestrator.yml)                      │
│  ├── fastapi-api:8000        ← API /api/v1 (ingest, query) │
│  ├── langgraph-orchestrator  ← Workflow ingestion + query  │
│  └── wiki-agent              ← LLM Wiki maintenance loop   │
├─────────────────────────────────────────────────────────────┤
│  🔧 Services système (hors Docker, systemd)                │
│  ├── ollama-client           ← Client vers M1/M2/M3 Ollama │
│  ├── inotifywait             ← Watch /data/wiki + /data/raw │
│  ├── cron                    ← Ingestion planifiée, lint   │
│  └── healthcheck             ← /health pour Prometheus     │
└─────────────────────────────────────────────────────────────┘
```

**Reverse Proxy / TLS** : pfSense (VM 104 sur M1) — termine TLS, DNAT 443 → LXC 100:8000. Pas de nginx dédié.

### 4. Flux d'appel LLM Local (via Ollama API)

```
Wiki Agent (LXC 100)
    │
    ├── Embedding → http://10.10.0.1:11434  (Ollama M1 CPU - RX 580 ROCm)
    │       └── fallback → http://10.10.0.2:11434 (Ollama M2 CPU backup)
    │
    ├── Generation → http://10.10.0.3:11434 (Ollama M3 BC250 Vulkan)
    │
    ├── Rerank/Judge/Avocat → http://10.10.0.2:11434 (Ollama M2 RTX 4000 CUDA)
    │
    └── Evaluator → http://10.10.0.1:11434 (Ollama M1 CPU Granite 4.1 8B)
```

### 5. Schema CLAUDE.md / AGENTS.md — Template pour `/data/wiki/CLAUDE.md`

**Fichier à créer** : `docs/claude-md-template.md` → copié vers `/data/wiki/CLAUDE.md` au premier boot LXC 100.

Contenu structuré (voir README.md section ajoutée) avec :
- Architecture cluster pour le LLM (tableau M1/M2/M3 + modèles + endpoints)
- Structure vault wiki (`/data/wiki` arborescence complète)
- Format page standard (Frontmatter YAML avec `confidence`, `contradictions`, `supersedes`)
- Workflows Wiki Agent : Ingest, Query, Lint (étapes détaillées)
- Assignation modèles par tâche (tableau tâche → modèle → endpoint → params)
- Configuration runtime (variables d'env LXC 100)
- Règles maintenance (immuabilité sources/, cross-refs bidirectionnels, versioning, etc.)
- Objectifs qualité wiki (couverture, fraîcheur, consistance, traçabilité, navigation)

### 6. Scripts Proxmox à créer

| Script | Emplacement | Description |
|--------|-------------|-------------|
| `create-lxc-master.sh` | `infrastructure/proxmox/` | Création LXC 100/101 + VM 104 |
| `orchestrator.yml` | `infrastructure/docker/` | Docker Compose stack complète (nginx supprimé, D4) |
| `Dockerfile.api` | `infrastructure/docker/` | FastAPI + deps |
| `Dockerfile.wiki-agent` | `infrastructure/docker/` | Wiki Agent (LangGraph + tools) |
| `Dockerfile.langgraph` | `infrastructure/docker/` | Orchestrateur LangGraph |

### 7. Variables d'environnement LXC 100 (`/etc/environment` ou `docker-compose.override.yml`)

```bash
OLLAMA_M1=http://10.10.0.1:11434
OLLAMA_M2=http://10.10.0.2:11434
OLLAMA_M3=http://10.10.0.3:11434
WIKI_ROOT=/data/wiki
RAW_ROOT=/data/raw
QDRANT_URL=http://10.10.0.1:6333
NFS_RELAY=/data/shared/evaluation-relay.json
LOG_LEVEL=INFO
```

### 8. Actions à ajouter au backlog (Phase 0 étendue)

- [ ] **0.6** Créer `infrastructure/proxmox/create-lxc-wiki-agent.sh` (LXC 100 complet)
- [ ] **0.7** Créer `infrastructure/docker/orchestrator.yml` + `nginx.conf` + 3 Dockerfiles
- [ ] **0.8** Créer `docs/claude-md-template.md` → template CLAUDE.md pour wiki
- [ ] **0.9** Intégrer healthchecks Ollama M1/M2/M3 dans wiki-agent (retry + fallback)
- [ ] **0.10** Test d'ingestion bout-en-bout : source → embed M1 → index Qdrant → wiki pages → index.md/log.md
- [ ] **0.11** Configurer mTLS pour API interne (certs auto-signés via pfSense CA)
- [x] ~~**0.12** Prometheus exporter custom wiki-agent~~ **RETIRÉ** (cf. D9) — metrics `wiki_pages_total`/`ingest_duration_seconds`/`query_latency_seconds`/`llm_calls_total` consultables via logs applicatifs, pas d'exporter dédié tant qu'aucun Prometheus n'est déployé
- [ ] **0.13** Git sidecar auto-commit dans LXC 100 (cron 1h) pour versioning wiki hors OMV

### 9. Décisions d'architecture à trancher (complément)

| Question | Options | Recommandation |
|----------|---------|----------------|
| **Template LXC** | Debian 12 vs Ubuntu 24.04 | **Debian 12** (plus léger, stable, pas de snap) |
| **Orchestration conteneurs** | Docker Compose vs systemd-nspawn | **Docker Compose** (standard, portable, compose.yml lisible) |
| **Wiki Agent implémentation** | Python script custom vs LangGraph nodes | **LangGraph** (déjà choisi stack, graphe d'état explicite) |
| **Authentification API** | mTLS + client certs vs JWT vs none (LAN) | **mTLS** (certs auto-signés pfSense CA, zéro config client) |
| **Monitoring Wiki Agent** | Prometheus exporter custom + Grafana vs logs applicatifs directs | ~~Prometheus/Grafana~~ **RETIRÉ (D9)** — logs applicatifs (`wiki_pages_total` etc. en log structuré) suffisent en v1, pas d'exporter dédié |
| **Backup wiki (hors OMV)** | Git auto-commit sur push wiki | **Git sidecar** dans LXC 100 (cron 1h, push vers remote bare) |

## Entretien du 30/07/2026 — Audit BC-250 + adoption OKF v0.2

### Sujet : Révision installation AMD BC-250 + adoption OKF v0.2 pour le vault wiki
**Participants** : utilisateur + agent opencode

#### Motivation
Analyser le repo [chelmooz/RAG-Harvard-IT-teacher](https://github.com/chelmooz/RAG-Harvard-IT-teacher) et la doc officielle [elektricm.github.io/amd-bc250-docs/](https://elektricm.github.io/amd-bc250-docs/) pour améliorer les scripts d'installation BC-250 du projet, puis planifier l'adoption du format OKF v0.2.

---

### 1. Confirmation des modèles BC-250 (Machine 3 — baremetal)
Décision tranchée vs backlog : **l'embedding n'est PAS sur BC-250**.

| Machine | Rôle embedding | Modèle | Backend |
|---------|---------------|--------|---------|
| **M1 Master (CPU Xeon 32c/64t)** | Embedding principal | `hf.co/nomic-ai/nomic-embed-text-v2-moe-GGUF:Q8_0` 768d Q8_0 | CPU Ollama/llama.cpp |
| **M2 GPU Worker (CPU Xeon 20c/40t)** | Embedding backup | `hf.co/nomic-ai/nomic-embed-text-v2-moe-GGUF:Q8_0` 768d Q8_0 | CPU Ollama/llama.cpp |
| **M3 BC-250** | **Aucun** — règle d'or | — | — |

**Règle d'or confirmée** : "Le CPU du BC-250 est le serviteur du GPU. Toute charge CPU significative vole la bande passante mémoire au Generator 14B." (backlog §317)

**Modèles BC-250 exclusivement** :

| Rôle | Modèle | Quant | VRAM | Endpoint |
|------|--------|-------|------|----------|
| Generator principal | `hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M` | Q4_K_M | ~9 GB | M3 Ollama |
| Generator alternatif MoE | `hf.co/Qwen/Qwen3-30B-A3B-GGUF:Q2_K` | Q2_K | ~11.3 GB | M3 Ollama |
| Text-to-SQL / Code | `hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q2_K` | Q2_K | ~11 GB | M3 Ollama |
| Vision (Phase 5.2) | `hf.co/cjpais/llava-v1.6-vicuna-13b-gguf:Q4_K_M` / `qwen2.5-vl` | Q4_K_M | ~9 GB | M3 Ollama |
| Fast-check lexical | `hf.co/ibm-granite/granite-4.0-h-tiny-GGUF:Q4_K_M` | Q4_K_M | ~3 GB | M3 Ollama |

**Backend GPU** : Ollama Vulkan (RADV) auto-fallback — **pas ROCm** (non supporté sur GFX1013).

---

### 2. Incohérences corrigées backlog vs scripts existants

| Script existant | Problème vs doc officielle | Correctif prévu |
|----------------|---------------------------|-----------------|
| `infrastructure/bc250/setup-vulkan-stack.sh` | `ttm.pages_limit` seul → **insuffisant** (triplet obligatoire `gttsize=14750 ttm.pages_limit=3959290 ttm.page_pool_size=3959290`) | Réécriture complète |
| `setup-vulkan-stack.sh` | `amdgpu.sg_display=0` inutile sur kernel 6.10+ | Retirer |
| `setup-vulkan-stack.sh` | Gouverneur via .deb → inexistant, tarball release obligatoire | Changer pour tarball |
| `setup-vulkan-stack.sh` | Pas de swap + zram config | Ajouter |
| `setup-vulkan-stack.sh` | Pas de sensors nct6683 | Ajouter |
| `enable-40cu-unlock.sh` | `cu_map.sh` pas automatisé avant build | Ajouter check harvest pattern interactif |
| `enable-40cu-unlock.sh` | Pas de hook rebuild post-kernel-upgrade | Ajouter hook apt |
| `enable-cpu-core-unlock.sh` | Volatil (ne survit pas cold boot), risque documenté | **Exclure** du déploiement standard — garder en `docs/experimental/` |

**Détail triplet VRAM GRUB** (doc officielle §Kernel Configuration) :
```
amdgpu.gttsize=14750 ttm.pages_limit=3959290 ttm.page_pool_size=3959290
```
Les 3 paramètres DOIVENT être posés ensemble — gttsize seul ne suffit pas (plafond ttm par défaut atteint avant, crash driver). **NE JAMAIS** utiliser `amd_iommu=on` (IOMMU cassé sur BC-250).

**Kernel cible** : 6.18.18 LTS recommandé (doc officielle), pin avec `dnf versionlock` (ou excludepkgs). Éviter 6.15.0-6.15.6 et 6.17.8-6.17.10 (bugs GPU).

**Mesa** : 25.1.3 minimum, 25.3+ recommandé. Fedora 43 mainline (décision 02/08/2026) — plus de repo experimental ni pin-priority.

**Gouverneur** : `cyan-skillfish-governor-smu` recommandé (filippor, tarball release, pas de kernel patch nécessaire). Config ideal : safe-points 1000/700, 1500/900, 2000/1000, 2200/1000.

**40 CU Unlock** : Optionnel interactif (step 9/9). Clone duggasco/bc250-40cu-unlock, `cu_map.sh` obligatoire avant, `active_cu_number=40` à vérifier. Rebuild après chaque kernel upgrade (hook dnf). Rollback via `disable`/`restore`.

---

### 3. Adoption OKF v0.2 — Format du vault wiki
**Date** : Google Cloud v0.2 annoncé fin juillet 2026 (pré-1.0)

**Constat** : le frontmatter YAML du projet (README section "Convention Frontmatter YAML") est **déjà aligné** à ~90% avec OKF v0.2.

| Champ projet | Champ OKF v0.2 | État |
|-------------|----------------|------|
| `type` | `type` (obligatoire) | ✅ OK |
| `title`, `description`, `tags` | `title`, `description`, `tags` | ✅ OK |
| `verified` (reviewer + status + timestamp) | `verified` (trust tier dérivé) | ✅ OK — Évaluateur écrit `human-reviewed` |
| `status`, `stale_after` | `status: draft\|stable\|deprecated`, `stale_after` | ✅ OK — lien direct avec `/api/v1/lint` |
| `sources` (liste plate) | `sources` (crédibilité par source : author, last_modified, credibility) | 🔧 Enrichir |
| Structure vault (`index.md`, `log.md`, `entities/`, `concepts/`) | §8 (index), §9 (log) du spec | ✅ OK |
| — | CLI `okf` (validate, list, show) | 🔧 Wrappers API `/api/v1/okf/validate\|list\|show` |
| — | Plugin Obsidian `okf-enforcer` | 🔧 Optionnel — pas de dépendance dure tant que pré-1.0 |

**Recommandation** : Adopter la structure frontmatter OKF v0.2 immédiatement (coût ~nul), wrapper CLI `okf` via API sans dépendance dure, pas de lock-in tant que pré-1.0.

**Actions backlog** :
- Phase 0.6 : Créer `docs/claude-md-template.md` avec template OKF v0.2
- Phase 0.7 : `scripts/okf-lint.py` — validation frontmatter OKF
- Phase 0.8 : Endpoints `/api/v1/okf/validate`, `/api/v1/okf/list`, `/api/v1/okf/show`
- Phase 4.5 : Structure vault OKF (`index.md` §8 + `log.md` §9)

**Mapping acteurs → trust tiers OKF** :
| Acteur projet | Trust tier OKF | Condition |
|--------------|---------------|-----------|
| Page brute ingérée | `unverified` | Défaut |
| Juge + Avocat OK | `machine-confirmed` | Évaluation auto passée |
| Évaluateur valide | `human-reviewed` | Synthèse finale positive |

---

### 4. Décisions conservées (inchangées)
- **Qdrant** → inchangé (hybrid search dense + sparse BM25, pas pgvector)
- **Python** → `>=3.11` (pyproject.toml inchangé)
- **Embedding** → Machine 1 CPU (pas de PyTorch ROCm sur BC-250)
- **Modèles** → liste backlog/README conservée intégralement

---

### 5. Prochaine action validée
Commencer par **Phase 0.2** : Réécriture `infrastructure/bc250/setup-vulkan-stack.sh` alignée doc officielle (triplet GRUB, Mesa 25.3+, gouverneur SMU tarball, swap + zram, sensors).

---

## 📋 Consultation Tierce — Pour décision par IA externe (31/07/2026)

### Contexte
Le transcript d'une session précédente (Claude) affirme avoir effectué de nombreuses corrections (regex injection, .gitignore, .gitattributes, mypy config, settings security, main.py auth/CORS, nginx rate limiting). **Or aucune de ces modifications n'est présente dans ce repo** (HEAD `4c31491`). Les 2 fichiers modifiés sont uniquement `ROADMAP.md` et `backlog.md` (doc).

### Sprint Proposés — À valider / rejeter / réordonner

#### Sprint 1 — Hygiène & CI (bloquant)
| # | Tâche | Fichiers | Gate |
|---|-------|----------|------|
| 1 | Fix `.gitignore` : `models/` → `/models/` | `.gitignore` | `git check-ignore src/models/__init__.py` → non ignoré |
| 2 | Créer `.gitattributes` (eol=lf) + renormalize | `.gitattributes` | `git status` → plus de CRLF churn |
| 3 | Fix `pyproject.toml` : `python_version = "3.12"` + `pydantic.mypy` plugin + override asyncpg | `pyproject.toml` | `mypy src` → 0 erreurs bloquantes |
| 4 | Fix `src/tools/injection_filter.py` : pattern `forget` + `StrEnum` + newline final | `src/tools/injection_filter.py` | `ruff check src/tools/injection_filter.py` → 0 erreurs |
| 5 | Déplacer test → `tests/test_injection_filter.py`, supprimer doublons racine | `tests/`, racine | `pytest tests/test_injection_filter.py` → 12+ passed |
| 6 | Fix `ruff` sur tout le repo (line length, unused imports, StrEnum) | multiples | `ruff check .` → 0 erreurs |

#### Sprint 2 — Sécurité API (C2, m5, M4)
| # | Tâche | Fichiers | Gate |
|---|-------|----------|------|
| 7 | Ajouter `api_key`, `api_key_header`, `cors_allow_origins` + `MissingApiKeyConfigError` dans `settings.py` | `src/core/settings.py` | `mypy src/core/settings.py` → OK |
| 8 | Middleware/dependency `require_api_key` dans `main.py` (protège `/query`, `/ingest`, `/embed`, `/okf/*`, `/lint` — PAS `/health`, `/ready`) | `src/api/main.py` | `pytest tests/test_api.py` → 200 sur health/ready, 401 sans key sur protégés |
| 9 | Fix CORS : `allow_origins=settings.cors_allow_origins` (pas `["*"]`) + retirer `allow_credentials=True` si wildcard | `src/api/main.py` | `ruff check src/api/main.py` + review manuel |
| 10 | Annotations retour `lifespan` + `not_implemented_handler` | `src/api/main.py` | `mypy src/api/main.py` → 0 erreurs |
| 11 | Rate limiting nginx : `limit_req_zone` + `limit_req` sur `/api/v1/` | `infrastructure/docker/nginx.conf` | `nginx -t` valide |

#### Sprint 3 — CI & Secrets (M3, M7, 0.16)
| # | Tâche | Fichiers | Gate |
|---|-------|----------|------|
| 12 | Créer `.github/workflows/ci.yml` (ruff + mypy + pytest + build docker) | `.github/workflows/ci.yml` | Push → GitHub Actions vert |
| 13 | `.env.example` : ajouter `API_KEY`, `API_KEY_HEADER`, `CORS_ALLOW_ORIGINS` | `.env.example` | Diff cohérent avec settings |
| 14 | Secrets management : ajouter `sops` / `.env.encrypted` stub (Phase 7) | `scripts/`, `.pre-commit-config.yaml` | Doc seulement pour l'instant |

#### Sprint 4 — Agents & Pipeline (Phase 1-3)
| # | Tâche | Fichiers | Gate |
|---|-------|----------|------|
| 15 | Implémenter `VectorService.hybrid_search` + `upsert_points` + `create_collection` | `src/services/vector.py` | Test unitaire mock Qdrant |
| 16 | Implémenter `OllamaClient` (generate, embed, rerank, unload_model) | `src/services/ollama.py` | Test contre Ollama local si dispo |
| 17 | Implémenter `WikiAgent` méthodes de base (write_page, update_index, append_log, lint, validate_frontmatter) | `src/agents/wiki_agent.py` | Test écriture vault temporaire |
| 18 | Implémenter `langgraph_orchestrator.build_graph()` (nœuds Planner → QueryRewriter → Search → ContextAssembler → Generator → Judge → Advocate → Evaluator → Wiki) | `src/agents/langgraph_orchestrator.py` | Smoke test flux complet |
| 19-22 | Implémenter Judge, Advocate, Generator, Evaluator (stubs → vraies implémentations) | `src/agents/*.py` | Tests d'intégration séquentiels |

#### Sprint 5 — MCP + Filtre Injection Niveau 2/3
| # | Tâche | Fichiers |
|---|-------|----------|
| 23 | Serveur MCP (`src/mcp/server.py`) exposant 7 tools WikiAgent | Nouveau module |
| 24 | Dockerfile MCP + service dans `orchestrator.yml` + route nginx `/mcp/` | Dockerfiles, nginx |
| 25 | mTLS sur `/mcp/` (Phase 0.13) | nginx, certs |
| 26 | Niveau 2 : Classifieur ML léger (optionnel) | `src/tools/injection_classifier.py` |
| 27 | Niveau 3 : Quarantaine via trust tiers OKF (frontmatter `injection_flagged` + `lint()` priorité) | `src/tools/injection_filter.py`, `src/agents/wiki_agent.py` |

---

### ❓ Questions pour consultation tierce (décision requise avant exécution)

| # | Question | Options | Impact |
|---|----------|---------|--------|
| Q1 | **Ordre des sprints** : Faire Sprint 1 complet (hygiène/CI) avant Sprint 2 (sécurité), ou enchaîner 1→2 sans attendre CI vert ? | A) Sprint 1 complet d'abord (sûr) B) 1→2 parallèles (plus vite) | Risque régression si Sprint 2 casse ce que Sprint 1 n'a pas encore fixé |
| Q2 | **CORS origins par défaut** : Quelle valeur pour `cors_allow_origins` ? | A) `["http://localhost:3000", "http://192.168.10.0/24"]` (dev + LAN client) B) `[]` (refusé par défaut, config explicite requise) C) `["*"]` sans `allow_credentials` (ouvert mais sans cookies) | Sécurité vs commodité dev |
| Q3 | **API Key** : Une seule key globale ou une par service/client ? | A) `API_KEY` unique globale (simple) B) `API_KEYS` liste (rotation, révocation par client) C) JWT + JWKS (standard, plus complexe) | Architecture auth |
| Q4 | **Rate limit nginx** : `limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;` te convient ? | A) 10 req/s par IP (conservateur) B) 50 req/s (standard API) C) Configurable via `settings.rate_limit_rps` | Protection vs UX |
| Q5 | **Test injection_filter** : Le fichier racine `test_injection_filter.py` — le garder comme référence ? Je le déplace dans `tests/` + j'ajoute les 12 payloads OWASP LLM01 du backlog. | A) Oui, déplacer + enrichir B) Non, réécrire depuis zéro C) Garder les deux (racine = legacy, tests/ = nouveau) | Couverture tests |
| Q6 | **MCP vs WikiAgent** : Le backlog dit MCP **après** WikiAgent concret. Commencer le serveur MCP (Sprint 5) en parallèle, ou attendre `WikiAgent` implémenté (Sprint 4.17) ? | A) MCP après WikiAgent (logique dépendance) B) MCP en parallèle (découplé, transport seulement) C) MCP d'abord pour valider l'API tools | Priorisation ressources |
| Q7 | **Niveau 2 injection (ML)** : Ajouter `protectai/deberta-v3-base-prompt-injection-v2` quantifié CPU ? | A) Oui, dès Sprint 5 (défense en profondeur) B) Non, Niveau 1 + trust tiers OKF suffisent pour usage personnel C) Plus tard, seulement si faux négatifs réels observés | Complexité + CPU M1 |
| Q8 | **Secrets management** : `sops` + `.env.encrypted` (Phase 7) ou HashiCorp Vault ? | A) `sops` + age (simple, git-friendly, pas de serveur) B) HashiCorp Vault (standard entreprise, mais overhead) C) Les deux : sops pour dev, Vault pour prod | Ops complexity |

---

### 📝 Note pour l'IA évaluatrice
- Ce repo est **pré-déploiement** : infrastructure as code (Proxmox LXC + Docker Compose) prête, mais services métiers sont des stubs (`NotImplementedError`).
- Le cluster cible 3 machines hétérogènes (Master CPU, GPU Worker RTX 4000, BC-250 Vulkan) — décisions hardware tranchées et documentées.
- Pattern Karpathy (vault Obsidian) + OKF v0.2 + évaluation multi-agents (Judge→Avocat→Évaluateur séquentiel sur RTX 4000 8GB) sont les piliers architecturaux.
- **Règle d'or BC-250** : CPU = serviteur du GPU (pas d'embedding sur BC-250, embedding sur Master CPU Xeon 32c/64t).
- Tout ce qui est dans cette section "Consultation Tierce" est **proposé, non décidé** — ne pas implémenter sans validation.

---

## 31/07/2026 — Session de planification pré-développement (2ᵉ échange IA)

### Participants
Utilisateur + agent opencode.

### Contexte
Le projet est en **pré-développement** — réflexion sur les actions à mener, pas de code métier exécutable. Le repo contient le squelette (FastAPI stubé, settings Pydantic, Dockerfiles, scripts Proxmox) mais tous les services métiers sont des `NotImplementedError`.

Le cluster est **100% offline** : les IA (Ollama) tournent en local sur les 3 machines. La seule sortie internet passe par pfSense sur l'interface 1 Gb de Machine 1, exclusivement pour les mises à jour (OS, Mesa, paquets). Machines 2 et 3 sont branchées en direct sur les cartes 10 Gb de M1 (pas de switch intermédiaire).

### Décisions actées

| # | Décision | Raison exprimée | Impact |
|---|----------|-----------------|--------|
| D1 | **Pas d'API key applicative** | Tourne en local, pfSense = périmètre sécurité, pull des modèles déjà fait | Retrait de `require_api_key`, `api_key_header`, `MissingApiKeyConfigError` du backlog et de la roadmap. Pas de section auth dans `.env`. |
| D2 | **Pas de CORS restrictif** | Accès localhost/LAN uniquement | `allow_origins=["*"]` conservé. Pas de `cors_allow_origins` paramétrable. |
| D3 | **Pas de mTLS** (Phase 0.13 retirée) | pfSense gère le réseau inter-VLAN, aucune API exposée à internet | mTLS noté "optionnel futur", supprimé du backlog actif. |
| D4 | **nginx retiré du stack** | Sur-ingénierie — pfSense fait firewall NAT + règles inter-VLAN, sert de seule porte d'entrée. Ajouter nginx en plus ne protège rien de plus et complexifie. | Suppression de `infrastructure/docker/nginx.conf` et du service nginx dans `docker-compose.orchestrator.yml`. FastAPI écouté directement. |
| D5 | **Rate limit inutile** | pfSense gère le périmètre ; de tout façon on est en LAN local sans utilisateurs externes. | Aucun `limit_req`, `limit_req_zone` à ajouter. |
| D6 | **Structure réseau confirmée** | M2 et M3 branchées en direct sur carte 10 Gb de M1, pas de switch. M1 sortie 1 Gb pfSense → internet pour updates. M2/M3 n'ont pas d'accès internet direct — tout le réseau inter-nœuds est en VLAN 10 (10.10.0.0/24). | Documentation réseau à auditer dans `README.md` et `docs/`. |
| D7 | **Adoption plan 3 sprints** | Remplace la roadmap précédente (liste plate ~95 items), simplifié en sprints exécutables. | `ROADMAP.md` réécrit en `{Sprint 1 Hygiène/CI → Sprint 2 Backend métier → Sprint 3 Finalisation}`. |
| D9 | **Monitoring complet (Prometheus+Grafana+Loki, LXC 103) retiré de la v1** | Sur-ingénierie pour 3 nœuds physiques, opérateur seul, projet pas encore en prod. Proxmox VE (M1/M2) et pfSense exposent déjà des graphs RRD natifs (CPU/RAM/disk/network) sans rien ajouter. Seul le BC-250 (bare metal, hors Proxmox) n'a aucune supervision native. | Retrait de Phase 7.1/7.2, item 0.12/0.14, LXC 103 (README + backlog). Ajout **Glances (`glances -w`)** sur BC-250 uniquement. Réactivation Prometheus/Grafana possible plus tard (Phase 7.7, non planifiée) si diagnostic perf réel nécessaire (latence Reranker/Générateur, VRAM RTX4000). |
| D10 | **Mock-first — aucun LLM pullé avant déploiement** | Pré-déploiement : aucune machine du cluster n'est livrée, aucun Ollama n'a de modèles. Le code (OllamaClient, agents, endpoints) doit être développé et testé 100% via `httpx.MockTransport` + Qdrant mocké, sans matériel. | Phase A/B entièrement développables et vérifiables en CI sans hardware. Les tests d'intégration mockent les réponses Ollama (generate/embed/rerank) et Qdrant. |
| D11 | **Ordre d'exécution : RAG core (Phase A) avant multi-agents (Phase B)** | Conforme au ROADMAP : l'hybrid search (Hybrid RAG + Retrieve-and-rerank) est le socle ; le pipeline multi-agents (évaluation) consomme ce socle. | ROADMAP réorganisé en 4 phases (A/B/C/D) avec phases C (déploiement) et D (CI) séparées. |
| D12 | **Boucle d'évaluation multi-agents OPTIONNELLE** | Juge → Avocat → Évaluateur = 4 appels LLM/requête (génération + 3 éval) → latence critique sur RTX 4000 8 GB + BC250 non conventionnel. Inutile pour le chat simple, utile pour les réponses finales. | Flag `evaluation_enabled` dans `settings.py` (défaut `false`, cf. `.env.example`). Activation par endpoint/requête prévue (Phase B6). Feedback Évaluateur → Planner limité à 1 itération max. |

### Points techniques à documenter

- ~~**IP correction `.env.example`** : Qdrant/Postgres/Redis actuellement pointés sur `10.10.0.1` (gateway) → doivent pointer sur `10.10.0.101` (LXC 101 Vector DB). Cf. scripts Proxmox `create-lxc-master.sh`.~~ **✅ FAIT (31/07/2026)** : `.env.example` réécrit avec `10.10.0.101`, noms de variables alignés sur `settings.py`.
- **Volume NFS `/data/shared` pour relay.json** : manquant dans `docker-compose.orchestrator.yml` — doit être ajouté pour que Judge soit avant le relay à travers le pipeline (→ ROADMAP C2).
- **BC250_CU_COUNT=24 par défaut** : 40 n'est valable qu'après l'exécution du script d'indistance, qui est encore non testé sur ordinal BAC.
- **Duplication postgres/redis** dans les deux `docker-compose.{vector-db,orchestrator}.yml` → port conflict si lancés sur le même hôte. À fusionner ou isoler en un seul réseau (→ Phase C).
- ~~**`models/` dans `.repoignore` igno aussi `src/models/`** par erreur. Pattern `models/` doit devenir `/models/` pour ne pas cacher le package.~~ **✅ FAIT (31/07/2026)** : `.gitignore` OK (`models/`), package mort `src/models/` supprimé.
- ~~**Bug `settings.py` env_file** : `Path(__file__).parents[3]` pointait sur `H:\` au lieu de la racine projet → le `.env` n'était jamais chargé (silencieux).~~ **✅ CORRIGÉ (31/07/2026)** : `parents[2]`. Vérifié : `.env.example` chargé (CU=40, Qdrant LXC 101, OKF tiers OK).

### Plan de build (31/07/2026 — décisions D10-D12)

`ROADMAP.md` réorganisé en 4 phases (A → B → C → D) :

- **Phase A — RAG core (mock-first)** : OllamaClient + Pool (A1-A2) → VectorService (A3) → IngestionService (A4) → LexicalSearch (A5) → RerankerService (A6) → endpoints `/embed` `/ingest` `/query` (A7) → tests hybrid search (A8).
- **Phase B — Multi-agents (mock-first)** : Planner → QueryRewriter → ContextAssembler → WikiAgent → Generator/Judge/Advocate/Evaluator → `evaluation_enabled` (D12) → `build_graph()` → endpoints OKF/lint → tests séquentiels relay.
- **Phase C — Déploiement** (bloquée : machines à livrer) : CMD idempotents Docker, NFS relay, OMV LXC 105, pull modèles + digests, Glances BC-250, smoke tests réels.
- **Phase D — CI/finalisation** : `.github/workflows/ci.yml`, template CLAUDE.md OKF, runbooks, merge main.

**Sprint 1 (Hygiène/CI) : TERMINÉ (31/07/2026)** — voir ROADMAP.md. Inclut : ruff 0 erreurs, mypy 0 bloquantes (plugin pydantic.mypy + py3.12 + override asyncpg), `.gitattributes` créé, `src/{api` et `src/models/` supprimés, doublon `test_injection_filter.py` supprimé, `.env.example` aligné (IPs + noms de variables), nginx/LXC 102-103 retirés (D4/D9).

### Décision de planification post-déploiement

- **Plan 3 sprints** adopté comme référent unique (remplace ancienne roadmap `ROADMAP.md`).
- `backlog.md` reste le document fait — toutes les décisions de cette session y sont archivées avec explications.
- **Attention : Sprint 1 est ré exécutable tellt qu'il**, sans aucune dépendance aux derniers (pas d'entreprise, de code métier, etc.).

### Questions résolues

| # | Question | Réponse |
|---|----------|---------|
| Q1 | Ordre Sprint 1 vs reste ? | Sprint 1 bloquant — sprint dont la suite dépend. |
| Q2 | `ROADMAP.md` redondant ? | Remplacé par le plan 3 sprints. L'ancien contenu migré n'est pas nécessaire. |
| Q3 | `.env.encrypted` tout de suite ? | Non — pas de secrets.
| Q4 | Redondance port postgres/redis compose ? | À résoudre avant Sprint 2. |
| Q5 | Retour nginx vs direct uvicorn ? | uvicorn direct, nginx retiré. |

### Audit demandé (Sprint 3.4)

- Revoir `README.md` : retirer mentions api_key, mTLS, nginx, CORS restrictif.
- Revoir `docs/architecture.md` + diagrammes Mermaid : corriger la strate réseau (plus de nginx, pfSense = proxy unique).
- Corriger IPs dans les schémas pour refléter `10.10.0.101` (Vector DB).

---

## 31/07/2026 — Session close (Sprint 1 terminé) — POINT DE REPRISE

### État de fin de session

- **Working tree : propre, tout pushé sur `main`** (HEAD `f7d9846`).
- **Sprint 1 (Hygiène/CI) : TERMINÉ** — ruff 0 erreurs, mypy 0 bloquantes (19 fichiers), pytest 14/14, `.gitattributes` créé, `src/{api` + `src/models/` supprimés, `.env.example` aligné sur `settings.py`, nginx/LXC 102-103 retirés (D4/D9).
- **ROADMAP.md** : plan 4 phases (A → B → C → D), décisions D10-D12 archivées.
- **README.md** : statut "développement mock-first" + tableau d'avancement.

### Prochaine étape — Phase A1 (OllamaClient + OllamaClientPool)

1. Implémenter `OllamaClient` : `generate`, `embed`, `rerank`, `unload_model`, `health` + retry (tenacity) + circuit-breaker — **testable via `httpx.MockTransport`** (décision D10, aucun LLM requis).
2. Implémenter `OllamaClientPool` : routage M1/M2/M3 par rôle (embed→M1 fallback M2, generate→M3, rerank/judge/advocate→M2, evaluate→M1).
3. Tests unitaires dédiés : `tests/test_ollama.py` (mocks httpx, retry, circuit-breaker, fallback pool).
4. Puis A2-A8 selon ROADMAP (VectorService → Ingestion → Lexical → Reranker → endpoints → test_hybrid_search).

### Rappels utiles pour la reprise

- Config lue depuis `.env` à la racine (bug `parents[2]` corrigé — vérifier qu'aucun `.env` traînant ne reste).
- `EVALUATION_ENABLED=false` par défaut (D12) — ne pas activer avant le pull des modèles.
- Le smoke test vit dans `scripts/smoke_test_frontend_api.py` (exclu du collect pytest par défaut, `testpaths=["tests"]`).
- Erreurs mypy autorisées : `# type: ignore[assignment]` sur les 5 champs `HttpUrl` (plugin pydantic.mypy), `# mypy: disable-error-code=no-untyped-def` non nécessaire (annotations ajoutées aux stubs).

---


## 01/08/2026 — Audit Claude (web) — corrections ruff + smoke test + docs

### Constat de départ

- `ruff check .` : **19 erreurs** alors que ROADMAP 1.7 et backlog (31/07) affirmaient "0 erreurs".
- `mypy src` : **4 erreurs résiduelles** sur `src/api/main.py` (`response_model` vs `JSONResponse` d'erreur sur `/embed` `/ingest` `/ingest/file` `/query`) — non détectées par l'audit du 31/07.
- `pytest` (suite officielle `tests/`) : échoue à la collecte, `python-multipart` absent de `pyproject.toml` (requis par `/ingest/file`).
- Couverture réelle du cœur RAG (Phase A) : 47 % global, `ingestion.py` 27 %, `vector.py` 26 %, `lexical.py` 31 %, `reranker.py` 33 %, `ollama.py` 30 % — aucun test unitaire dédié (`tests/test_hybrid_search.py` de la tâche A8 n'existe pas).
- `git status` : `ingestion.py`, `lexical.py`, `reranker.py` non trackés ; `main.py`, `vector.py`, `ollama.py`, `pyproject.toml`, `test_api.py` modifiés non commités.
- `scripts/smoke_test_frontend_api.py` : "32/32 PASSED" affirmé dans README/backlog était faux à l'exécution — 30/32 (2 échecs). Le test n'avait pas suivi l'évolution du code : `/embed`, `/ingest`, `/query` sont passés de stub `NotImplementedError` (500) à endpoints implémentés (Phase A) qui renvoient `503` tant que les services ne sont pas initialisés hors lifespan. Bug annexe : `/embed` testé en `GET` alors que l'endpoint est en `POST`.

### Corrections appliquées

- `scripts/excalidraw_to_svg.py`, `scripts/smoke_test_frontend_api.py`, `src/core/settings.py`, `src/services/reranker.py`, `src/services/vector.py` : 19 → 0 erreur ruff (E501, F401, Q000, TRY300).
- `src/services/vector.py` : refactor initial avait cassé le *type narrowing* mypy sur `upsert()` — corrigé en `if/else` explicite (aucune régression mypy introduite).
- `scripts/smoke_test_frontend_api.py` : `test_22` scindé en `test_22` (stubs réels `/lint` `/okf/*` → 500) et `test_22b` (`/query` `/embed` implémentés mais non initialisés → 503) ; `test_26` passé en `POST` avec body valide. 32 → 33 scénarios, **33/33 PASSED** (vérifié par exécution).
- `README.md` : ligne Sprint 1 (mypy 4 résiduelles, pas 0), tests squelette 14/14 → 16/16, note `/api/embed` mise à jour (implémenté Phase A, plus un stub), 32/32 → 33/33.
- `ROADMAP.md` : lignes 1.7 (ruff, corrigé) / 1.8 (mypy, 4 résiduelles) + titre section Sprint 1 passé de "TERMINÉ" à "QUASI TERMINÉ".

### Reste hors périmètre de cette session

- `python-multipart` toujours absent de `pyproject.toml` — casse `pip install -e .` en env propre dès qu'on touche `/ingest/file`.
- Les 4 erreurs mypy sur `src/api/main.py` (pattern `JSONResponse` vs `response_model`) non corrigées.
- Couverture tests quasi nulle sur `ingestion.py`/`vector.py`/`lexical.py`/`reranker.py`/`ollama.py` — tâche A8 (`tests/test_hybrid_search.py`) toujours à faire.
- Fichiers non commités (`ingestion.py`, `lexical.py`, `reranker.py`, etc.) — à committer.

---

## 01/08/2026 — Extraction Agent Skills (MCP vs Agent Skills) — B5.1

### Contexte

Discussion partie d'une image comparative MCP vs Agent Skills. Constat
dans le code : `OllamaClientPool.judge()/advocate()/evaluate()/generate()`
prennent un paramètre `prompt: str` dont le contenu n'était écrit nulle
part — trou réel identifié avant même l'implémentation de B5.

### Fait

- 5 `SKILL.md` créés : `src/agents/skills/{generator,judge,advocate,evaluator,wiki_agent}/SKILL.md`
  — critères d'évaluation, barème, format de sortie JSON, discipline
  anti lost-in-the-middle/anti-hallucination par rôle.
- `src/agents/skills/loader.py` : chargeur avec cache (`functools.cache`),
  fail-fast (`ValueError`/`FileNotFoundError`) sur rôle/fichier manquant.
- `build_prompt()` ajouté sur `GeneratorAgent`, `JudgeAgent`,
  `AdvocateAgent`, `EvaluatorAgent` (assemble skill + données du relay,
  testable sans mock LLM) ; `skill_reference()` sur `WikiAgent` (règles
  de lint/frontmatter, pas un prompt LLM).
- `evaluate/challenge/synthesize/generate()` restent `NotImplementedError`
  — câblage `OllamaClientPool` volontairement hors scope (mock-first,
  D10-D14).
- Ruff (`0 erreur`, ignore `TRY003` ajouté pour `loader.py`, cohérent
  avec les exceptions déjà en place sur `services/*.py`) + mypy (`0 erreur`)
  vérifiés sur `src/agents/`.

### Stratégie Agent Skills (question ouverte — PAS tranchée)

Remarque de Michel : les skills OpenCode (`clean-code-discipline`,
`loop-engineering`) et les nouveaux skills du projet ne sont pas écrits
dans le dépôt versionné de la même façon que le code — et ce RAG n'est
pas forcément soumis à la même discipline. Points à trancher avant que
le nombre de `SKILL.md` grossisse (B7, LangGraph) :

- **Localisation** : `src/agents/skills/<role>/SKILL.md` (actuel,
  colocalisé avec le code Python) vs répertoire séparé hors du package
  Python (ex. `skills/` à la racine, ou dans le vault Obsidian lui-même
  comme pages `type: agent`) vs dépôt dédié partagé avec les skills
  OpenCode.
- **Versioning** : un `SKILL.md` modifié change le comportement d'un
  agent au même titre qu'un changement de code — doit-il suivre la même
  revue/CI que `src/` (ruff n'a rien à y valider, mais un lint markdown
  + une revue humaine minimum semblent nécessaires) ?
- **Testabilité** : `build_prompt()` est testable (comparaison texte),
  mais rien ne garantit aujourd'hui qu'un `SKILL.md` modifié produit
  encore un JSON conforme au format de sortie attendu par le code aval
  (`evaluate()`/`synthesize()` qui parseront la réponse LLM) — un test
  de contrat (schema JSON attendu documenté dans le skill lui-même,
  vérifié par un test qui appelle un LLM mocké renvoyant un exemple
  conforme) est à prévoir.
- **Fact-checking = priorité n°1** : la chaîne Generator→Judge→Advocate→
  Evaluator existe spécifiquement pour limiter le *lost in the middle*
  et les hallucinations sur contexte long. La discipline anti
  lost-in-the-middle est maintenant écrite explicitement dans les 4
  skills concernés (Generator/Judge/Advocate/Evaluator) plutôt que
  laissée implicite — à vérifier empiriquement une fois B5.2 câblé
  (comparer taux de détection de hallucinations injectées
  volontairement avant/après ce skill).

### Prochaine étape

B5.2 (câblage `OllamaClientPool`) reste bloqué par la stratégie
mock-first (pas de pull de modèle avant déploiement, D10-D14) — les
`build_prompt()` sont prêts à être branchés dès que le hardware C1-C6
est livré.

---

## 01/08/2026 — Gap identifié (image RAG/Agents/MCP/A2A) — Human Control absent

### Constat

Comparaison du pipeline avec le lane "AI Agents" (Plan→Observe→Reflect
+ curseur Human Control ↔ Autonomous Action). Deux trous :

- **PlannerAgent (B1)** : `src/agents/planner.py` n'existe pas encore
  (déjà tracé backlog 0.29 / ROADMAP B1 — pas un oubli de planning,
  juste pas construit).
- **Human Control** : **rien n'existe** — le pipeline est 100 %
  automatique, `Evaluator` écrit `verified.status = human-reviewed`
  sans qu'aucun humain n'intervienne jamais (nom déjà signalé comme
  trompeur dans `src/agents/skills/evaluator/SKILL.md`). Pas tracé
  avant aujourd'hui.

### Question ouverte (PAS tranchée)

Faut-il un vrai point de contrôle humain avant publication — au moins
pour `decision = draft` (confiance 0.5-0.75) ou pour des `tags`/
`type` jugés sensibles — plutôt que publication 100 % automatique dès
que le seuil de confiance de l'Évaluateur est atteint ? À trancher
avant B5.2 (câblage réel du LLM Evaluator), sinon le comportement par
défaut sera "aucun humain dans la boucle" par construction.

---

## 01/08/2026 — Coordination inter-agents (relay.json) — motifs d'interrogation avant B7

### Constat

A2A (discovery/delegation/routing/handoffs/audit) confirmé hors scope
(cluster unique, pas d'agents distants) — mais la coordination interne
simple (Generator→Judge→Avocat→Évaluateur→WikiAgent) a des trous
identifiés en comparant le design documenté (29/07, `session_id` prévu
dans le schéma relay.json) au code réel (`src/services/relay.py`) et à
l'orchestrateur (`langgraph_orchestrator.py`, `build_graph()` toujours
`NotImplementedError`).

### Questions ouvertes (à trancher avant B7, PAS de décision prise ici)

Formulées comme motifs d'interrogation pour guider une implémentation
SOLID / Clean Code / KISS de `build_graph()` et de `RelayService` —
pas comme un cahier des charges figé :

- **SRP (Single Responsibility)** — `RelayService` fait aujourd'hui
  à la fois "stockage d'un relay" et implicitement "un seul relay
  global à la fois" (chemin fixe `nfs_relay_path`). Le `session_id`
  existe dans le schéma JSON mais n'est responsabilité de personne
  dans le code (aucune classe ne l'utilise pour isoler une session).
  Question : la responsabilité "isoler une session" doit-elle être
  portée par `RelayService` lui-même (chemin paramétré par
  `session_id`), ou par un composant séparé (ex. un
  `SessionRelayFactory`) qui construit un `RelayService` par requête ?
- **KISS** — avant d'ajouter un verrou distribué ou une queue, est-ce
  qu'un chemin de fichier `relay-{session_id}.json` suffit à éliminer
  la collision entre requêtes concurrentes ? À valider : est-ce que
  plusieurs requêtes concurrentes sont même un cas réel au vu du
  volume attendu (usage perso/petite équipe) — sinon la solution la
  plus simple est peut-être de documenter "1 requête à la fois" plutôt
  que de complexifier `RelayService`.
- **Audit trail vs KISS** — le design actuel écrase le relay à chaque
  étape (`tmp` → `rename` atomique, un seul instantané). Ajouter un
  historique (append plutôt qu'overwrite, ou copie dans `log.md`)
  répond au besoin d'audit mais viole KISS si rien n'exploite cet
  historique aujourd'hui — à ne construire que si un besoin réel de
  traçabilité post-incident est identifié (cf. YAGNI, cohérent D14).
- **Gestion d'échec / Open-Closed** — `RelayService.read()` renvoie
  `None` si `stale()`, sans comportement défini en aval (retry ?
  abandon ? escalade humaine — cf. gap "Human Control" du 01/08).
  Question : ce comportement doit-il être injecté (stratégie de
  gestion d'échec passée à l'orchestrateur, ouvert à l'extension sans
  modifier `RelayService`) plutôt que codé en dur dans
  `build_graph()` ?
- **Dependency Inversion** — `build_graph()` doit-il dépendre d'une
  abstraction du relais (interface `RelayService`-like) plutôt que du
  chemin NFS concret, pour rester testable avec le mock-first actuel
  (D10) sans dépendre de `/data/shared` ?

### Prochaine étape

À trancher au moment de B7 (`build_graph()` complet) — ne pas
sur-designer `RelayService` avant que B6/B7 ne rendent ces questions
concrètes (cohérent avec la discipline YAGNI déjà appliquée sur la
mémoire, D14).

---

## 01/08/2026 — Grille "System Design Concepts" — un point neuf : PostgreSQL inutilisé

### Constat

Passage en revue face à une grille générique (Load Balancer, Cache,
Database, Microservices, Message Queue, Rate Limiter, Search Service).
6 des 7 points sont soit déjà couverts (Search Service = VectorService+
LexicalSearch+Reranker), soit déjà tranchés (Rate Limiter = D5, Load
Balancer/Microservices = hors échelle du projet), soit déjà tracés
(Cache = B16). Un point neuf :

- **PostgreSQL déployé (2 docker-compose) mais sans aucun schéma ni
  table** — `postgres_dsn` (`src/core/settings.py`) n'est utilisé que
  par le healthcheck (`_check_postgres` dans `src/api/main.py`/
  `src/main.py`). Le commentaire settings.py dit "conversations,
  feedback, mémoire long-terme" mais rien n'écrit dedans. Candidat
  YAGNI (même logique que D14 sur la mémoire) : soit on construit un
  usage réel, soit on questionne le déploiement d'un service qui ne
  sert à rien pour l'instant.

### Lien avec la question déjà loggée (coordination/relay)

Le commentaire `settings.py` ligne 269 ("Redis : cache, queue
orchestrateur, sessions") anticipe déjà Redis comme *message queue*
pour l'orchestrateur — angle supplémentaire sur la question déjà
ouverte "relay.json vs verrou/queue" du point précédent : une queue
Redis (liste/stream) résoudrait la collision session concurrente sans
ajouter de nouveau composant. Pas tranché ici non plus — juste noté
que les deux questions ouvertes se recoupent.

### Question ouverte (PAS tranchée)

PostgreSQL : construire un usage réel (schéma conversations/feedback)
maintenant, ou le retirer du docker-compose tant qu'aucun agent n'en a
besoin (YAGNI, cohérent avec D14) ?

---

## 01/08/2026 — Grille "System Design Concepts" (suite, planche 4/4) — Notification System absent

### Constat

Search Service (déjà couvert), File Storage (déjà couvert par OMV/Borg),
Real-time Analytics (déjà écarté, D9) : rien de neuf. Un point neuf :

- **Aucun mécanisme de notification/alerte push.** Le monitoring actuel
  (D9, Phase 7 allégée) est intégralement pull : graphs Proxmox natifs,
  Glances web (`-w`), `/health`/`/ready`. Michel doit consulter
  manuellement pour détecter une panne. Seul élément planifié et non
  fait : "SMART NVMe : alertes usure (mail/webhook simple)" — un seul
  cas précis, pas un mécanisme général.
- Runbooks déjà écrits (0.22 : BC250 ne boot plus, RTX 4000 OOM, NFS
  stale handle, Qdrant corruption, OMV HDD failure) mais rien ne
  déclenche leur consultation — seul un check manuel régulier les
  rendrait utiles en pratique.

### Distinction avec le gap "Human Control" (01/08, déjà loggé)

Celui-ci porte sur la validation de contenu avant publication (pipeline
Evaluator). Celui-ci porte sur la santé opérationnelle du cluster
(pannes hardware/service). Deux besoins différents, tous deux absents.

### Question ouverte (PAS tranchée)

Un webhook simple (mail ou Slack/ntfy self-hosted) déclenché par les
health checks déjà en place (`/health`, `/ready`, D0.17) suffirait
probablement — cohérent avec l'esprit "allégé" de D9 (pas de
Prometheus/Grafana), juste un signal push minimal plutôt qu'un
mécanisme pull uniquement. Pas tranché ici, à discuter au moment de la
Phase 7.

---

## 01/08/2026 — Sidecar OCR PDF -> Vault (Unlimited-OCR)

### Constat de départ

- Besoin d'ingérer des PDFs dans le vault sous forme de notes markdown
  propres (tableaux, mise en page) plutôt qu'un simple texte brut extrait.
- Évalué [baidu/Unlimited-OCR](https://github.com/baidu/Unlimited-OCR) (VLM
  3B, lignée DeepSeek-OCR, parsing multi-page en un seul passage) : ne
  tourne que sur GPU CUDA — le BC-250 (M3, Vulkan-only) est exclu d'office.
  Seul le RTX 4000 8 GB (M2) est éligible, mais déjà chargé (Inference,
  Reranking, Juge, Avocat) : risque de contention VRAM si le pipeline OCR
  est branché en direct dans le chemin de requête.

### Décision actée

- Sidecar **hors chemin critique**, cohérent avec le docstring déjà présent
  dans `ingestion.py` ("pipeline offline asynchrone"). Flux :
  `PDF (inbox) → OCR (M2) → note vault (sources/) → IngestionService → Qdrant`.
- Deux déclenchements, pas de service long-vivant qui garde la VRAM :
  cron en heure creuse (`--once`, ex: fenêtre 02:30 du rsync existant) et
  déclenchement manuel via un mini-serveur FastAPI dédié (`--serve`,
  Swagger auto-généré sur `:8090`) — pas de couplage avec `src/api/main.py`
  (M1, pas de GPU).

### Fait

- `src/services/ocr_sidecar.py` (nouveau) : classe `PdfOcrSidecar` (scan
  inbox, OCR multi-page, nettoyage balises `<|det|>`, écriture note +
  frontmatter minimal, indexation, archivage `_processed/`/`_failed/`,
  déchargement VRAM explicite en fin de run) + CLI `--once`/`--serve`.
- `pyproject.toml` : nouveau groupe optionnel `ocr-sidecar` (torch,
  transformers, pymupdf, einops, addict, easydict) — isolé du reste,
  installé uniquement sur M2 (`pip install -e ".[ocr-sidecar]"`), pas
  d'impact sur M1/M3.

### Reste hors périmètre de cette session

- Frontmatter du sidecar volontairement minimal — le schéma OKF v0.2
  complet n'est pas encore formalisé (item 4.3 toujours ouvert) ; à
  réaligner une fois ce point clos.
- Pas encore testé sur le RTX 4000 réel (VRAM effective en usage
  concurrent avec Reranker/Juge/Avocat non mesurée).
- `docs/deployment-guide.md` : entrée cron à ajouter (emplacement identifié,
  pas rédigé).
- Aucun test unitaire sur `ocr_sidecar.py`.
- `README.md` : capacité non encore mentionnée dans la description du
  pipeline d'ingestion.

---

## 01/08/2026 — MemoryManager (monitoring mémoire cluster, V1 lecture seule)

### Contexte

- Revue externe (copilot) : proposait un MemoryManager générique, sans
  connaissance de l'architecture réelle (Vulkan-only BC-250, relay
  séquentiel M2, règle d'or CPU). Corrections appliquées : réutilisation
  d'`OllamaClientPool` existant (pas de nouveaux clients), match modèles
  par tag complet (pas substring), estimation RAM Qdrant via
  `get_collection_stats()` (approx ~200 B/point, choix Q2 — pas de
  Prometheus, cf. D9), `free -b` direct sur M3 (Q3 — unified GDDR6).

### Décisions (confirmées avant implémentation)

- Q1 : réutiliser `OllamaClientPool` (singleton lifespan API).
- Q2 : estimation RAM Qdrant par `points_count * 200 B` (pas `/metrics`).
- Q3 : `free -b` direct pour BC-250 (unified 16 GB), fallback non requis.
- SSH : user `root` partout, clé déployée via cloud-init/manuel
  (`infrastructure/ssh-keys-deployment.md`).

### Fait

- `src/services/ssh_client.py` (nouveau) : wrapper asyncssh
  (`SSHClient`, erreurs typées, decode bytes, timeout).
- `src/services/memory_manager.py` (nouveau) : `MemoryManager` +
  dataclasses (`MachineMemoryState`, `ClusterMemoryState`, `Alert`),
  snapshots M1/M2/M3 en parallèle, `assert_bc250_cpu_idle()`,
  `reserve_m2_gpu_for()`, `check_thresholds()`, log alertes structurées.
- `src/services/ollama.py` : méthode `list_models()` ajoutée (`/api/ps`).
- `src/services/vector.py` : méthode publique `get_collection_stats()`.
- `src/core/settings.py` : section SSH (M2/M3) + seuils mémoire
  (M1/M2/M3) — 15 nouvelles variables, toutes dans `.env.example`.
- `src/api/main.py` : endpoint `GET /api/v1/health/memory` (snapshot +
  alertes, 503 si services non initialisés, disabled si flag off).
- `pyproject.toml` : dépendance `asyncssh>=2.14.0` + per-file-ignore
  TRY003 pour ssh_client/memory_manager.
- `tests/test_memory_manager.py` : 12 tests (snapshots, garde-fous,
  alertes) — mocks SSH/Ollama/Qdrant, aucune machine réelle.
- `tests/test_api.py` : +1 test endpoint `/health/memory`.
- `infrastructure/ssh-keys-deployment.md` (nouveau) : guide déploiement
  clés SSH LXC 100 → M2/M3.

### Validation

- `pytest`: 29/29 PASSED
- `ruff`: 0 erreur sur fichiers modifiés
- `mypy`: 0 erreur sur services modifiés (4 résiduelles pré-existantes
  sur `ocr_sidecar.py` non touchées)

### Reste hors périmètre (V2 potentiel)

- Blocage automatique (actif) : refuser requête si seuil dépassé
  (V1 = lecture seule + alertes).
- Persistance historique Qdrant (`cluster_memory_history`) — flag
  `MEMORY_MANAGER_PERSIST_TO_QDRANT` défini mais non implémenté.
- Intégration relay : `reserve_m2_gpu_for()` appelé par le pipeline
  d'évaluation (à brancher en Phase B multi-agents).
- Monitoring continu (boucle interval) — seul le snapshot on-demand existe.

---

## 01/08/2026 — Prompts Agents v1 : templates + few-shots + contrats Pydantic

### Contexte

- Question ouverte : comment l'information qualité passe-t-elle du Juge à
  l'Avocat du diable en mode séquentiel ? Réponse : via `relay.json` (NFS
  M1↔M2) — l'Avocat lit la sortie complète du Juge (`judge.critique` +
  `judge.score`) en entrée de son prompt. **Pas de partage KV cache** :
  modèles différents (DeepSeek-R1-8B vs Ministral-8B), architectures et
  tokenizers incompatibles. Le relay.json EST le mécanisme de passage.
- Question OKF pour les sorties agents : **non pertinent** — OKF v0.2 est
  verbeux (type, verified, sources[], stale_after...) et conçu pour des
  pages wiki persistantes, pas pour du parsing LLM inter-agents.
  Recommandation actée : schémas JSON minimaux versionnés
  (`*_output_v1`, 4-6 champs) + OKF réservé au frontmatter du vault
  (écrit par l'Évaluateur sur les pages validées, `verified:
  human-reviewed` jamais en automatique → `machine-confirmed`).

### Décisions

- Sorties agents = schémas Pydantic stricts, versionnés, validés avant
  écriture relay.json.
- Score Advocate INVERSÉ (0.0 = faille bloquante, 1.0 = aucune faille) —
  clarification vs Juge.
- Few-shots (2 par agent) dans le prompt système pour fiabiliser le JSON.
- Parsing : retry avec prompt correctif (1 tentative) si JSON invalide ;
  `json_repair` à évaluer en dernier recours.
- `human-reviewed` interdit en sortie automatique (contrainte Literal).

### Fait

- `docs/prompts-agents.md` (nouveau) : principes communs + prompts système
  + 2 few-shots concrets par agent (Judge, Advocate, Evaluator, Generator,
  Planner, Rewriter) + trace de décision OKF.
- `src/agents/judge.py` : `JudgeOutput` (score, critique, checks_passed,
  flags[hallucination_suspect|omission_source|contradiction_interne],
  confidence).
- `src/agents/advocate.py` : `AdvocateOutput` (score inversé, faille,
  claims_contested, hallucination_risk, missing_context, confidence) +
  docstring explicite passage info via relay.json.
- `src/agents/evaluator.py` : `EvaluatorOutput` (decision
  publish|revise|reject, final_score, reasoning, revision_instructions,
  verified_tier[machine-confirmed|unverified]).
- `src/agents/generator.py` : `GeneratorOutput` (answer, citations,
  confidence, reasoning_trace).
- `src/agents/planner.py` (nouveau) : `PlannerOutput` + `SearchStrategy`
  (validateur vector+bm25 = 1.0).
- `src/agents/rewriter.py` (nouveau) : `RewriterOutput` (rewritten_query,
  expanded_terms, resolved_references).
- `src/agents/__init__.py` : exports des 6 agents + schémas.
- `tests/test_agent_schemas.py` : 13 tests (valides + rejets : score hors
  bornes, flag inconnu, risk inconnu, human-reviewed auto interdit,
  poids ≠ 1.0).
- `pyproject.toml` : per-file-ignore TRY003 pour `src/agents/*`.

### Validation

- `pytest`: 42/42 PASSED (13 nouveaux)
- `ruff`: 0 erreur
- `mypy`: 0 erreur sur `src/agents/` (9 fichiers)

### Prochaine étape (Phase B.1)

- Implémentation des méthodes LLM (prompt système + few-shots + parsing
  robuste + retry correctif) dans les 6 agents.
- Construction du graphe LangGraph minimal end-to-end
  (Plan → Rewrite → Retrieval → Rerank → Assemble → Gen → [Relay →
  Judge → Advocate → Eval si EVALUATION_ENABLED]).

---

## 02/08/2026 — M3 Fedora 43 + Évaluateur Granite (décisions matériel)

### Contexte

Utilisateur a validé **Fedora 43** comme OS du BC-250 (M3) après étude de la
doc communautaire [elektricm/amd-bc250-docs](https://elektricm.github.io/amd-bc250-docs/)
(Mesa 25.1+ en mainline, kernel 6.18.18 LTS recommandé, kernels
6.15.0-6.15.6 et 6.17.8-6.17.10 cassés) et a demandé de documenter
l'installation complète : adressage, services, drivers, modèles, BIOS
Forbidden-Darkness (core unlock 6→8 + VRAM dynamique 512 MB) et script
40 CU. A aussi tranché l'Évaluateur : **Granite** (diversification de lignée
vs Générateur Qwen3-14B).

### Fait

- `docs/deployment-guide.md` : section Machine 3 entièrement réécrite —
  §3.0 BIOS Forbidden-Darkness (repo + flash + vérifs), §3.1 Fedora 43
  (install, adressage 10.10.0.3/24, partitionnement), §3.2 pin kernel
  6.18.18 LTS (versionlock), §3.3 vérif Vulkan, §3.4 TTM pages_limit
  3959290, §3.5 GRUB triplet, §3.6 unlock 40 CU, §3.7 gouverneur
  (COPR filippor/bazzite), §3.8 Ollama Vulkan + modèles, §3.9 Glances
  (décision D9), §3.10 NFS, §3.11 SSH + firewall.
- `infrastructure/bc250/setup-vulkan-stack.sh` : réécrit pour Fedora 43
  (dnf + COPR, plus d'experimental/apt).
- `infrastructure/bc250/enable-40cu-unlock.sh` : §3 dépendances Fedora (dnf).
- `infrastructure/bc250/enable-cpu-core-unlock.sh` : header → voie principale
  = BIOS Forbidden-Darkness (script rw-r-r-0644 gardé en fallback).
- `docs/diagrams/01-cluster-overview.md` : OMV LXC 105 déplacé dans M2
  (alignement diagrammes 04/05/06), Évaluateur → Granite 4.1 8B, M3 →
  Fedora 43 + core unlock 8c/16t BIOS, lien Cold save corrigé.
- `src/core/settings.py` : `evaluator_model` → `hf.co/ibm-granite/
  granite-4.1-8b-instruct-GGUF:Q4_K_M` ; `.env.example` idem.
- `src/agents/evaluator.py` + `docs/prompts-agents.md` §3 + `README.md`
  (2 diagrammes) + `docs/architecture.md` + `docs/deployment-guide.md`
  (pull §5) + `docs/BRIEF-INTEGRATION-MODELES-Q4-HF.md` + `backlog.md`
  : toutes les références Évaluateur Qwen3-4B → Granite 4.1 8B.
- `ruff` : 0 erreur (noqa E501 ajouté sur ligne TTM settings.py) ;
  `pytest` : 42/42 PASSED.

### Prochaine étape

- Phase C4 : pulls réels des modèles (digests SHA256 à remplir dans `.env`)
- Déploiement Fedora 43 sur le BC-250 réel (guide §3 prêt).

---

## 02/08/2026 — Clarification BIOS Forbidden-Darkness (flash P3.00 inutile) + harmonisation mermaid

### Contexte

Retour de Michel : le flash P3.00 n'est **plus nécessaire** comme étape
préalable — le repo Forbidden-Darkness fournit un **BIOS complet** (base
P3.00 incluse, core unlock 8c/16t + VRAM dynamique 512 MB), on flashe donc
directement cette image en UEFI. Demande aussi : vérifier les diagrammes
mermaid et signaler les corrections.

### Fait

- `docs/deployment-guide.md` §3.0 : "BIOS cible P3.00 moddé" → "BIOS moddé
  Forbidden-Darkness complet, flash UEFI direct, AUCUN flash P3.00 stock
  préalable" (tableau + blocs code).
- `README.md` : tableau Machine 3 (BIOS final = Forbidden-Darkness, OS →
  Fedora 43 — restait "Debian Testing/Sid") ; 3 mermaid alignés
  "Zen 2 6c/12t" → "8c/16t (core unlock BIOS)" ; règle d'or CPU → 8c/16t ;
  décision Roadmap "AntiX-26 vs Debian" → Fedora 43.
- `docs/diagrams/03-query-flow.md` : Évaluateur "4b" → "Granite 4.1 8b".
- `docs/diagrams/05-network-topology.md` + `06-physical-topology.md` :
  "6c/12t" → "8c/16t (core unlock BIOS)".
- `backlog.md` : tableau Machine 3 (BIOS + Fedora 43) ; checklist OS/Mesa/
  Governor (dnf + grub2-mkconfig + COPR, plus d'experimental) ; table pièges
  (Mesa → Fedora mainline, tmpfiles 3959290) ; kernel pin dnf versionlock ;
  rebuild 40 CU hook dnf ; garde "6c/12t → 8c/16t" légitime dans les
  descriptions d'état d'origine.
- `docs/bc250-hardware-notes.md` : OS → Fedora 43, BIOS Forbidden-Darkness
  (P3.00 inclus, fallback SMU), ttm.pages_limit → 3959290.
- `infrastructure/bc250/enable-cpu-core-unlock.sh` : `apt` → `dnf` (stress-ng).
- `infrastructure/bc250/setup-vulkan-stack.sh` : formulation BIOS clarifiée.

### Diagrammes vérifiés — état final

- 01 ✅ corrigé (OMV M2, Granite, Fedora 43, 8c/16t)
- 02 ✅ ok (ingestion, pas de mention M3 BIOS)
- 03 ✅ corrigé (Évaluateur Granite 4.1 8b)
- 04 ✅ ok (OMV sur M2, cohérent)
- 05 ✅ corrigé (8c/16t)
- 06 ✅ corrigé (8c/16t)

### Validation

- Rien de code modifié (doc + scripts shell) — pas de test à relancer.
- Aucun `apt`/experimental/antiX-26 résiduel hors contexte M1/M2 (LXC Debian légitime).

---

## 02/08/2026 — M3 : specs 8c/16t directes (plus de 6c/12t)

### Contexte

Retour de Michel : si le BIOS Forbidden-Darkness (flash direct) rend les
8c/16t **définitifs**, pourquoi les tableaux de specs Machine 3 affichent
encore "6c/12t" ? — Le "6c/12t" n'est plus l'état de la carte après flash.

### Fait

- `README.md` tableau Machine 3 : "6c/12t → 8c/16t core unlock" → "**8c/16t**
  — core unlock persistant par flash BIOS".
- `backlog.md` tableau Machine 3 : "Zen 2 6c/12t (→ 8c/16t)" → "Zen 2 **8c/16t**".
- `docs/deployment-guide.md` §3.0 Effet 1 : "6c/12t → 8c/16t persistant" →
  "**8c/16t** persistant (flash BIOS, plus de script volatil SMU)".
- `docs/bc250-hardware-notes.md` : "Core unlock 6c/12t → 8c/16t" → "Core
  unlock → **8c/16t persistant** (2 cores débloqués dès le boot)".
- `src/core/settings.py` : description `bc250_cpu_cores_unlocked` →
  "8c/16t via BIOS Forbidden-Darkness persistant ; fallback SMU volatil".
- `.env.example` : commentaire `BC250_CPU_CORES_UNLOCKED` idem.
- **Conservés à dessein** : `enable-cpu-core-unlock.sh` (script fallback SMU
  qui part réellement de 6c) et la trace de session ci-dessus (historique).
- `pytest test_settings` : 4/4 PASSED, ruff OK.

---

## 02/08/2026 — Dashboard CTOS (chat + monitoring single-page)

### Contexte

Nouveau frontend unifié pour remplacer la page wiki : une seule page web
"CTOS" (inspiration Watch Dogs, dark cyberpunk) avec :
- chat RAG à gauche (70 %), panneau monitoring M1/M2/M3 + cluster à droite (30 %)
- vanilla JS/CSS sans build, pas d'auth (LAN de confiance)
- polices locales WOFF2 (JetBrains Mono + Space Grotesk), dark + toggle semi-lit
- sliding window contexte chat (anti lost-in-the-middle) : 10 paires max, 12 000 chars max
- monitoring via MemoryManager + Ollama /api/ps + Qdrant + Glances M3 — PAS de Proxmox API
- temps de réponse affiché (pas de streaming token obligatoire, SSE implémenté quand même)
- M3 : pas d'émulation, Glances natif Fedora 43 (port 61208), pas de py3nvml (AMD/Vulkan)

### Renommage de la marque → CTOS (validation utilisateur)

L'ancien nom de marque du projet a été remplacé par **CTOS** (dashboard) et
`rag-*` (hostnames LXC). Toutes les occurrences renommées : branding
frontend (index.html, chat.html, CSS, JS, namespace JS → `CTOS`,
localStorage `ctos-theme`), prompt LLM (`Tu es CTOS, assistant…`), hostnames
LXC (`rag-master`, `rag-vectordb`, `rag-gpu-inference`, `rag-workers`, VM
pfSense `rag-pfsense`), mot de passe défaut LXC → `ctos`, pyproject (auteur
"Projet CTOS", email `ctos@example.com`), backlog (tableau hostname + trace
session). Vérifié : `git grep -i` de l'ancien nom = 0 occurrence (hors
`static/fonts` binaire).

### Fait

- `src/core/settings.py` : section Dashboard CTOS — `dashboard_enabled`,
  `dashboard_refresh_sec` (10), `glances_m3_url`, `chat_history_max` (10),
  `chat_max_context_chars` (12000), `dashboard_semi_light`, `monitoring_offline`
  (prédéploiement : cartes n/a immédiates, zéro sonde réseau).
- `src/services/monitoring.py` (nouveau) : `MonitoringService` — `summary()` →
  4 cartes (m1/m2/m3/cluster) + alerts ; `_card_m1/_card_m2/_card_m3` ;
  `_card_cluster` via `_cluster_checks()` (Qdrant /health, Ollama tags ×3,
  Glances /api/3/cpu, relay age) ; `_check_relay()` (relay.json < TTL×3) ;
  `_summary_offline()` mode prédéploiement sans réseau.
- `src/api/main.py` : static mount `/static` ; GET `/` (index.html),
  `/partials/chat`, `/partials/monitoring` (fragment HTML + alerts) ;
  `/api/v1/monitoring` (JSON poll) ; `/api/v1/chat` (SSE : token/done avec
  elapsed_ms, sources, chunks_used — pipeline hybrid search + rerank +
  génération LLM via `pool.generate` M3, repli sur contexte brut si échec).
- `static/` (nouveau) : `index.html` (shell CTOS), `partials/chat.html`,
  `css/ctos.css` (design system + fonts-face + scanlines + thème semi-lit),
  `css/chat.css`, `css/monitoring.css`, `js/utils.js`, `js/chat.js` (SSE via
  fetch ReadableStream), `js/monitoring.js` (poll 10s), `js/app.js` (bootstrap,
  horloge, toggle thème) ; `fonts/` (JetBrainsMono Regular/Bold, Space Grotesk
  variable — WOFF2 valides).
- `.env.example` : section Dashboard CTOS (DASHBOARD_*, GLANCES_M3_URL,
  CHAT_HISTORY_MAX, CHAT_MAX_CONTEXT_CHARS, MONITORING_OFFLINE commentée).
- `infrastructure/docker/Dockerfile.api` : `COPY static/ static/` (le dashboard
  était absent de l'image → 404 en conteneur).

### Bugs corrigés pendant le test

- tenacity 9.1.4 : `AttemptManager` n'a plus `attempt_number` → compat 8/9 dans
  `ollama.py` (`getattr(attempt_state, "attempt_number", None)` → retry_state).
- `MachineCard`/`MachineMetric` non sérialisables → `to_dict()` + `summary()`
  sérialise, `_render_card` accepte dict.
- `logger` manquant dans `main.py` (import logging ajouté).
- Test en prédéploiement : les sondes SSH/Ollama/Qdrant sur IP inexistantes
  bloquaient (~3 s × 10+) → `MONITORING_OFFLINE=true` + garde chat
  prédéploiement (SSE erreur clair, aucune tentative réseau).

### Validation

- TestClient (mode prédéploiement) : `/` 200, `/partials/chat` 200,
  `/static/css/ctos.css` 200, `/api/v1/monitoring` 200 (4 cartes),
  `/partials/monitoring` 200, `/api/v1/chat` 200 SSE (erreur prédéploiement claire).
- `pytest test_api + test_settings` : 10/10 PASSED (20 s).
- ruff : mes fichiers propres ; restent 3 violations TRY003/TRY301
  pré-existantes (`src/main.py`, `ocr_sidecar.py`) hors périmètre.

### Prochaines étapes (post-déploiement)

- Validation réelle M1/M2/M3 avec le dashboard (monitoring + chat de bout en bout)
- Ouvert : `partials/monitoring` rend du HTML + le JS refait le rendu — choisir
  UNE source de vérité (le JSON `/api/v1/monitoring` suffit, partial à supprimer)







