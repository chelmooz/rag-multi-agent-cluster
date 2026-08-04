#!/usr/bin/env bash
# Machine 2 (GPU Worker + Services) — Xeon E5-2698 v3 (16c/32t), 64 GB ECC, 1 TB NVMe + HDD 2TB, RTX 4000
# Crée le LXC : 105 OMV Backup (HDD 2TB passthrough, borg repo)
# À exécuter sur l'hôte Proxmox M2 APRÈS create-lxc-gpu.sh (même nœud).
set -euo pipefail

TEMPLATE="debian-12-standard_12.7-1_amd64.tar.zst"
BRIDGE="vmbr10"
GATEWAY="10.10.0.1"
DNS="10.10.0.1"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERR]${NC} $*"; }

# Pas de mot de passe root faible par défaut (ancien défaut "ctos"/"root" prévisible
# et présent en clair dans un repo public) : PASSWORD doit être positionnée explicitement.
[[ -n "${PASSWORD:-}" ]] || { err "Variable PASSWORD non définie. Exécuter : PASSWORD='<mot-de-passe-fort>' $0"; exit 1; }

# === 0. Vérifications
[[ $EUID -eq 0 ]] || { err "Root requis."; exit 1; }
command -v pct &>/dev/null || { err "pct introuvable."; exit 1; }

# === 0.1 Template
if ! pveam list local | grep -q "$TEMPLATE"; then
  pveam download local "$TEMPLATE"
fi
TEMPLATE_PATH="local:vztmpl/$TEMPLATE"

# === 0.2 Détection HDD 2TB de backup
# Priorité : variable HDD_DEV, sinon premier disque sata/usb non racine de ~2TB
if [[ -z "${HDD_DEV:-}" ]]; then
  HDD_DEV=$(lsblk -dno NAME,SIZE,TYPE | awk '$3=="disk" && $2 ~ /^1\.[5-9]T|^2\.[0-9]T/ {print $1; exit}' | sed 's|^|/dev/|' || true)
fi
if [[ -z "$HDD_DEV" ]]; then
  warn "Aucun HDD 2TB détecté automatiquement."
  warn "Passer l'argument explicite : HDD_DEV=/dev/sdb bash create-lxc-omv.sh"
  warn "Ou monter le passthrough après création : pct set 105 -mp0 /dev/disk/by-id/<HDD-ID>,mp=/srv/backup"
fi

# ============================================================
# LXC 105 — OMV Backup (HDD 2TB passthrough)
# vCPU: 2  RAM: 4 GB  Disque: 20 GB  IP: 10.10.0.105/24
# Services: OMV (Docker), borg repo sur /srv/backup (HDD passthrough)
# ============================================================
info "LXC 105 — OMV Backup"
if pct status 105 &>/dev/null; then
  warn "LXC 105 existe déjà."
else
  pct create 105 "$TEMPLATE_PATH" \
    --hostname rag-omv \
    --cores 2 --memory 4096 --swap 2048 \
    --rootfs local:20 \
    --net0 name=eth0,bridge=$BRIDGE,firewall=1,ip=10.10.0.105/24,gw=$GATEWAY,type=veth \
    --unprivileged 1 --features nesting=1 \
    --ostype debian \
    --password "$PASSWORD" \
    --storage local
  info "LXC 105 créé."
fi

# === Passthrough HDD 2TB (si détecté) ===
if [[ -n "$HDD_DEV" ]] && [[ -b "$HDD_DEV" ]]; then
  info "Passthrough HDD : $HDD_DEV → /srv/backup"
  pct set 105 -mp0 "$HDD_DEV",mp=/srv/backup
else
  warn "Passthrough HDD SKIPPÉ (HDD_DEV non renseigné ou invalide)."
  warn "  Après-coup : pct set 105 -mp0 /dev/disk/by-id/<HDD-ID>,mp=/srv/backup"
fi

# ============================================================
# Résumé
# ============================================================
echo -e "\n${GREEN}======= CRÉATION TERMINÉE =======${NC}"
echo -e "LXC 105  ${YELLOW}10.10.0.105${NC}  OMV Backup  (2 vCPU, 4 GB, Docker + borg)"
if [[ -n "$HDD_DEV" ]]; then
  echo -e "         ${YELLOW}$HDD_DEV${NC} → /srv/backup (passthrough)"
fi
echo -e "${GREEN}==================================${NC}"
echo ""
echo "Post-installation obligatoire :"
echo "  pct enter 105  # puis suivre deployment-guide.md §2.5"
echo "    (Docker + OMV container + borg repo + clé SSH OMV→M1/M3)"
