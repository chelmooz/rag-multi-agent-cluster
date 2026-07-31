#!/usr/bin/env bash
# Machine 1 (Master) — Dual Xeon E5-2699 v3 (36c/72t), 32 GB ECC
# Crée les LXC : 100 Orchestrator, 101 Vector DB, 102 API Gateway,
#                103 Monitoring, 104 pfSense (VM), 105 OMV Backup
set -euo pipefail

PASSWORD="${PASSWORD:-jarvis}"
TEMPLATE="debian-12-standard_12.7-1_amd64.tar.zst"
BRIDGE="vmbr10"
GATEWAY="10.10.0.1"
DNS="10.10.0.1"

# Couleurs
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERR]${NC} $*"; }

# === 0. Vérifications
[[ $EUID -eq 0 ]] || { err "Ce script doit être exécuté en root sur Proxmox."; exit 1; }
command -v pct &>/dev/null || { err "pct introuvable — êtes-vous sur un nœud Proxmox ?"; exit 1; }
pveam available --refresh &>/dev/null || true

# === 1. Template
info "Template Debian 12"
if ! pveam list local | grep -q "$TEMPLATE"; then
  pveam download local "$TEMPLATE"
fi
TEMPLATE_PATH="local:vztmpl/$TEMPLATE"

# ============================================================
# LXC 100 — Orchestrator + Wiki Agent (Docker)
# vCPU: 8  RAM: 10 GB  Disque: 50 GB  IP: 10.10.0.100/24
# Services: nginx, fastapi-api, langgraph-orchestrator,
#           wiki-agent, redis, postgres
# ============================================================
info "LXC 100 — Orchestrator + Wiki Agent"
if pct status 100 &>/dev/null; then
  warn "LXC 100 existe déjà, création ignorée."
else
  pct create 100 "$TEMPLATE_PATH" \
    --hostname jarvis-master \
    --cores 8 --memory 10240 --swap 2048 \
    --rootfs local:50 \
    --net0 name=eth0,bridge=$BRIDGE,firewall=1,ip=10.10.0.100/24,gw=$GATEWAY,type=veth \
    --unprivileged 1 --features nesting=1,keyctl=1,fuse=1 \
    --ostype debian \
    --password "$PASSWORD" \
    --storage local
  info "LXC 100 créé."
fi

# ============================================================
# LXC 101 — Vector DB (Docker : Qdrant + PostgreSQL + Redis)
# vCPU: 6  RAM: 8 GB  Disque: 80 GB  IP: 10.10.0.101/24
# ============================================================
info "LXC 101 — Vector DB"
if pct status 101 &>/dev/null; then
  warn "LXC 101 existe déjà."
else
  pct create 101 "$TEMPLATE_PATH" \
    --hostname jarvis-vectordb \
    --cores 6 --memory 8192 --swap 2048 \
    --rootfs local:80 \
    --net0 name=eth0,bridge=$BRIDGE,firewall=1,ip=10.10.0.101/24,gw=$GATEWAY,type=veth \
    --unprivileged 1 --features nesting=1 \
    --ostype debian \
    --password "$PASSWORD" \
    --storage local
  info "LXC 101 créé."
fi

# ============================================================
# LXC 102 — API Gateway (nginx seul)
# vCPU: 1  RAM: 512 MB  Disque: 8 GB  IP: 10.10.0.102/24
# ============================================================
info "LXC 102 — API Gateway"
if pct status 102 &>/dev/null; then
  warn "LXC 102 existe déjà."
else
  pct create 102 "$TEMPLATE_PATH" \
    --hostname jarvis-gateway \
    --cores 1 --memory 512 --swap 512 \
    --rootfs local:8 \
    --net0 name=eth0,bridge=$BRIDGE,firewall=1,ip=10.10.0.102/24,gw=$GATEWAY,type=veth \
    --unprivileged 1 \
    --ostype debian \
    --password "$PASSWORD" \
    --storage local
  info "LXC 102 créé."
fi

# ============================================================
# LXC 103 — Monitoring (Prometheus + Grafana + Loki)
# vCPU: 4  RAM: 4 GB  Disque: 50 GB  IP: 10.10.0.103/24
# ============================================================
info "LXC 103 — Monitoring"
if pct status 103 &>/dev/null; then
  warn "LXC 103 existe déjà."
else
  pct create 103 "$TEMPLATE_PATH" \
    --hostname jarvis-monitoring \
    --cores 4 --memory 4096 --swap 2048 \
    --rootfs local:50 \
    --net0 name=eth0,bridge=$BRIDGE,firewall=1,ip=10.10.0.103/24,gw=$GATEWAY,type=veth \
    --unprivileged 1 --features nesting=1 \
    --ostype debian \
    --password "$PASSWORD" \
    --storage local
  info "LXC 103 créé."
fi

# ============================================================
# VM 104 — pfSense (optionnel, non LXC)
# vCPU: 1  RAM: 512 MB  IP: 10.10.0.104/24 (WAN: DHCP)
# ============================================================
info "VM 104 — pfSense (optionnel, créer manuellement via WebUI)"
warn "pfSense nécessite une VM, pas un LXC (FreeBSD)."
warn "  ISO: pfSense-CE-2.7.2-RELEASE-amd64.iso"
warn "  Command: qm create 104 --name jarvis-pfsense --cores 1 --memory 512"
warn "    --net0 virtio,bridge=$BRIDGE --net1 virtio,bridge=vmbr1"
warn "    --cdrom local:iso/pfSense-CE-2.7.2-RELEASE-amd64.iso --ostype other"

# ============================================================
# LXC 105 — OMV Backup (500 Go dédiés)
# vCPU: 2  RAM: 2 GB  Disque: 8 + 500 Go  IP: 10.10.0.105/24
# ============================================================
info "LXC 105 — OMV Backup"
if pct status 105 &>/dev/null; then
  warn "LXC 105 existe déjà."
else
  # Créer le disque 500 Go si pas existant
  if ! pvesm list local | grep -q "vm-105-disk-1"; then
    pvesm alloc local 105 vm-105-disk-1 500G
  fi
  pct create 105 "$TEMPLATE_PATH" \
    --hostname jarvis-omv \
    --cores 2 --memory 2048 --swap 1024 \
    --rootfs local:8 \
    --mp0 local:500,mp=/srv/backup \
    --net0 name=eth0,bridge=$BRIDGE,firewall=1,ip=10.10.0.105/24,gw=$GATEWAY,type=veth \
    --unprivileged 1 \
    --ostype debian \
    --password "$PASSWORD" \
    --storage local
  info "LXC 105 créé."
fi

# ============================================================
# Résumé
# ============================================================
echo -e "\n${GREEN}======= CRÉATION TERMINÉE =======${NC}"
echo -e "LXC 100  ${YELLOW}10.10.0.100${NC}  Orchestrator (8 vCPU, 10 GB RAM, Docker)"
echo -e "LXC 101  ${YELLOW}10.10.0.101${NC}  Vector DB     (6 vCPU,  8 GB RAM, Docker)"
echo -e "LXC 102  ${YELLOW}10.10.0.102${NC}  API Gateway   (1 vCPU,512 MB RAM, nginx)"
echo -e "LXC 103  ${YELLOW}10.10.0.103${NC}  Monitoring    (4 vCPU,  4 GB RAM, Docker)"
echo -e "VM  104  ${YELLOW}10.10.0.104${NC}  pfSense       (optionnel — VM seulement)"
echo -e "LXC 105  ${YELLOW}10.10.0.105${NC}  OMV Backup    (2 vCPU,  2 GB RAM, +500 Go)"
echo -e "${GREEN}==================================${NC}"
echo ""
echo "Prochaine étape : lancer les scripts de post-install dans chaque LXC :"
echo "  pct enter 100  # puis installer Docker, lancer docker-compose.orchestrator.yml"
echo "  pct enter 101  # Docker + docker-compose.vector-db.yml"
echo "  pct enter 102  # nginx"
echo "  pct enter 103  # Prometheus + Grafana + Loki"
echo "  pct enter 105  # OMV"
