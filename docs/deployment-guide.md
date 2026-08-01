# Guide de Déploiement — Cluster RAG Multi-Agents

Plan d'installation pas-à-pas pour les 3 machines du cluster.

---

## Sommaire

1. [Machine 1 — Control Plane (Proxmox, LXC 100-101, VM 104)](#machine-1--control-plane)
2. [Machine 2 — Compute & Storage Plane (Proxmox, LXC 105, 200-201)](#machine-2--gpu-worker--services-compute--storage-plane)
3. [Machine 3 — BC-250 Baremetal (Fedora 43)](#machine-3--bc-250-baremetal)
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

#### 1.5 Hôte M1 — NFS export + Ollama CPU

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
ollama pull hf.co/nomic-ai/nomic-embed-text-v2-moe-GGUF:Q8_0
ollama pull hf.co/ibm-granite/granite-4.1-8b-instruct-GGUF:Q4_K_M
```

> Note : Plus de Monitoring LXC 103 (décision D9) — supervision via graphs natifs Proxmox + pfSense, et Glances sur BC-250 (cf. section 3).

---

## Machine 2 — GPU Worker + Services (Compute & Storage Plane)

**Matériel** : Xeon E5-2698 v3 (16c/32t), 64 GB ECC, **1 TB NVMe**, RTX 4000 8 GB VRAM, Proxmox VE 9.3

| LXC | IP | vCPU | RAM | Disque | Rôle |
|-----|----|------|-----|--------|------|
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

### 2.3 Monitoring — graphs natifs Proxmox uniquement

> Décision D9 (31/07/2026) : **plus de Prometheus/Grafana/Loki (LXC 103 retiré)**.
> Supervision M1/M2 via l'UI Proxmox (graphs RRD natifs CPU/RAM/disk/network).
> Supervision BC-250 via **Glances** (mode web `glances -w`) — cf. section 3.

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
ollama pull hf.co/bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF:Q4_K_M        # Judge (~5 GB Q4_K_M)
ollama pull hf.co/gpustack/bge-reranker-v2-m3-GGUF:Q4_K_M                # Reranker (RTX 4000)

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

**Matériel** : AMD BC-250 (Zen 2, 8c/16t core unlock BIOS, 40 CU unlock, 16 GB GDDR6 unifiée), **Fedora 43**

> **Décision 02/08/2026** : OS M3 = **Fedora 43** (recommandé #1 par la doc
> communautaire [elektricm/amd-bc250-docs](https://elektricm.github.io/amd-bc250-docs/)
> — Mesa 25.1+ dans les repos mainline, kernel LTS, scripts packagés, le plus
> testé). Debian Testing/Sid abandonné : Mesa depuis experimental + compilation
> manuelle + Xanmod requis = maintenance inutile pour un nœud baremetal.

### 3.0 BIOS — flash Forbidden-Darkness (OBLIGATOIRE, une seule fois)

Avant toute installation OS, flasher le BIOS moddé Forbidden-Darkness.
C'est un BIOS **complet** (base P3.00 incluse, pas de flash P3.00 stock
préalable). Il rend **persistant** le core unlock 6→8 et configure le
**carve-out VRAM dynamique 512 MB** (rien à refaire après cold boot).

| Élément | Détail |
|---|---|
| **Repo BIOS** | [Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script) |
| **BIOS final** | BIOS moddé Forbidden-Darkness complet (base P3.00 + core unlock + VRAM 512 MB) — flash UEFI direct, AUCUN flash P3.00 stock préalable |
| **Effet 1 — Core unlock** | **8c/16t** persistant (flash BIOS, plus de script volatil SMU) |
| **Effet 2 — VRAM dynamique** | **512 MB carve-out** dynamique (~12 GB dispo IA sur 16 GB unifiée) |
| **Risque** | Flash BIOS = irréversible, pas de snapshot. Garder une sauvegarde du BIOS d'origine sur USB (rollback recovery) + backup config `/etc`. |

```bash
# ⚠️ À faire une fois, hors ligne, avant d'installer Fedora.
# Suivre le menu script du repo Forbidden-Darkness :
git clone https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script.git
cd AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script
# Lire le README — le repo fournit l'image BIOS complète à flasher en UEFI
# (dd de l'image sur une clé). Aucun flash P3.00 stock en amont.
# Le BIOS inclu d'office : core unlock 8c/16t + carve-out VRAM dynamique 512 MB

# Vérification après flash (dans le setup BIOS) :
#   - 8 cores / 16 threads visibles
#   - VRAM dynamic 512 MB
```

> ⚠️ **Ne pas utiliser** Smokeless_UMAF (dégâts permanents documentés) ni
> `amd_iommu=on` dans les cmdlines GRUB.

### 3.1 Installation Fedora 43

```bash
# 1. Télécharger l'ISO Fedora 43 Workstation
#    https://fedoraproject.org/workstation/download

# 2. Créer la clé USB bootable
#    sudo dd if=Fedora-Workstation-Live-x86_64-43.iso of=/dev/sdX bs=1M status=progress

# 3. Boot : sélectionner "Troubleshooting" → "Install in Basic Graphics Mode"
#    (évite l'écran noir — no modele vidéo au boot)

# 4. Partitionnement manuel (recommandé) :
#    /boot/efi  1G   (esp)
#    /boot      1G
#    /          100G (btrfs/xfs — systèmes)
#    swap       16G  (utile pour batch mémoire)
#    /var/lib/ollama  reste (~357 GB NVMe) — modèles 14B/30B

# 5. Réseau : configurer l'interface Ethernet 1GbE en statique
#    IP 10.10.0.3/24 · GW 10.10.0.254 (pfSense) · DNS 10.10.0.254
#    nmcli con mod <IFACE> ipv4.method manual \
#      ipv4.addresses 10.10.0.3/24 ipv4.gateway 10.10.0.254 ipv4.dns 10.10.0.254

# 6. Après installation : mises à jour
sudo dnf update -y
sudo dnf install -y mesa-vulkan-drivers vulkan-tools glmark2 \
  kernel-headers kernel-devel gcc make curl git
```

### 3.2 Kernel — pinner 6.18.18 LTS (CRITIQUE)

```bash
# Kernels CASSES sur BC-250 (panics) : 6.15.0-6.15.6 et 6.17.8-6.17.10
# 6.18.18 LTS = recommandé, stable.

sudo dnf install -y kernel-6.18.18   # si non déjà installé par défaut
sudo dnf versionlock add kernel kernel-core kernel-modules
# (ou) /etc/dnf/plugins/versionlock.list + dnf config-manager --save --setopt=excludepkgs

# Vérifier la version active :
uname -r   # attendu : 6.18.18
```

### 3.3 Vérification stack Vulkan (Mesa/RADV)

```bash
vulkaninfo --summary | grep -i "deviceName\|apiVersion\|GFX1013"
# Attendu : Mesa 25.1+ (Fedora 43 mainline), RADV GFX1013
# Sinon : sudo dnf upgrade mesa-vulkan-drivers
```

### 3.4 TTM pages_limit (critique — modèles 14B+)

```bash
sudo sh -c 'echo options ttm pages_limit=3959290 page_pool_size=3959290 > /etc/modprobe.d/ttm-gpu-memory.conf'
# (triplet GRUB ci-dessous fait pareil au boot — les deux sont gardés par sécurité)

# Vérifier persistance post-reboot
cat /sys/module/ttm/parameters/pages_limit
# DOIT afficher 3959290
```

### 3.5 GRUB — cmdline obligatoire

```bash
sudo sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT="quiet amdgpu.gttsize=14750 ttm.pages_limit=3959290 ttm.page_pool_size=3959290 amdgpu.sg_display=0"/' /etc/default/grub
sudo grub2-mkconfig -o /boot/grub2/grub.cfg
sudo reboot
```

> Triplet : `amdgpu.gttsize=14750` (~15 GiB GTT) + `ttm.pages_limit/page_pool_size`
> (3959290 pages = ~15 GiB). **Jamais** `amd_iommu=on` sur BC-250.

### 3.6 Unlock 40 CU (duggasco, +32 à +61 % tok/s)

> **Pré-requis** : stack Vulkan fonctionnelle (§3.3) et GRUB posé (§3.5).
> Le core unlock 8c/16t est déjà fait par le BIOS (§3.0) — ce script ne
> concerne QUE les Compute Units GPU (24 → 40).

```bash
bash infrastructure/bc250/enable-40cu-unlock.sh
# Patch : https://github.com/duggasco/bc250-40cu-unlock
# (build module amdgpu patché, écrit config modprobe, reboot)

# Vérification post-reboot (OBLIGATOIRE) :
cat /sys/module/amdgpu/parameters/bc250_cc_write_mode   # → 3
sudo dmesg | grep active_cu_number                      # → 40
RADV_DEBUG=info vulkaninfo --summary 2>&1 | grep num_cu # → 40
```

> ⚠️ Chaque `dnf upgrade` du kernel écrase le patch — rebuild à prévoir
> (`sudo ./scripts/bc250-enable-40cu.sh build` puis `enable`).

### 3.7 Gouverneur GPU (cyan-skillfish-governor-smu — 1500 MHz / 900 mV)

```bash
# Fedora : packagé via COPR (pas de compilation manuelle)
sudo dnf copr enable filippor/bazzite
sudo dnf install -y cyan-skillfish-governor-smu

# Config safe-points (usage soutenu, pas d'overclock) :
# /etc/cyan-skillfish-governor-smu/config.toml
#   freq 1500 MHz / voltage 900 mV (cf. settings BC250_GOV_FREQ_MHZ/VOLTAGE_MV)

sudo systemctl enable --now cyan-skillfish-governor-smu.service
sudo systemctl status cyan-skillfish-governor-smu.service
```

### 3.8 Ollama Vulkan

```bash
curl -fsSL https://ollama.com/install.sh | sh

sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf > /dev/null << 'EOF'
[Service]
Environment=OLLAMA_VULKAN=1
Environment=OLLAMA_FLASH_ATTENTION=1
Environment=OLLAMA_KV_CACHE_TYPE=q4_0
Environment=OLLAMA_CONTEXT_LENGTH=65536
Environment=OLLAMA_MAX_LOADED_MODELS=1
Environment=OLLAMA_HOST=0.0.0.0
OOMScoreAdjust=-1000
EOF

sudo systemctl daemon-reload && sudo systemctl restart ollama
sudo systemctl enable ollama

# Modèles M3 (Générateur + variantes) — digests SHA256 dans .env :
ollama pull hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M@sha256:...            # Générateur ~9 GB
ollama pull hf.co/Qwen/Qwen3-30B-A3B-GGUF:Q2_K@sha256:...          # Alt MoE ~11.3 GB
ollama pull hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q2_K@sha256:...  # Text-to-SQL
ollama pull hf.co/cjpais/llava-v1.6-vicuna-13b-gguf:Q4_K_M@sha256:...        # Vision
ollama pull hf.co/ibm-granite/granite-4.0-h-tiny-GGUF:Q4_K_M@sha256:...      # Fast-check
```

### 3.9 Glances — monitoring BC-250 (décision D9)

```bash
# Glances remplace Prometheus/Grafana (D9) — le BC-250 n'a pas Proxmox
sudo dnf install -y glances
sudo systemctl enable --now glances \
  --no-pager 2>/dev/null || true

# Mode web exposé sur :61208 (écoute réseau)
sudo tee /etc/systemd/system/glances-web.service > /dev/null << 'EOF'
[Unit]
Description=Glances web monitoring (BC-250)
After=network.target

[Service]
ExecStart=/usr/bin/glances -w -p 61208 -B 0.0.0.0
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload && sudo systemctl enable --now glances-web.service
# Vérifier : curl http://10.10.0.3:61208
```

### 3.10 NFS mount (relay évaluation + vault en lecture)

```bash
sudo dnf install -y nfs-utils
sudo mkdir -p /data/shared /data/wiki
echo "10.10.0.1:/data/shared /data/shared nfs rw,hard,intr,noatime 0 0" | sudo tee -a /etc/fstab
echo "10.10.0.1:/data/wiki /data/wiki nfs ro,hard,intr,noatime 0 0" | sudo tee -a /etc/fstab
sudo mount -a
```

### 3.11 SSH (MemoryManager — clés root)

```bash
# Autoriser la clé publique du LXC 100 (orchestrateur) pour le monitoring
sudo mkdir -p /root/.ssh && sudo chmod 700 /root/.ssh
echo "ssh-ed25519 AAAA... root@lxc100" | sudo tee -a /root/.ssh/authorized_keys
sudo chmod 600 /root/.ssh/authorized_keys

# Firewall Fedora : ouvrir Ollama + Glances sur VLAN 10
sudo firewall-cmd --permanent --add-rich-rule='rule family=ipv4 source address=10.10.0.0/24 port port=11434 protocol=tcp accept'
sudo firewall-cmd --permanent --add-rich-rule='rule family=ipv4 source address=10.10.0.0/24 port port=61208 protocol=tcp accept'
sudo firewall-cmd --reload
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
ollama pull hf.co/bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF:Q4_K_M@sha256:...
ollama pull hf.co/gpustack/bge-reranker-v2-m3-GGUF:Q4_K_M@sha256:...
```

### Machine 2 — LXC 201 (CPU, fallback)

```bash
ollama pull hf.co/bartowski/Ministral-8B-Instruct-2410-GGUF:Q4_K_M@sha256:...
ollama pull bge-m3@sha256:...
```

### Machine 3 — BC-250 (Vulkan)

```bash
ollama pull hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M@sha256:...  # Générateur (~9 GB)
ollama pull hf.co/Qwen/Qwen3-30B-A3B-GGUF:Q2_K@sha256:...        # Générateur alternatif (~11.3 GB)
ollama pull hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q2_K@sha256:...  # Text-to-SQL
ollama pull hf.co/cjpais/llava-v1.6-vicuna-13b-gguf:Q4_K_M@sha256:...        # Vision
ollama pull hf.co/ibm-granite/granite-4.0-h-tiny-GGUF:Q4_K_M@sha256:...  # Fast-check
```

### Machine 1 — Hôte (CPU)

```bash
ollama pull hf.co/nomic-ai/nomic-embed-text-v2-moe-GGUF:Q8_0@sha256:... # Embedding
ollama pull hf.co/ibm-granite/granite-4.1-8b-instruct-GGUF:Q4_K_M@sha256:...  # Évaluateur (diversification lignée)
```

> ⚠️ Fixer les digests SHA256 dans `.env` pour garantir la reproductibilité.

---

## 6 Vérification du Cluster

```bash
# Depuis n'importe quel nœud du VLAN 10 (10.10.0.0/24) :
curl http://10.10.0.100:8000/api/v1/health     # LXC 100 FastAPI
curl http://10.10.0.101:6333/health            # LXC 101 Qdrant
curl http://10.10.0.105:80                      # LXC 105 OMV Web UI
curl http://10.10.0.200:11434/api/tags         # LXC 200 Ollama GPU
curl http://10.10.0.201:11434/api/tags         # LXC 201 Ollama CPU
curl http://10.10.0.3:11434/api/tags           # M3 BC-250 Ollama Vulkan
curl http://10.10.0.3:61208                     # M3 BC-250 Glances (monitoring)
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
| Glances BC-250 (M3) | `http://10.10.0.3:61208` |
| OMV Backup | `http://10.10.0.105:80` |
| NFS relay | `10.10.0.1:/data/shared` → `/data/shared` |

---

## Allocation mémoire / vCPU (rappel)

### Machine 1 — Control Plane (Dual Xeon E5-2699 v3, 32 GB, 1 TB NVMe)

| LXC | vCPU | RAM | Usage |
|-----|------|-----|-------|
| 100 | 8 | 10 GB | Orchestrator + Wiki Agent |
| 101 | 6 | 8 GB | Vector DB |
| 104 (VM) | 1 | 512 MB | pfSense (reverse proxy + firewall + NAT) |
| **Total** | **15** | **~18.5 GB** | **~13 GB libre pour Proxmox + burst** |



### Machine 2 — Compute & Storage Plane (Xeon E5-2698 v3, 64 GB, 1 TB NVMe, RTX 4000)

| LXC | vCPU | RAM | VRAM GPU | Usage |
|-----|------|-----|----------|-------|
| 105 | 2 | 4 GB | — | **OMV Backup (HDD 2TB passthrough, borg)** |
| 200 | 6 | 8 GB | 8 GB (passthrough) | Judge + Reranker |
| 201 | 4 | 8 GB | — | Avocat + Backup Embedding |
| **Total** | **12** | **20 GB** | **8 GB VRAM** | **cache modèles + cold save OMV (HDD 2TB)** |

### Machine 3 (BC-250, 16 GB GDDR6 unifiée)

Pas de LXC — Ollama Vulkan natif. Mémoire GDDR6 partagée CPU/GPU (max ~12 GB dispo pour IA, le reste pour le système).
Monitoring : **Glances** (`glances -w`, port 61208) — seul nœud sans supervision Proxmox (décision D9).

---

*Document généré le 31/07/2026 — Phase 0 du projet.*
