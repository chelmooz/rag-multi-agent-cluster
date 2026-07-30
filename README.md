# 🧠 Cluster RAG Multi-Agents 100% Offline (Proxmox + AMD BC-250 + Obsidian Vault)

![Statut](https://img.shields.io/badge/Status-En_conception-orange)
![Licence](https://img.shields.io/badge/License-MIT-green)
![Privacy](https://img.shields.io/badge/Privacy-100%25_Offline-blue)
![Hardware](https://img.shields.io/badge/Hardware-Proxmox%20%7C%20AMD%20BC250%20%7C%20RTX4000%20%7C%20RX580-purple)
![Frontend](https://img.shields.io/badge/Frontend-Obsidian_Vault-7c3aed)

> ⚠️ **Statut réel** (voir [ROADMAP.md](ROADMAP.md)) : ce dépôt est au stade de **conception documentaire**. Aucun composant listé ci-dessous n'est encore implémenté. Ce README décrit la cible, pas l'existant.

> ⚠️ **Correction hardware (29/07/2026)** : le BC-250 tourne sous **Vulkan (Mesa/RADV), pas ROCm** — AMD ne fournit pas de bibliothèques rocBLAS pour ce GPU (GFX1013). Sa mémoire est **16 GB GDDR6 unifiée** partagée CPU/GPU (pas 12 GB dédiés). Voir [docs communautaires BC-250](https://elektricm.github.io/amd-bc250-docs/) et le [guide AI akandr/bc250](https://github.com/akandr/bc250).

> ℹ️ **Beta test frontend** : voir `scripts/test_frontend_api.py` — validation automatisée API + frontend (32 scénarios). **`/api/embed` → OK** (bge-m3 1024d — dense + sparse en un seul passage, BM25 conservé en complément lexical ; fallback histogramme si indisponible).

> ✅ **Alignement OKF v0.2 (30/07/2026)** : Frontmatter wiki migré vers format OKF v0.2 (Google Cloud, juin 2026). Champs clés : `type` (obligatoire), `verified` (trust tier : unverified/machine-confirmed/human-reviewed), `status` (draft/stable/deprecated), `stale_after` (date), `sources` enrichis (crédibilité par source). Structure vault OKF : `index.md` (§8) + `log.md` (§9). CLI `okf` + plugin Obsidian `okf-enforcer` identifiés — **pas de dépendance dure tant que pré-1.0** (lecture/écriture frontmatter gérée nativement dans Wiki Agent).

---

## 📑 Table des matières

- [Vue d'ensemble](#-vue-densemble)
- [Architecture du Système](#️-architecture-du-système)
- [Plan de Backup (3-2-1)](#-plan-de-backup-3-2-1)
- [Topologie Réseau & Sécurité](#-topologie-réseau--sécurité)
- [Intégration avec Obsidian (pattern Karpathy)](#-intégration-avec-obsidian-pattern-karpathy)
- [Fonctionnalités Clés](#-fonctionnalités-clés)
- [Infrastructure Matérielle](#️-infrastructure-matérielle)
- [Stack Technique](#️-stack-technique)
- [Guide d'Installation](#-guide-dinstallation)
- [Utilisation](#-utilisation)
- [Roadmap](#️-roadmap)
- [Points de Vigilance DevOps](#️-points-de-vigilance-devops-risques-maîtrisés)
- [Contribuer](#-contribuer)
- [Licence](#-licence)

---

## 🌍 Vue d'ensemble

Dans un contexte où la confidentialité des données et la souveraineté numérique sont cruciales, ce projet vise une alternative robuste aux API cloud propriétaires.

Contrairement aux RAG classiques qui se contentent de générer une réponse, ce système intègre une **couche d'évaluation multi-agents** inspirée des processus de révision humains. Après la génération, un **« Juge »** évalue la qualité, tandis qu'un **« Avocat du diable »** cherche activement les failles logiques ou les hallucinations. Un **« Évaluateur »** final synthétise ces avis avant de retourner la réponse à l'utilisateur.

**Frontend cible** : un vault Obsidian maintenu par le cluster — l'orchestrateur écrit et met à jour des pages markdown interreliées (`index.md`, `log.md`, entités, concepts, synthèses) directement dans un dossier vault. L'utilisateur consulte le graphe de connaissances, les pages et les liens via l'interface Obsidian. Aucune app Tauri/React à maintenir.

---

## 🏗️ Architecture du Système

Voir aussi le schéma complet dans [`docs/architecture.svg`](docs/architecture.svg) (mapping des composants sur les 3 machines du cluster).

### Légende des couleurs (commune à tous les diagrammes)

| Couleur | Rôle | Machine |
|---|---|---|
| 🔵 | Frontend / Entrées-Sorties | Client (Obsidian) |
| 🩵 | Orchestration, API, VectorDB, Embedding CPU, Évaluateur, NFS | **M1** Master |
| 🟢 | Reranker, Juge, Avocat, Backup Embedding CPU | **M2** GPU Worker |
| 🟠 | Générateur, Text-to-SQL, Vision, Fast-check | **M3** BC-250 Baremetal |
| 🩷 | `relay.json` (NFS partagé M1↔M2) | Évaluation séquentielle |
| 🟡 | Backup Cold / Passerelle | Off-site, pfSense |

**Conventions de flèches** : `──▶` flux synchrone · `┄┄▶` asynchrone, feedback ou backup.

### 🗺️ Vue d'ensemble du cluster

![Architecture cluster](docs/diagrams/01-cluster-overview.svg)

### 📥 Flux d'ingestion (offline, asynchrone)

L'ingestion n'est **jamais dans le chemin critique** d'une requête : chunking, embedding et indexation tournent en batch sur le CPU de M1.

![Flux ingestion](docs/diagrams/02-ingestion-flow.svg)

### 🔄 Flux de requête & évaluation multi-agents

![Flux requête évaluation](docs/diagrams/03-query-flow.svg)

---

## 🔐 Plan de Backup (3-2-1)

### Architecture

![Backup 3-2-1](docs/diagrams/04-backup-321.svg)

### Règle 3-2-1

| Règle | Implémentation |
|---|---|
| **3 copies** | Prod + OMV Live + HDD Cold |
| **2 médias** | NVMe + HDD mécanique |
| **1 off-site** | Rotation physique HDD 2 TB |

### Outils & Rétention

| Outil | Usage |
|---|---|
| borg | Sauvegarde dédupliquée, chiffrée, compression LZ4 |
| rsync | Sync configs Ollama, wiki, scripts |
| qdrant snapshot | Backup atomique VectorDB (cron quotidien) |
| LUKS | Chiffrement HDD (clés hors cluster) |
| OMV | Interface NFS/SMB, scheduling cron |

---

## 🌐 Topologie Réseau & Sécurité

![Topologie réseau](docs/diagrams/05-network-topology.svg)

### VLAN / Sous-réseaux

| VLAN | CIDR | Usage | Machines |
|---|---|---|---|
| 10 (Cluster) | `10.10.0.0/24` | Backbone 10G inter-nœuds (Qdrant, Ollama API, NFS) | M1, M2, M3 |
| 20 (WAN) | `192.168.1.0/24` | pfSense → Internet (updates, modèles) | pfSense GW |
| 30 (Mgmt) | `172.16.0.0/24` | Proxmox GUI, IPMI, SSH secours (1G) | M1, M2, M3 |
| 40 (Client) | `192.168.10.0/24` | Obsidian client, Web UI | Client, pfSense |

**Passerelle** : pfSense (VM sur Proxmox M1 — LXC 104 — ou appliance dédiée) — routes inter-VLAN + NAT sortant.

### NFS Relay (évaluation)

- **Export M1 (hôte)** : `/data/shared` → `10.10.0.0/24(rw,sync,no_subtree_check,no_root_squash)` sur `10.10.0.1`
- **Mount M2** : `/data/shared` sur `10.10.0.1:/data/shared` (fstab, `_netdev`)
- **Fichier** : `evaluation-relay.json` (verrou fichier atomique, TTL 300 s)

> ⚠️ **Note** : Le README Qwen mentionnait l'export depuis la VM OMV, mais le NFS pour l'évaluation est exporté par l'hôte M1 (`10.10.0.1`) pour simplicité et performance. L'OMV (LXC 105) gère le backup cold, pas le relay temps-réel.

### Règles Firewall (pfSense) — Flux autorisés

| Source | Dest | Proto/Port | Usage |
|---|---|---|---|
| `10.10.0.0/24` | `10.10.0.0/24` | TCP 6333 | Qdrant (VectorDB) |
| `10.10.0.0/24` | `10.10.0.0/24` | TCP 11434 | Ollama API (M2, M3) |
| `10.10.0.0/24` | `10.10.0.0/24` | TCP 2049/NFS | Relay évaluation + vault wiki |
| `10.10.0.2` | `10.10.0.1` | TCP 2049 | Mount NFS M1→M2 |
| `192.168.10.0/24` | `10.10.0.1` | TCP 80/443 | Client → API Gateway (nginx LXC 102) |
| `10.10.0.0/24` | `192.168.1.0/24` | TCP 80/443 | Sortie modèles/updates (via pfSense NAT) |
| `172.16.0.0/24` | *any* | SSH/HTTPS | Admin Proxmox/IPMI (isolé) |

**MTU** : 9000 (Jumbo frames) sur VLAN 10 pour NFS/Ollama/Qdrant — gain ~15 % débit gros transferts.

---

## 🔗 Intégration avec Obsidian (pattern Karpathy)

Le frontend est un **vault Obsidian standard** — le cluster écrit et met à jour des pages markdown structurées. L'utilisateur ouvre Obsidian, pointe vers le dossier vault, et navigue via le graphe de connaissances.

### Structure du Vault (`/data/wiki`)

```
wiki/
├── index.md              # Catalogue des pages
├── log.md                # Chronologie des interactions
├── entities/             # Personnes, lieux, organisations
├── concepts/             # Idées, thèmes, définitions
├── sources/              # Références originales (ingest)
└── synthesis/            # Analyses, comparatifs, rapports
```

### Convention Frontmatter YAML (aligné OKF v0.2)

```yaml
---
type: "entity|concept|source|synthesis|log|agent|workflow"  # CHAMP OBLIGATOIRE OKF v0.2
title: "Nom de la page"
description: "Résumé 1-2 phrases pour index/search"           # OKF v0.2
resource: "wiki"                                              # OKF v0.2 - type de ressource
tags: ["tag1", "tag2"]                                        # OKF v0.1 base
verified:                                                     # OKF v0.2 - trust tier (Évaluateur = human-reviewed)
  - reviewer: "evaluator-agent"
    status: "human-reviewed"      # unverified | machine-confirmed | human-reviewed
    timestamp: "2026-07-29T10:30:00Z"
status: "stable"                  # draft | stable | deprecated (lint endpoint)
stale_after: "2026-12-31"         # date fraîcheur (lint endpoint)
sources:                          # OKF v0.2 - crédibilité par source
  - uri: "source1.md"
    author: "wiki-agent"
    last_modified: "2026-07-29T10:30:00Z"
    credibility: "high"           # high | medium | low
  - uri: "https://example.com"
    author: "external"
    last_modified: "2026-07-29T10:30:00Z"
    credibility: "medium"
created: "2026-07-29T10:30:00Z"
updated: "2026-07-29T10:30:00Z"
version: 1
---
```

### Endpoints API

| Endpoint | Description |
|---|---|
| `POST /api/v1/ingest` | Envoie une source (fichier, URL, texte) → crée/MAJ pages wiki |
| `POST /api/v1/query` | Pose une question → réponse synthétisée + citations |
| `GET /api/v1/lint` | Health check wiki : pages orphelines, contradictions, gaps |
| `GET /api/v1/embed` | Embedding texte → vecteur dense 1024d + sparse appris (bge-m3) + fallback histogramme |

### Workflow Web Clipper

1. Obsidian Web Clipper (extension navigateur) convertit les articles web en markdown
2. Injection via `curl -X POST ${CLUSTER_API_URL}/api/v1/ingest -F "file=@article.md"`
3. Le cluster : chunk → embed → index → écrit pages wiki → MAJ `index.md` + `log.md`

Ressources : [Obsidian](https://obsidian.md) · [pattern Karpathy LLM Wiki](https://github.com/karpathy/LLMWiki) (inspiration).

---

## ⭐ Fonctionnalités Clés

- 🔒 **100 % Offline & Souverain** : aucune donnée ne quitte le réseau local.
- 🤖 **Évaluation Multi-Agents** : pattern « Juge + Avocat du diable » pour limiter les hallucinations.
- 🔍 **Recherche Hybride** : lexicale (BM25) + vectorielle (sémantique) + variantes (SQL, tables, vision).
- ⚡ **Orchestration Distribuée** : séparation orchestration / inférence GPU / stockage.
- 🛠️ **Hardware Atypique** : exploitation de la puce AMD BC-250 (jusqu'à 40 CUs après unlock) via Vulkan/Mesa.
- 🧠 **Frontend Obsidian Vault** : graphe de connaissances, web clipper, pages markdown maintenues par le cluster en continu.
- 🔄 **Boucle de Feedback** : l'évaluateur peut renvoyer de l'information au planificateur.

---

## 🖥️ Infrastructure Matérielle

| Nœud | Rôle | CPU / RAM | GPU / Accélérateur | Virtualisation |
|---|---|---|---|---|
| **Machine 1** | **Master** (Orchestration, API, VectorDB, Monitoring, Évaluateur, Embedding CPU, Relay NFS) | 2× Xeon E5-2699 v4 / **32 GB ECC** | **AMD Radeon RX 580** (8 GB) — fallback léger uniquement | Proxmox VE 9.3 (LXC 100, 101, 102, 103, 104*, 105) |
| **Machine 2** | **GPU Worker** (Inference, Reranking, Juge, Avocat, Backup Embedding CPU) | 1× Xeon E5-2698 v4 / **64 GB ECC** | **NVIDIA Quadro RTX 4000** (8 GB VRAM dédiée) | Proxmox VE 9.3 (LXC 200 privilégié GPU, 201) |
| **Machine 3** | **BC-250 Baremetal** (Générateur, Text-to-SQL, Vision, Fast-check) | Carte minage BIOS modifiée · Puce PS5 (BC-250, Zen 2, 6c/12t) · **40 CU débloquées** | **16 GB GDDR6 unifiée** CPU+GPU · ~12 GB dispo pour IA (512 MB carve-out dynamique) | **BIOS P3.00+ patché · VRAM dynamique 512 MB** · Debian Testing/Sid (baremetal, Ollama Vulkan natif) |
| **Client** | Obsidian Vault (visualisation + ingestion) | Poste de travail | – | Native (Electron) |

\* LXC 104 = pfSense, uniquement si pas d'appliance dédiée.

### Stockage

| Machine | Disque | Usage |
|---|---|---|
| M1 (Master) | 1 TB NVMe | Proxmox + LXCs + Qdrant + Wiki + **OMV LXC 105** (500 GB dédié backup live) |
| M2 (GPU Worker) | 256 GB NVMe | Proxmox + LXCs + cache Ollama |
| M3 (BC-250) | 475 GB NVMe | OS Debian + Modèles |
| Backup Cold | 2 TB HDD mécanique (USB/SATA, LUKS) | Archive dédupliquée, rétention 30j/12m/3y |

> ⚠️ **OMV : VM ou LXC ?** Le backlog indique LXC 105, mais OMV se déploie classiquement en VM (disque virtio). La décision finale : **LXC 105 avec disque virtio dédié 500 GB** pour simplicité Proxmox. Si problèmes performance → migration VM.

### ⚡ Règle d'or BC-250

> **Le CPU du BC-250 est le serviteur du GPU.** Toute charge CPU significative sur M3 est un vol de bande passante mémoire au Générateur 14B. Le CPU (Zen 2 6c/12t) doit rester au repos (ou charge minimale) quand le GPU fait de l'inférence Vulkan. **Embedding = Machine 1 CPU (principal) / Machine 2 CPU (backup).**
>
> **Preuve** : le BC-250 a 16 GB GDDR6 *unifiée* (CPU+GPU, même pool, même bande passante). Si le CPU est chargé (embedding, batch, compilation) :
> - **Contention bande passante mémoire** → le GPU 14B est affamé
> - **Pression thermique** → CPU + GPU = jusqu'à 235 W TDP dans un format compact → throttling certain
> - **VRAM effective réduite** → le modèle 14B perd des ressources critiques
>
> Références : [AMD BC-250 Documentation](https://elektricm.github.io/amd-bc250-docs/) — Unified Memory Architecture, Vulkan-only, 40 CU unlock · [akandr/bc250](https://github.com/akandr/bc250) — Ollama + Vulkan benchmarks, GFX1013, roofline analysis

### Répartition LXC prévue

| Machine | LXC | Rôle |
|---|---|---|
| Machine 1 | `100` | Orchestrator + Wiki Agent |
| | `101` | Vector DB (Qdrant) |
| | `102` | API Gateway (nginx) |
| | `103` | Monitoring (Prometheus/Grafana/Loki) |
| | `104` | pfSense (option, si pas d'appliance dédiée) |
| | `105` | OMV Backup (500 GB disque virtio dédié) |
| Machine 2 | `200` | Inference GPU (passthrough RTX 4000) — Reranker + Juge |
| | `201` | Workers Agents — Avocat + Backup Embedding CPU |
| Machine 3 | — | Ollama Vulkan natif (pas de LXC) |

### Résumé machines M1 & M2

| Machine | IP (VLAN 10) | Rôle | Hardware | Services |
|---------|-------------|------|----------|----------|
| **M1** (Master) | `10.10.0.1` | Orchestration, API, VectorDB, Embedding CPU, Évaluateur, NFS | 2× Xeon E5-2699 v4 32c/64t, 32 GB ECC, 1 TB NVMe | Qdrant (LXC 101 :6333), Ollama CPU (embedding nomic), nginx API Gateway (LXC 102 :80/443), pfSense (LXC 104), OMV Backup (LXC 105) |
| **M2** (GPU Worker) | `10.10.0.2` | Reranker, Juge, Avocat, Backup Embedding CPU | Xeon 20c/40t, 256 GB NVMe, RTX 4000 (CUDA) | Ollama GPU — Judge qwen3.5:7b / Avocat mistral-3.2:7b (LXC 200-201 :11434), NFS mount depuis M1 |

**Endpoints :** Ollama M1 = `http://10.10.0.1:11434`, Ollama M2 = `http://10.10.0.2:11434`, Qdrant = `http://10.10.0.1:6333`, Gateway = `10.10.0.1:80/443`

### 🖥️ Topologie physique : machines, LXC & flux

![Topologie physique](docs/diagrams/06-physical-topology.svg)

---

## 🛠️ Stack Technique

- **Infrastructure** : Proxmox VE 9.3, LXC, Docker, Docker Compose
- **IA & LLM (Machine 2, RTX 4000)** : Ollama, CUDA, modèles open-weight (Qwen3.5, Mistral, BGE)
- **IA & LLM (Machine 3, BC-250)** : Ollama + backend **Vulkan** (`OLLAMA_VULKAN=1`), Mesa/RADV 25.1+ — **pas ROCm** (non supporté sur GFX1013)
- **IA & LLM (Machine 1)** : embedding `bge-m3` (dense + sparse appris) sur **CPU Xeon (principal)**, en complément de BM25 (lexical exact via Qdrant) ; RX 580 en **fallback léger uniquement** (OpenCL si besoin)
- **Orchestration Agents** : **LangGraph** (choix tranché — graphe d'état explicite, parallélisme natif, checkpointing)
- **Vector Store & DB** : **Qdrant** (hybrid search natif), PostgreSQL, Redis
- **API & Backend** : FastAPI, nginx (reverse proxy LXC 102)
- **Frontend** : **Obsidian Vault** (pattern Karpathy) — pages markdown maintenues par le cluster, visualisation via Obsidian (Electron)
- **Observabilité** : Prometheus, Grafana, Loki

---

## 🚀 Guide d'Installation

> Les scripts référencés ci-dessous sont des **stubs à compléter** — voir [ROADMAP.md](ROADMAP.md) pour l'état d'avancement de chacun.

### 1. Prérequis

- Cluster Proxmox VE 9.3 configuré
- Machine baremetal Debian Testing/Sid avec puce AMD BC-250
- Accès root à toutes les machines
- (Optionnel) poste client pour le vault Obsidian

### 2. Configuration du nœud BC-250 (baremetal)

Ce nœud ne peut pas être virtualisé, il doit tourner en natif.

✅ BIOS déjà flashé : P3.00+ community-patched, VRAM dynamique 512 MB configurée (carve-out UMA).
Voir [BIOS Flashing Guide](https://elektricm.github.io/amd-bc250-docs/bios/flashing/) si besoin de refaire.

Paramètre boot install : `nomodeset` (à retirer après installation de Mesa).

```bash
cd infrastructure/bc250
./setup-vulkan-stack.sh    # Mesa/Vulkan (pas ROCm — voir avertissement en tête de README)
./enable-40cu-unlock.sh    # optionnel : débloque les 16 CU masqués en usine (24 → 40)
```

Puis configurer Ollama pour le backend Vulkan (variables clés, voir `.env.example`) :

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
cat <<EOF | sudo tee /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment=OLLAMA_VULKAN=1
Environment=OLLAMA_FLASH_ATTENTION=1
Environment=OLLAMA_KV_CACHE_TYPE=q4_0
Environment=OLLAMA_CONTEXT_LENGTH=65536
Environment=OLLAMA_MAX_LOADED_MODELS=1
OOMScoreAdjust=-1000
EOF
sudo systemctl daemon-reload && sudo systemctl restart ollama
```

> ⚠️ **Piège documenté** : vérifier **après reboot** que `ttm.pages_limit` tient à `4194304` (`systemd-tmpfiles` peut l'écraser au boot).

### 3. Déploiement des LXC Proxmox

```bash
cd infrastructure/proxmox
sudo ./create-lxc-master.sh   # LXC 100, 101, 102, 103, 104*, 105
sudo ./create-lxc-gpu.sh      # LXC 200 (passthrough GPU), 201
```

### 4. Lancement de la stack Docker

Sur le LXC Master (Orchestrator) :

```bash
cd infrastructure/docker
docker compose -f docker-compose.orchestrator.yml up -d
docker compose -f docker-compose.vector-db.yml up -d
```

### 5. Configuration du vault Obsidian (client)

```bash
mkdir -p ~/rag-wiki-vault
# Monter le vault sur le LXC Master (NFS/SMB) pour que le cluster y écrive
# Ouvrir Obsidian → "Open folder as vault" → sélectionner ~/rag-wiki-vault
```

### 6. Téléchargement des modèles (versions validées backlog 29/07/2026)

```bash
# Sur Machine 2 (RTX 4000) — LXC 200/201
ollama pull qwen3.5:7b@sha256:...             # Juge
ollama pull mistral:7b@sha256:...             # Avocat (mistral-small-3.2:7b n'existe pas → mistral:7b ou mistral-nemo)
ollama pull bge-reranker-v2-m3@sha256:...     # Reranker
# Backup embedding CPU sur M2 (64 GB RAM inutilisée)
ollama pull bge-m3@sha256:...

# Sur Machine 3 (BC-250) — Ollama Vulkan natif
ollama pull qwen3.5:14b@sha256:...            # Générateur principal (Q4_K_M ~9 GB)
ollama pull qwen3.5-35b-a3b@sha256:...        # Générateur alternatif MoE (IQ2_M ~11 GB)
ollama pull qwen3-coder-30b-a3b@sha256:...    # Text-to-SQL / Code (IQ2_M)
ollama pull bge-m3@sha256:...                 # Embedding dense+sparse (pour variantes)
ollama pull llava-next:13b@sha256:...         # Vision (Phase 5.2)
ollama pull qwen2.5-vl@sha256:...             # Vision alt (Phase 5.2)
ollama pull granite-4.0-h-tiny@sha256:...     # Fast-check lexical (Phase 5.4)

# Sur Machine 1 (secours / embedding léger)
ollama pull nomic-embed-text@sha256:...       # Embedding secours
ollama pull qwen2.5:3b@sha256:...             # Monitoring / fallback
```

> 🔒 **Reproductibilité** : fixer les digests SHA256 dans `.env` / `docker-compose` — `ollama pull model@sha256:...` évite les surprises de tags mobiles.

---

## 💻 Utilisation

### Via API (cURL)

```bash
curl -X POST "${CLUSTER_API_URL}/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Quelle est la stratégie de déploiement recommandée pour le BC250 ?",
    "context": "infrastructure"
  }'
```

`CLUSTER_API_URL` est défini dans `.env` (voir `.env.example`) — **ne jamais coder l'IP du cluster en dur** dans les exemples ou les scripts commités.

### Via Obsidian

- Ouvrir le vault Obsidian sur le poste client (vault partagé avec le cluster)
- Naviguer dans les pages wiki (`index.md`, `entities/`, `concepts/`, `sources/`)
- Utiliser le **graphe de connaissances** (Obsidian Graph View) pour explorer les liens
- Les pages sont mises à jour automatiquement par le cluster via les endpoints API

```bash
# Ajouter une source
curl -X POST ${CLUSTER_API_URL}/api/v1/ingest -F "file=@article.md"
# Poser une question
curl -X POST ${CLUSTER_API_URL}/api/v1/query -d '{"question":"..."}'
```

---

## 🗺️ Roadmap

Voir [ROADMAP.md](ROADMAP.md) pour le détail et l'état réel d'avancement (rien n'est encore fait — ce projet part de zéro sur le code, seule la conception documentaire existe).

> ✅ **Déjà tranché** : Choix CrewAI vs LangGraph → **LangGraph** (écrit dans ce README et le backlog). AntiX-26 vs Debian pour M3 → **Debian Testing/Sid** (baremetal).

---

## ⚠️ Points de Vigilance DevOps (Risques Maîtrisés)

| Risque | Impact | Mitigation |
|---|---|---|
| **SPOF : Machine 1 (Master)** | Qdrant + API + Wiki + Évaluateur + NFS = tout s'arrête si M1 tombe | Backup Qdrant snapshot quotidien sur M2. NFS export read-only possible depuis M2. |
| **Latence NFS sur évaluation** | Relay file = point de synchronisation bloquant | MTU 9000 + 10 GbE = <1 ms RTT. Timeout 120 s Juge → Avocat. Acceptable. |
| **BC-250 baremetal = pas de snapshot/rollback** | Mise à jour noyau/BIOS risquée | Tests sur VM simulée d'abord. Backup config `/etc` + BIOS P3.00 sur USB. |
| **RTX 4000 8 GB limite dure** | Pas de place pour un modèle > 7B quantifié | Choix validé : Juge/Avocat 7B max. Si besoin 14B → seul le BC-250 peut. |
| **Modèles non verrouillés (tags Ollama)** | `pull qwen3.5:7b` = version mobile → reproductibilité | Fixer digests SHA256 dans `.env` / `docker-compose`. `ollama pull qwen3.5:7b@sha256:...` |
| **Concurrency lock vault Obsidian** | Client + cluster écrivent simultanément | NFS `no_root_squash` + file locking (fcntl). Ou versioning git sidecar. |

### Recommandations immédiates

1. **Lock les versions modèles** — Ajouter dans `.env` : `OLLAMA_MODEL_JUDGE=qwen3.5:7b@sha256:xxx` etc.
2. **Health checks obligatoires** — `/health` sur chaque service (Ollama, Qdrant, API) → Prometheus scrape.
3. **Secrets management** — Pas de tokens/API keys en dur. `sops` + `.env.encrypted` ou Vault (Phase 7).
4. **Backup Qdrant** — `qdrant snapshot create` cron quotidien → stocké sur M2 (64 GB dispo).
5. **Test de charge pré-prod** — `hey` / `locust` sur `/api/v1/query` avec 10-50 RPS avant mise en prod.
6. **Runbook incident** — Documenter : « BC-250 ne boot plus », « RTX 4000 OOM », « NFS stale handle », « Qdrant corruption ».

---

## 🤝 Contribuer

1. Fork le projet
2. Créer une branche (`git checkout -b feature/AmazingFeature`)
3. Committer (`git commit -m 'Add some AmazingFeature'`)
4. Push (`git push origin feature/AmazingFeature`)
5. Ouvrir une Pull Request

## 📄 Licence

Ce projet est distribué sous licence MIT — voir [LICENSE](LICENSE).

## 🙏 Remerciements

- [karpathy](https://github.com/karpathy) pour le pattern [LLM Wiki](https://github.com/karpathy/LLMWiki), qui inspire l'architecture frontend
- La communauté Proxmox et la communauté BC-250 ([elektricM/amd-bc250-docs](https://github.com/elektricM/amd-bc250-docs), [akandr/bc250](https://github.com/akandr/bc250), [duggasco/bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock)) pour le support hardware atypique
- La communauté open-source IA pour les modèles open-weight

*Développé pour l'IA souveraine, le hardware open-source et les seconds cerveaux locaux (Obsidian + LLM).*
