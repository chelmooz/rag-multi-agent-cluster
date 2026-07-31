# Guide de Déploiement — Cluster RAG Multi-Agents

Plan d'installation pas-à-pas pour les 3 machines du cluster.

---

## Sommaire

1. [Machine 1 — Control Plane (Proxmox, LXC 100-101, 103, VM 104)](#machine-1--control-plane)
2. [Machine 2 — Compute & Storage Plane (Proxmox, LXC 103, 105, 200-201)](#machine-2--gpu-worker--services-compute--storage-plane)
3. [Machine 3 — BC-250 Baremetal (Debian Testing/Sid)](#machine-3--bc-250-baremetal)
4. [Déploiement Docker & Services](#4-déploiement-docker--services)
5. [Téléchargement des Modèles](#5-téléchargement-des-modèles)
6. [Vérification du Cluster](#6-vérification-du-cluster)

---

## Machine 1 — Control Plane (Master)

**Matériel** : Dual Xeon E5-2699 v3 (36c/72t), 32 GB DDR4 ECC, 1 TB NVMe, Proxmox VE 9.3

| LXC/VM | IP | vCPU | RAM | Disque | Rôle |
|--------|----|------|-----|--------|------|
| 100 | 10.10.0.100 | 8 | 10 GB | 50 GB | Orchestrator + Wiki Agent (Docker) |
| 101 | 10.10.0.101 | 6 | 8 GB | 80 GB | Vector DB (Docker : Qdrant, Postgres, Redis) |
| 103 | 10.10.0.103 | 4 | 2 GB | 50 GB | Monitoring (Prometheus, Grafana, Loki) |
| 104 | — | 1 | 512 MB | — | pfSense (VM, reverse proxy + firewall + NAT) |

### Ordre d'exécution

#### 1.1 Préparer l'hôte Proxmox

```bash
# Template Debian 12
pveam update
pveam download local debian-12-standard_12.7-1_amd64.tar.zst

# Créer le bridge VLAN 10 (cluster backbone)
pvesh create /nodes/proxmox/network --type bridge --iface vmbr10 \
  --bridge_ports <interface_10g> --autostart 1 --vlan_aware 1 \
  --cidr 10.10.0.1/24
```

#### 1.2 Créer les LXC

```bash
cd infrastructure/proxmox
bash create-lxc-master.sh
```

#### 1.3 Post-installation LXC 100 (Orchestrator)

```bash
pct enter 100

# Docker
apt update && apt install -y curl ca-certificates
curl -fsSL https://get.docker.com | sh

# NFS mount
mkdir -p /data/wiki /data/raw /data/index /data/shared
echo "10.10.0.1:/data/shared /data/shared nfs rw,hard,intr,noatime,noexec 0 0" >> /etc/fstab
mount -a

# Lancer la stack orchestrator
cd /path/to/infrastructure/docker
docker compose -f docker-compose.orchestrator.yml up -d
```

#### 1.4 Post-installation LXC 101 (Vector DB)

```bash
pct enter 101
curl -fsSL https://get.docker.com | sh
cd /path/to/infrastructure/docker
docker compose -f docker-compose.vector-db.yml up -d

# Vérifier
curl http://localhost:6333/health
curl http://localhost:6333/collections
```

#### 1.5 Hôte M1 — NFS export + Ollama CPU + Monitoring (LXC 103)

```bash
# NFS relay pour l'évaluation séquentielle
apt install -y nfs-kernel-server
mkdir -p /data/shared
chmod 777 /data/shared
echo "/data/shared 10.10.0.0/24(rw,sync,no_subtree_check,no_root_squash)" >> /etc/exports
exportfs -a
systemctl enable --now nfs-server

# Ollama CPU (embedding + évaluateur)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull nomic-embed-text-v2-moe
ollama pull qwen3.5:3b
```

> Note : Le Monitoring (LXC 103 — Prometheus/Grafana/Loki) est déployé sur Machine 2, pas sur M1.
> Voir section 2.3 du guide Machine 2.

---

## Machine 2 — GPU Worker + Services (Compute & Storage Plane)

**Matériel** : Xeon E5-2698 v3 (16c/32t), 64 GB ECC, **1 TB NVMe**, RTX 4000 8 GB VRAM, Proxmox VE 9.3

| LXC | IP | vCPU | RAM | Disque | Rôle |
|-----|----|------|-----|--------|------|
| 103 | 10.10.0.103 | 4 | 2 GB | 50 GB | Monitoring (Prometheus, Grafana, Loki) |
| 105 | 10.10.0.105 | 2 | 4 GB | 20 GB | **OMV Backup** (Docker - HDD 2TB passthrough) |
| 200 | 10.10.0.200 | 6 | 8 GB | 30 GB | Inference GPU (passthrough RTX 4000, privilégié) |
| 201 | 10.10.0.201 | 4 | 8 GB | 30 GB | Workers Agents (Avocat + Backup Embedding CPU) |

### 2.1 Config GPU passthrough sur l'hôte Proxmox

```bash
# Activer IOMMU
sed -i 's/GRUB_CMDLINE_LINUX_DEFAULT=".*"/GRUB_CMDLINE_LINUX_DEFAULT="quiet intel_iommu=on iommu=pt"/' /etc/default/grub
update-grub

# Modules VFIO
echo -e "vfio\nvfio_iommu_type1\nvfio_pci\nvfio_virqfd" > /etc/modules
update-initramfs -u -k all

# Isoler le RTX 4000
lspci -nn | grep -i nvidia   # trouver l'ID PCI, ex: 10de:1b80
echo "options vfio-pci ids=10de:1b80 disable_vga=1" > /etc/modprobe.d/vfio.conf

reboot
```

### 2.2 Créer les LXC

```bash
cd infrastructure/proxmox
bash create-lxc-gpu.sh
```

### 2.3 Post-installation LXC 103 (Monitoring)

```bash
pct enter 103

# Docker
curl -fsSL https://get.docker.com | sh

# Prometheus
docker run -d --name prometheus --restart unless-stopped \
  -p 9090:9090 -v /etc/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus:latest

# Grafana
docker run -d --name grafana --restart unless-stopped \
  -p 3000:3000 -e GF_SECURITY_ADMIN_PASSWORD=CHANGE_ME \
  grafana/grafana:latest

# Loki
docker run -d --name loki --restart unless-stopped \
  -p 3100:3100 -v /etc/loki/config.yaml:/etc/loki/config.yaml \
  grafana/loki:latest
```

### 2.4 Post-installation LXC 200 (Inference GPU)

```bash
pct enter 200

# Drivers NVIDIA CUDA
apt update && apt install -y curl gnupg
wget https://developer.download.nvidia.com/compute/cuda/repos/debian12/x86_64/cuda-keyring_1.1-1_all.deb
dpkg -i cuda-keyring_1.1-1_all.deb
apt update
apt install -y cuda-drivers-545   # version compatible RTX 4000

# Vérifier
nvidia-smi

# Ollama CUDA
curl -fsSL https://ollama.com/install.sh | sh
mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/override.conf << EOF
[Service]
Environment=OLLAMA_HOST=0.0.0.0
Environment=CUDA_VISIBLE_DEVICES=0
Environment=OLLAMA_MAX_LOADED_MODELS=1
EOF
systemctl daemon-reload && systemctl restart ollama

# Models
ollama pull qwen3.5:7b        # Judge (~5 GB Q4_K_M)
ollama pull bge-reranker-v2-m3

# NFS mount relay
mkdir -p /data/shared
echo "10.10.0.1:/data/shared /data/shared nfs rw,hard,intr,noatime 0 0" >> /etc/fstab
mount -a
```

### 2.5 Post-installation LXC 105 (OMV Backup)

```bash
pct enter 105

# Docker + OMV Container
apt update && apt install -y curl ca-certificates
curl -fsSL https://get.docker.com | sh

# Create OMV directory and mount HDD passthrough
mkdir -p /srv/backup
# HDD should be passed through from host: pct set 105 -mp0 /dev/disk/by-id/<HDD-ID>,mp=/srv/backup

# Deploy OMV via Docker
docker run -d \
  --name openmediavault \
  --restart=unless-stopped \
  -p 80:80 -p 443:443 \
  -v /srv/backup:/srv/backup \
  -v /omv/config:/app/openmediavault/config \
  -v /omv/data:/var/lib/openmediavault \
  --device /dev/sda:/dev/sda \  # Example - adjust to actual HDD device
  --privileged \
  linuxserver/openmediavault

# Access OMV web interface at http://10.10.0.105
# Initial setup: create admin user, configure SSH access, set up shared folders

# Configure Borg repository
apt update && apt install -y borgbackup ssh
mkdir -p /var/log/borg

# SSH key for pulling from M1 and BC250 (generate on OMV, copy to targets)
ssh-keygen -t ed25519 -f /root/.ssh/omb_backup -N ""

# Borg repository initialization (run once)
borg init --encryption=repokey /srv/backup/borg-repo
```

### 2.6 Cron OMV Backup (heures creuses IA)

```bash
# Edit crontab on OMV (via SSH or WebGUI > Scheduled Jobs)
0 2 * * * /usr/bin/borg pull --log-json root@10.10.0.1:/var/lib/qdrant/snapshots /srv/backup/borg-repo::qdrant-{hostname}-{now:%Y-%m-%d_%H-%M-%S} >> /var/log/borg/qdrant_pull.log 2>&1
30 2 * * * /usr/bin/rsync -avz --delete root@10.10.0.1:/data/wiki/ /srv/backup/wiki/ >> /var/log/borg/wiki_sync.log 2>&1
30 2 * * * /usr/bin/rsync -avz --delete root@10.10.0.1:/etc/ /srv/backup/configs/m1/ >> /var/log/borg/config_sync.log 2>&1
30 2 * * * /usr/bin/rsync -avz --delete root@10.10.0.2:/etc/ /srv/backup/configs/m2/ >> /var/log/borg/config_sync.log 2>&1
30 2 * * * /usr/bin/rsync -avz --delete root@10.10.0.3:/etc/ /srv/backup/configs/m3/ >> /var/log/borg/config_sync.log 2>&1
0 3 * * * /usr/bin/borg create --compression lz2 /srv/backup/borg-repo::backup-{now:%Y-%m-%d_%H-%M-%S} /srv/backup/wiki/ /srv/backup/configs/ /srv/backup/ollama-cache/ >> /var/log/borg/borg_create.log 2>&1
0 5 * * 0 /usr/bin/borg prune -v --list /srv/backup/borg-repo --keep-daily=14 --keep-monthly=3 >> /var/log/borg/borg_prune.log 2>&1
```

---

## Machine 3 — BC-250 Baremetal

**Matériel** : AMD BC-250 (Zen 2, 40 CU unlock, 16 GB GDDR6 unifiée), Debian Testing/Sid

### 3.1 Installation OS de base

```bash
# Installer Debian Testing/Sid avec paramètre boot: nomodeset
# Partition : /boot 1G, / 100G, swap 16G, reste pour /var/lib/ollama
# Après installation, retirer nomodeset

apt update && apt upgrade -y
apt install -y linux-headers-$(uname -r) build-essential curl git \
  mesa-utils vulkan-tools glmark2
```

### 3.2 Stack Vulkan (Mesa/RADV)

```bash
cd infrastructure/bc250
bash setup-vulkan-stack.sh

# Vérification
vulkaninfo --summary | grep -i "GFX1013\|deviceName"
# Attendu : Mesa 25.1+, RADV GFX1013
```

### 3.3 TTM pages_limit (critique — modèles 14B+)

```bash
echo 4194304 | sudo tee /sys/module/ttm/parameters/pages_limit
echo 4194304 | sudo tee /sys/module/ttm/parameters/page_pool_size
echo "options ttm pages_limit=4194304 page_pool_size=4194304" | tee /etc/modprobe.d/ttm-gpu-memory.conf

# Vérifier persistance post-reboot
cat /sys/module/ttm/parameters/pages_limit
# DOIT afficher 4194304
```

### 3.4 GRUB

```bash
sed -i 's/GRUB_CMDLINE_LINUX_DEFAULT=".*"/GRUB_CMDLINE_LINUX_DEFAULT="amdgpu.gttsize=14750 ttm.pages_limit=3959290 ttm.page_pool_size=3959290 amdgpu.sg_display=0"/' /etc/default/grub
update-grub
```

### 3.5 Unlock 40 CU (optionnel, +32 à +61 % tok/s)

```bash
bash enable-40cu-unlock.sh
# Clone, build, enable, reboot
# Vérifier : sudo dmesg | grep active_cu_number → 40
```

### 3.6 Unlock 8 cores CPU (optionnel, volatil après cold boot)

```bash
bash enable-cpu-core-unlock.sh
# Vérifier : lscpu | grep CPU(s) → 16
```

### 3.7 Gouverneur GPU (1500 MHz / 900 mV)

```bash
# Installer cyan-skillfish-governor-smu
# Config dans /etc/cyan-skillfish-governor-smu/config.toml
systemctl enable --now cyan-skillfish-governor-smu.service
```

### 3.8 Ollama Vulkan

```bash
curl -fsSL https://ollama.com/install.sh | sh
mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/override.conf << EOF
[Service]
Environment=OLLAMA_VULKAN=1
Environment=OLLAMA_FLASH_ATTENTION=1
Environment=OLLAMA_KV_CACHE_TYPE=q4_0
Environment=OLLAMA_CONTEXT_LENGTH=65536
Environment=OLLAMA_MAX_LOADED_MODELS=1
Environment=OLLAMA_HOST=0.0.0.0
OOMScoreAdjust=-1000
EOF
systemctl daemon-reload && systemctl restart ollama
```

### 3.9 NFS mount

```bash
mkdir -p /data/shared /data/wiki
echo "10.10.0.1:/data/shared /data/shared nfs rw,hard,intr,noatime 0 0" >> /etc/fstab
echo "10.10.0.1:/data/wiki /data/wiki nfs ro,hard,intr,noatime 0 0" >> /etc/fstab
mount -a
```

---

## 4 Déploiement Docker & Services

### 4.1 Stack Vector DB (LXC 101)

```bash
cd infrastructure/docker
docker compose -f docker-compose.vector-db.yml up -d
```

### 4.2 Stack Orchestrator (LXC 100)

```bash
cd infrastructure/docker
docker compose -f docker-compose.orchestrator.yml up -d
```

### 4.3 Reverse Proxy & TLS (pfSense VM 104)

pfSense (VM 104 sur M1) gère le reverse proxy, la terminaison TLS et le NAT. Configurez-le via l'interface web :

1. **Interface LAN (VLAN 10)** : IP `10.10.0.254/24`
2. **Firewall rule** : Autoriser `TCP 80/443` depuis VLAN 40 (Client) → DNAT vers `10.10.0.100:8000` (LXC 100)
3. **TLS** : Générer ou importer un certificat (Let's Encrypt pour LAN, ou auto-signé via pfSense CA)
4. **NAT outbound** : Autoriser M1/M2/M3 à sortir vers Internet (VLAN 20) pour updates/modèles

```bash
# Sur M1 hôte : exporter la configuration pfSense
# Via WebUI : Diagnostics → Backup/Restore → Exporter la config
# Versionner dans infrastructure/proxmox/pfsense-config.xml
```

### 4.4 Stack OMV Backup (LXC 105)

```bash
# Depuis l'hôte Proxmox M2
pct enter 105
docker compose -f /srv/omv/docker-compose.yml up -d
```

> Voir section 2.5 pour le détail de l'installation OMV + HDD passthrough + borg.

---

## 5 Téléchargement des Modèles

### Machine 2 — LXC 200 (RTX 4000, CUDA)

```bash
ollama pull qwen3.5:7b@sha256:...
ollama pull bge-reranker-v2-m3@sha256:...
```

### Machine 2 — LXC 201 (CPU, fallback)

```bash
ollama pull mistral-small-3.2:7b@sha256:...
ollama pull bge-m3@sha256:...
```

### Machine 3 — BC-250 (Vulkan)

```bash
ollama pull qwen3.5:14b@sha256:...            # Générateur (~9 GB)
ollama pull qwen3.5-35b-a3b@sha256:...        # Générateur alternatif (~11 GB)
ollama pull qwen3-coder-30b-a3b@sha256:...    # Text-to-SQL
ollama pull llava-next:13b@sha256:...          # Vision
ollama pull granite-4.0-h-tiny@sha256:...      # Fast-check
```

### Machine 1 — Hôte (CPU)

```bash
ollama pull nomic-embed-text-v2-moe@sha256:... # Embedding
ollama pull qwen3.5:3b@sha256:...              # Monitoring / fallback
```

> ⚠️ Fixer les digests SHA256 dans `.env` pour garantir la reproductibilité.

---

## 6 Vérification du Cluster

```bash
# Depuis n'importe quel nœud du VLAN 10 (10.10.0.0/24) :
curl http://10.10.0.100:8000/api/v1/health     # LXC 100 FastAPI
curl http://10.10.0.101:6333/health            # LXC 101 Qdrant
curl http://10.10.0.103:9090                    # LXC 103 Prometheus
curl http://10.10.0.103:3000                    # LXC 103 Grafana
curl http://10.10.0.105:80                      # LXC 105 OMV Web UI
curl http://10.10.0.200:11434/api/tags         # LXC 200 Ollama GPU
curl http://10.10.0.201:11434/api/tags         # LXC 201 Ollama CPU
curl http://10.10.0.3:11434/api/tags           # M3 BC-250 Ollama Vulkan
```

### Endpoints de référence

| Service | URL |
|---------|-----|
| API (publique, via pfSense DNAT) | `https://<domain>:443/api/v1/` |
| API (interne) | `http://10.10.0.100:8000/api/v1/` |
| Qdrant | `http://10.10.0.101:6333` |
| PostgreSQL | `10.10.0.101:5432` |
| Redis | `10.10.0.101:6379` |
| Ollama M2 GPU | `http://10.10.0.200:11434` |
| Ollama M2 CPU | `http://10.10.0.201:11434` |
| Ollama M3 BC-250 | `http://10.10.0.3:11434` |
| Ollama M1 CPU (host) | `http://10.10.0.1:11434` |
| Prometheus | `http://10.10.0.103:9090` |
| Grafana | `http://10.10.0.103:3000` |
| Loki | `http://10.10.0.103:3100` |
| OMV Backup | `http://10.10.0.105:80` |
| NFS relay | `10.10.0.1:/data/shared` → `/data/shared` |

---

## Allocation mémoire / vCPU (rappel)

### Machine 1 — Control Plane (Dual Xeon E5-2699 v3, 32 GB, 1 TB NVMe)

| LXC | vCPU | RAM | Usage |
|-----|------|-----|-------|
| 100 | 8 | 10 GB | Orchestrator + Wiki Agent |
| 101 | 6 | 8 GB | Vector DB |
| 102 | 1 | 512 MB | API Gateway |
| 104 (VM) | 1 | 512 MB | pfSense (optionnel) |
| **Total** | **16** | **~19 GB** | **~13 GB libre pour Proxmox + burst** |



### Machine 2 — Compute & Storage Plane (Xeon E5-2698 v3, 64 GB, 1 TB NVMe, RTX 4000)

| LXC | vCPU | RAM | VRAM GPU | Usage |
|-----|------|-----|----------|-------|
| 103 | 4 | 2 GB | — | Monitoring (Prometheus/Grafana/Loki) |
| 200 | 6 | 8 GB | 8 GB (passthrough) | Judge + Reranker |
| 201 | 4 | 8 GB | — | Avocat + Backup Embedding |
| **Total** | **14** | **18 GB** | **8 GB VRAM** | **cache modèles + cold save ponctuel** |

### Machine 3 (BC-250, 16 GB GDDR6 unifiée)

Pas de LXC — Ollama Vulkan natif. Mémoire GDDR6 partagée CPU/GPU (max ~12 GB dispo pour IA, le reste pour le système).

---

*Document généré le 31/07/2026 — Phase 0 du projet.*
