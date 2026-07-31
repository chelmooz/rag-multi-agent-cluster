#!/usr/bin/env bash
# Machine 2 (GPU Worker) — Xeon E5-2698 v3 (16c/32t), 64 GB ECC, RTX 4000 (8 GB VRAM)
# Crée les LXC : 200 Inference GPU (passthrough RTX 4000, privilégié),
#                201 Workers Agents (Avocat + Backup Embedding CPU)
set -euo pipefail

PASSWORD="${PASSWORD:-jarvis}"
TEMPLATE="debian-12-standard_12.7-1_amd64.tar.zst"
BRIDGE="vmbr10"
GATEWAY="10.10.0.1"
DNS="10.10.0.1"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERR]${NC} $*"; }

# === 0. Vérifications
[[ $EUID -eq 0 ]] || { err "Root requis."; exit 1; }
command -v pct &>/dev/null || { err "pct introuvable."; exit 1; }

# === 0.1 Template
if ! pveam list local | grep -q "$TEMPLATE"; then
  pveam download local "$TEMPLATE"
fi
TEMPLATE_PATH="local:vztmpl/$TEMPLATE"

# ============================================================
# HÔTE Proxmox — Config IOMMU + VFIO (à faire avant création)
# ============================================================
info "Vérification IOMMU/VFIO sur l'hôte..."
if ! dmesg | grep -q "DMAR: IOMMU enabled"; then
  warn "IOMMU non actif. Ajouter intel_iommu=on à GRUB_CMDLINE_LINUX_DEFAULT"
  warn "  sed -i 's/GRUB_CMDLINE_LINUX_DEFAULT=\".*\"/GRUB_CMDLINE_LINUX_DEFAULT=\"quiet intel_iommu=on iommu=pt\"/' /etc/default/grub"
  warn "  update-grub && reboot"
fi

# Détection GPU NVIDIA
NVIDIA_PCI=$(lspci -nn | grep -i "nvidia" | grep -i "vga\|3d" | head -1 | awk '{print $1}')
if [[ -z "$NVIDIA_PCI" ]]; then
  warn "Aucun GPU NVIDIA détecté. Vérifiez le branchement."
  NVIDIA_PCI="0000:01:00.0"  # fallback
fi
NVIDIA_ID=$(lspci -nn -s "$NVIDIA_PCI" | grep -oP '\[\K[0-9a-f]{4}:[0-9a-f]{4}(?=\])' || echo "10de:1b80")

info "GPU détecté : PCI=$NVIDIA_PCI  ID=$NVIDIA_ID"

# Création du fichier devices.conf pour le LXC 200
mkdir -p /var/lib/lxc/200
cat > /var/lib/lxc/200/devices.conf << 'NVDEV'
lxc.cgroup2.devices.allow: c 195:* rwm
lxc.cgroup2.devices.allow: c 509:* rwm
lxc.cgroup2.devices.allow: c 510:* rwm
lxc.cgroup2.devices.allow: c 511:* rwm
lxc.cgroup2.devices.allow: c 512:* rwm
lxc.mount.entry: /dev/nvidia0 dev/nvidia0 none bind,optional,create=file
lxc.mount.entry: /dev/nvidiactl dev/nvidiactl none bind,optional,create=file
lxc.mount.entry: /dev/nvidia-uvm dev/nvidia-uvm none bind,optional,create=file
lxc.mount.entry: /dev/nvidia-modeset dev/nvidia-modeset none bind,optional,create=file
NVDEV
info "Devices GPU configurés pour LXC 200."

# ============================================================
# LXC 200 — Inference GPU (privilégié, passthrough RTX 4000)
# vCPU: 6  RAM: 8 GB  Disque: 30 GB  IP: 10.10.0.200/24
# Modèles: Judge (qwen3.5:7b) + Reranker (bge-reranker-v2-m3)
# ============================================================
info "LXC 200 — Inference GPU"
if pct status 200 &>/dev/null; then
  warn "LXC 200 existe déjà."
else
  pct create 200 "$TEMPLATE_PATH" \
    --hostname jarvis-gpu-inference \
    --cores 6 --memory 8192 --swap 2048 \
    --rootfs local:30 \
    --net0 name=eth0,bridge=$BRIDGE,firewall=1,ip=10.10.0.200/24,gw=$GATEWAY,type=veth \
    --unprivileged 0 \
    --features nesting=1,mount=cgroup2 \
    --ostype debian \
    --password "$PASSWORD" \
    --storage local
  info "LXC 200 créé."
fi

# Injecter les devices GPU dans la config LXC
echo "" >> /etc/pve/lxc/200.conf
echo "# GPU passthrough NVIDIA RTX 4000" >> /etc/pve/lxc/200.conf
cat /var/lib/lxc/200/devices.conf >> /etc/pve/lxc/200.conf

# ============================================================
# LXC 201 — Workers Agents (Avocat + Backup Embedding CPU)
# vCPU: 4  RAM: 8 GB  Disque: 30 GB  IP: 10.10.0.201/24
# Modèles: Advocate (mistral-small-3.2:7b) + Embedding CPU (bge-m3)
# ============================================================
info "LXC 201 — Workers Agents"
if pct status 201 &>/dev/null; then
  warn "LXC 201 existe déjà."
else
  pct create 201 "$TEMPLATE_PATH" \
    --hostname jarvis-workers \
    --cores 4 --memory 8192 --swap 2048 \
    --rootfs local:30 \
    --net0 name=eth0,bridge=$BRIDGE,firewall=1,ip=10.10.0.201/24,gw=$GATEWAY,type=veth \
    --unprivileged 1 --features nesting=1 \
    --ostype debian \
    --password "$PASSWORD" \
    --storage local
  info "LXC 201 créé."
fi

# ============================================================
# Résumé
# ============================================================
echo -e "\n${GREEN}======= CRÉATION TERMINÉE =======${NC}"
echo -e "LXC 200  ${YELLOW}10.10.0.200${NC}  Inference GPU  (6 vCPU, 8 GB, privilégié, RTX 4000)"
echo -e "LXC 201  ${YELLOW}10.10.0.201${NC}  Workers Agents  (4 vCPU, 8 GB, Ollama CPU)"
echo -e "${GREEN}==================================${NC}"
echo ""
echo "Post-installation obligatoire :"
echo "  Dans LXC 200 : installer NVIDIA drivers + Ollama CUDA"
echo "    pct enter 200 && bash /root/setup-gpu-lxc.sh"
echo "  Dans LXC 201 : installer Ollama CPU + NFS mount"
echo "    pct enter 201 && bash /root/setup-worker-lxc.sh"
echo ""
echo "ATTENTION : la VM hôte doit être rebootée après config IOMMU."
