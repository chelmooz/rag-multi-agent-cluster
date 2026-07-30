# Backlog — Cluster RAG Multi-Agents

## Phase 0 — Squelette & Config
- [ ] 0.1 Structure `src/` complète (agents, tools, core, api, services)
- [ ] 0.2 Config centralisée `.env` + `settings.py` (Pydantic Settings)
- [ ] 0.3 Docker Compose VectorDB (Qdrant + PostgreSQL + Redis)
- [ ] 0.4 Docker Compose Orchestrator (FastAPI + workers)
- [ ] 0.5 Scripts Proxmox LXC (master + GPU passthrough RTX 4000)
- [ ] 0.6 **Créer `docs/claude-md-template.md` → template CLAUDE.md pour wiki (frontmatter OKF v0.2)**
- [ ] 0.7 **Créer `scripts/okf-lint.py` : validation frontmatter OKF + détection stale/orphelins/contradictions**
- [ ] 0.8 **Endpoints OKF wrapper : `/api/v1/okf/validate`, `/api/v1/okf/list`, `/api/v1/okf/show`**
- [ ] 0.6 Créer `infrastructure/proxmox/create-lxc-wiki-agent.sh` (LXC 100 complet)
- [ ] 0.7 Créer `infrastructure/docker/orchestrator.yml` + `nginx.conf` + 3 Dockerfiles
- [ ] 0.8 Créer `docs/claude-md-template.md` → template CLAUDE.md pour wiki (frontmatter OKF v0.2)
- [ ] 0.9 Intégrer healthchecks Ollama M1/M2/M3 dans wiki-agent (retry + fallback)
- [ ] 0.10 Test d'ingestion bout-en-bout : source → embed M1 → index Qdrant → wiki pages → index.md/log.md
- [ ] 0.11 Configurer mTLS pour API interne (certs auto-signés via pfSense CA)
- [ ] 0.12 Prometheus exporter custom wiki-agent (metrics: `wiki_pages_total`, `ingest_duration`, `query_latency`)
- [ ] 0.13 Git sidecar auto-commit dans LXC 100 (cron 1h) pour versioning wiki hors OMV
- [ ] 0.14 Script `scripts/okf-lint.py` : validation frontmatter OKF v0.2 + détection stale/orphelins/contradictions (wrappers CLI `okf`)

## Phase 1 — Pipeline RAG Core (Master LXC 100-101)
- [ ] 1.1 Ingestion Service (chunking, augmentation, embedding sur Machine 1 CPU)
- [ ] 1.2 VectorService (Qdrant client, hybrid search)
- [ ] 1.3 LexicalSearch (BM25 via Qdrant sparse)
- [ ] 1.4 Reranker (bge-reranker-v2-m3 sur RTX 4000 - Machine 2)
- [ ] 1.5 API Endpoints (/ingest, /query OpenAI-compat)
- [ ] 1.6 **Endpoint `/api/v1/embed` : bge-m3 dense+sparse unifié + fallback histogramme** (OK → README)

## Phase 2 — Orchestrateur & Planificateur (LXC 100 - Machine 1)
- [ ] 2.1 Orchestrator (flux principal)
- [ ] 2.2 Planner (intention + stratégie)
- [ ] 2.3 QueryRewriter (réécriture conversationnelle)
- [ ] 2.4 ContextAssembler (chunks + savoir interne + fenêtre)
- [ ] 2.5 HTTP Client Pool (httpx avec retry/circuit-breaker)

## Phase 3 — Génération + Évaluation Multi-Agents
- [ ] 3.1 Generator (qwen3.5:14b Q4_K_M ou qwen3.5-35b-a3b IQ2_M sur BC250 Vulkan)
- [ ] 3.2 Judge (qwen3.5:7b Q4_K_M sur RTX 4000 - Machine 2 LXC 200) — **séquentiel, unload après écriture relay**
- [ ] 3.3 Devil's Advocate (mistral-small-3.2:7b Q4_K_M sur RTX 4000 - Machine 2 LXC 201) — **séquentiel après Judge, lit relay**
- [ ] 3.4 Evaluator (qwen3.5:3b / granite-3.2:2b Q4_K_M sur Machine 1 CPU) — **lit relay.json complet, synthèse finale**
- [ ] 3.5 **Évaluateur écrit `verified: human-reviewed` dans frontmatter pages validées (OKF trust tier)**

## Phase 4 — Wiki Persistant (Pattern Karpathy + OKF v0.2)
- [ ] 4.1 WikiTools (read/write/append/index/log via vault Obsidian)
- [ ] 4.2 IngestAgent (source → pages wiki + index.md + log.md)
- [ ] 4.3 Schema AGENTS.md (conventions nommage, frontmatter OKF v0.2, structure)
- [ ] 4.4 Endpoint /api/v1/ingest
- [ ] 4.5 **Structure vault OKF : `index.md` (§8 catalogue) + `log.md` (§9 chronologie) + frontmatter validé**
- [ ] 4.6 **Lint endpoint `/api/v1/lint` utilise `okf list --stale --orphan --contradiction`**

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
| **Machine 1** | **Master** (Orchestration, API, VectorDB, Monitoring, Evaluator, Embedding CPU, **Relay NFS**) | 2× Xeon E5-2699 v4 / **32 GB ECC** | **AMD Radeon RX 580** (8 GB) | Proxmox VE 9.3 (LXC 100, 101, 102, 103, 104*, 105) |
| **Machine 2** | **GPU Worker** (Reranker, Judge, Avocat, Backup Embedding CPU) | 1× Xeon E5-2698 v4 / **64 GB ECC** | **NVIDIA Quadro RTX 4000** (8 GB VRAM dédiée) | Proxmox VE 9.3 (LXC 200 privilégié GPU, 201) |
| **Machine 3** | **BC250 Baremetal** (Generator, Text-to-SQL, Vision, Fast-check) | Zen 2 6c/12t / **16 GB GDDR6 unifiée** | **Intégré - Vulkan ONLY** (40 CU débloquées) | Debian Testing/Sid baremetal (Ollama Vulkan natif) |
| **Client** | Obsidian Vault (visualisation + ingestion) | Poste de travail | – | Native (Electron) |

\* LXC 104 = pfSense, uniquement si pas d'appliance dédiée.

**Réseau** : Machine 1 dispose de 2 ports 10 Gb/s + 1 port 1 Gb/s (carte familiale) — backbone 10 Gb/s inter-nœuds recommandé.

**NFS Relay** : Machine 1 exporte `/data/shared` → monté sur Machine 2 `/data/shared` (fichier `evaluation-relay.json` partagé pour pipeline Juge→Avocat→Évaluateur).

**Répartition LXC prévue** :
- Machine 1 : `100` Orchestrator, `101` Vector DB (Qdrant), `102` API Gateway (Nginx), `103` Monitoring (Prometheus/Grafana/Loki)
- Machine 2 : `200` Inference GPU (passthrough RTX 4000), `201` Workers Agents (Juge, Avocat, backup embedding)
- Machine 3 : Ollama Vulkan natif (pas de LXC)

## Modèles Recommandés par Machine (30/07/2026 - validé échange)

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

## Machine 3 — BC250 Baremetal : Checklist Complète (29/07/2026)

### Hardware & Firmware
- [ ] Carte BC-250 reçue, inspectée (PCB, condensateurs, slot PCIe)
- [ ] Alim 300W+ 12V 8-pin PCIe connectée
- [ ] Refroidissement AIO / high-CFM fans monté (test thermal paste)
- [ ] BIOS flashé P3.00+ community-patched (elektricM guide)
- [ ] BIOS VRAM: Dynamic 512 MB configuré
- [ ] Backup BIOS P3.00 sur USB (procédure recovery validée)

### OS & Kernel
- [ ] Debian Testing/Sid installé (netinst, `nomodeset` au boot install)
- [ ] Kernel 6.18.18 LTS ou 6.19.x installé (pin apt pour éviter 6.15/6.17 buggés)
- [ ] GRUB: `ttm.pages_limit=4194304 ttm.page_pool_size=4194304 amdgpu.sg_display=0`
- [ ] `update-grub` + reboot + vérif `cat /proc/cmdline`
- [ ] CPU governor: `performance` persistant (tmpfiles.d)

### Mesa / Vulkan
- [ ] Repo `experimental` ajouté + pin-priority 500 pour mesa-vulkan-drivers
- [ ] `apt install -t experimental mesa-vulkan-drivers libgl1-mesa-dri mesa-utils vulkan-tools`
- [ ] `vulkaninfo --summary` → "AMD BC-250 (RADV GFX1013)" + INTEGRATED_GPU
- [ ] `glxinfo` → OpenGL 4.6+ Mesa 25.1.x

### GPU Governor (Oberon)
- [ ] `cyan-skillfish-governor-smu` .deb installé (Magnap/filippor release)
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
    - [ ] `qwen3.5:14b@sha256:...` (Q4_K_M, ~9 GB)
    - [ ] `qwen3.5-35b-a3b@sha256:...` (IQ2_M, ~11 GB)
    - [ ] `qwen3-coder-30b-a3b@sha256:...` (IQ2_M)
    - [ ] `llava-next:13b@sha256:...` (Q4_K_M)
    - [ ] `qwen2.5-vl@sha256:...` (Q4_K_M)
    - [ ] `granite-4.0-h-tiny@sha256:...` (Q4_K_M)
    - [ ] `nomic-embed-text-v2-moe@sha256:...`

### Réseau & NFS (VLAN 10)
- [ ] IP statique 10.10.0.3/24, MTU 9000 sur interface 1G
- [ ] Route pfSense 10.10.0.254 → Internet (NAT)
- [ ] NFS client: mount M1:/data/shared → /data/shared (_netdev, fstab)
- [ ] NFS client: mount M1:/data/wiki → /data/wiki (_netdev, fstab)
- [ ] Firewall: autoriser 11434 (Ollama), 2049 (NFS), 80/443 (WAN)
- [ ] Test: `iperf3 -c 10.10.0.1` → >900 Mbps, MTU 9000 OK

### Monitoring & Observabilité
- [ ] `prometheus-node-exporter` installé + scrape config M1
- [ ] GPU telemetry: oberon governor metrics (power, temp, clock) exposés
- [ ] SMART NVMe: `nvme smart-log` cron + alertes usure
- [ ] Logs: journald → Loki (correlation ID)
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
| **`systemd-tmpfiles` écrase `ttm.pages_limit`** | `cat /sys/module/ttm/parameters/pages_limit` → `3145728` (12 GiB) au lieu de `4194304` | Vérifier **après reboot**, pas après écriture. `tmpfiles.d` priorité finale gagne. Corriger `/etc/tmpfiles.d/gpu-ttm-memory.conf` |
| **Kernel update casse 40 CU unlock** | `active_cu_number` retombe à 24 | Rebuild module patché + `dracut -f` + reboot **après chaque kernel upgrade** |
| **Mesa dans Debian Stable trop vieux** | `vulkaninfo` → Mesa 24.x, pas de RADV GFX1013 | **OBLIGATOIRE** Debian Testing/Sid + repo experimental pin 500 |
| **ROCm installé par erreur** | `rocblas_abort()`, compute queue hang | **Ne jamais installer ROCm**. Vulkan only. |
| **CPU governor `schedutil`** | Spikes latence TTFT, instabilité | `performance` lock via tmpfiles.d |
| **zram trop gros** | Concurrence RAM physique avec modèles | Max 2 GB (`zram-size = 2048`) |
| **Modèles sans digest SHA256** | `ollama pull qwen3.5:14b` → version mobile différente | **Toujours** `@sha256:...` dans `.env` / scripts |

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
9. Monitoring (node-exporter, oberon metrics, SMART, Loki)
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

---

### 29/07/2026 — Pipeline Séquentiel Juge → Avocat sur Machine 2 (RTX 4000 8GB) — **TRANCHÉ**

**Problème** : Judge (qwen3.5:7b ~5GB) + Avocat (mistral-small-3.2:7b ~5GB) = **~10GB VRAM** > **8GB RTX 4000**. Impossible de les faire tourner en parallèle.

**Solution** : Exécution **séquentielle** sur le même GPU (LXC 200/201 partagé) avec **unload explicite** du modèle précédent avant chargement du suivant.

**Flux** :
```
Generator (BC250 M3) → réponse écrite dans relay.json
  ↓
Juge (M2 RTX 4000) → charge qwen3.5:7b → évalue → écrit relay.json → **unload modèle**
  ↓
Avocat (M2 RTX 4000) → charge mistral-3.2:7b → lit relay + réponse → évalue → écrit relay → **unload**
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

→ **CPU BC250 (Zen 2 6c/12t) DOIT RESTER AU REPOS** pendant l'inférence GPU. Embedding = Machine 1 CPU (principal) / Machine 2 CPU (backup).

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
| 192.168.10.0/24 | 10.10.0.1 | TCP 80/443 | Client → API Gateway (nginx LXC 102) |
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
| **Observabilité intégrée** | Prometheus/Grafana/Loki prévu dès Phase 7 — correlation ID depuis le début. |

### ⚠️ Points de vigilance (Risques maîtrisés)

| Risque | Impact | Mitigation |
|--------|--------|------------|
| **Single Point of Failure : Machine 1 (Master)** | Qdrant + API + Wiki + Evaluator + NFS = tout s'arrête si M1 tombe | → Backup Qdrant snapshot quotidien sur M2. NFS export read-only possible depuis M2. |
| **NFS latency sur évaluation** | Relay file = point de synchronisation bloquant | → MTU 9000 + 10GbE = <1ms RTT. Timeout 120s Juge → Avocat. Acceptable. |
| **BC250 baremetal = pas de snapshot/rollback** | Mise à jour noyau/BIOS risquée | → Tests sur VM simulée d'abord. Backup config `/etc` + BIOS P3.00 sur USB. |
| **RTX 4000 8GB limite dure** | Pas de place pour modèle > 7B quantifié | → Choix validé : Judge/Avocat 7B max. Si besoin 14B → seul BC250 peut. |
| **Modèles non verrouillés (tags Ollama)** | `qwen3.5:7b` pull = version mobile → reproductibilité | → Fixer digests SHA256 dans `.env` / `docker-compose`. `ollama pull qwen3.5:7b@sha256:...` |
| **Obsidian vault lock concurrency** | Client + Cluster écrivent simultanément | → NFS `no_root_squash` + file locking (fcntl). Ou versioning git sidecar. |

### 🔧 Recommandations immédiates (DevOps)

1. **Lock les versions modèles** — Ajouter dans `.env` : `OLLAMA_MODEL_JUDGE=qwen3.5:7b@sha256:xxx` etc.
2. **Health checks obligatoires** — `/health` sur chaque service (Ollama, Qdrant, API) → Prometheus scrape.
3. **Secrets management** — Pas de tokens/API keys en dur. `sops` + `.env.encrypted` ou Vault (Phase 7).
4. **Backup Qdrant** — `qdrant snapshot create` cron quotidien → stocké sur M2 (64GB dispo).
5. **Test de charge pré-prod** — `hey` / `locust` sur `/api/v1/query` avec 10-50 RPS avant mise en prod.
6. **Runbook incident** — Documenter : "BC250 ne boot plus", "RTX 4000 OOM", "NFS stale handle", "Qdrant corruption".

### Verdict

**Architecture cohérente, contrainte hardware respectée, pattern d'évaluation multi-agents viable.**

Le cluster tient sur 3 machines hétérogènes sans compromis majeur. Le seul "hack" assumé est le relay NFS séquentiel — mais c'est un pattern standard (sidecar file) qui évite d'acheter un 2e RTX 4000.

---

### 29/07/2026 — Plan Backup 3-2-1 (OMV + HDD 2TB cold) — **TRANCHÉ**

**Topologie stockage** :
| Niveau | Support | Contenu | Fréquence | Outil |
|--------|---------|---------|-----------|-------|
| **Prod (NVMe)** | M1: 1 TB | Proxmox, LXCs, Qdrant, Wiki, **OMV VM** | — | — |
| | M2: 256 GB | Proxmox, LXCs, Ollama cache BC250 | — | — |
| | BC250: 475 GB | OS Debian, Modèles (9-11 GB) | — | — |
| **Backup Live (NVMe)** | OMV VM sur M1 (disque 500 GB dans 1 TB) | Qdrant snapshots, Wiki rsync, Configs M1/M2/BC250, Ollama models cache | Quotidien (cron) | borg/kopia pull |
| **Tier 3 Cold (HDD)** | HDD mécanique 2 TB (USB/SATA, LUKS) | Archive dédupliquée, rétention 30j/12m/3y | Hebdo | borg push depuis OMV |

**Règle 3-2-1** : 3 copies (Prod + OMV + HDD) · 2 médias (NVMe + HDD) · 1 off-site (rotation HDD)

**Flux backup** :
```
OMV (M1) ──borg pull──► M2 (256 GB) ──rsync pull──► BC250
    │
    └──► HDD 2TB (borg create --compression lz4, LUKS)
```

**Actions** :
- [ ] Ajouter disque virtio 500 GB à la config Proxmox M1 pour OMV VM
- [ ] Déployer OMV VM (Debian + OMV) sur M1
- [ ] Configurer borg/kopia repo sur HDD 2TB (LUKS + clé hors cluster)
- [ ] Cron quotidien : Qdrant snapshot → OMV → borg create
- [ ] Cron hebdo : borg push HDD 2TB + rotation physique
- [ ] Documenter restore procedure dans `infrastructure/backup/restore.md`

Prêt pour Phase 0 (squelette + config + Docker Compose).

---

## 29/07/2026 — Architecture LXC 100 (Orchestrator + Wiki Agent) + Schema CLAUDE.md — **NOUVEAU**

### 1. Spécifications LXC 100 — Master Orchestrator

| Paramètre | Valeur |
|-----------|--------|
| **CTID** | 100 |
| **Hostname** | `jarvis-master` |
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

### 2. Mounts NFS (depuis OMV VM LXC 105 sur M1)

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
│  ├── nginx:80/443            ← Reverse proxy + TLS local   │
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
    └── Evaluator → http://10.10.0.1:11434 (Ollama M1 CPU qwen3.5:3b)
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
| `create-lxc-wiki-agent.sh` | `infrastructure/proxmox/` | Création LXC 100 + config post-install |
| `orchestrator.yml` | `infrastructure/docker/` | Docker Compose stack complète |
| `nginx.conf` | `infrastructure/docker/` | Reverse proxy + TLS local |
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
- [ ] **0.12** Prometheus exporter custom wiki-agent (metrics: `wiki_pages_total`, `ingest_duration`, `query_latency`)
- [ ] **0.13** Git sidecar auto-commit dans LXC 100 (cron 1h) pour versioning wiki hors OMV

### 9. Décisions d'architecture à trancher (complément)

| Question | Options | Recommandation |
|----------|---------|----------------|
| **Template LXC** | Debian 12 vs Ubuntu 24.04 | **Debian 12** (plus léger, stable, pas de snap) |
| **Orchestration conteneurs** | Docker Compose vs systemd-nspawn | **Docker Compose** (standard, portable, compose.yml lisible) |
| **Wiki Agent implémentation** | Python script custom vs LangGraph nodes | **LangGraph** (déjà choisi stack, graphe d'état explicite) |
| **Authentification API** | mTLS + client certs vs JWT vs none (LAN) | **mTLS** (certs auto-signés pfSense CA, zéro config client) |
| **Monitoring Wiki Agent** | Prometheus exporter custom + Grafana | **Oui**, metrics: `wiki_pages_total`, `ingest_duration_seconds`, `query_latency_seconds`, `llm_calls_total` |
| **Backup wiki (hors OMV)** | Git auto-commit sur push wiki | **Git sidecar** dans LXC 100 (cron 1h, push vers remote bare) |