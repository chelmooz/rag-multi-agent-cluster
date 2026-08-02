#!/usr/bin/env bash
# Met en place la stack de compute réelle du BC-250 : Vulkan (RADV/Mesa), PAS ROCm.
#
# Correction importante par rapport à la v1 de ce projet : ROCm ne fonctionne pas
# sur cette puce. Le GFX1013 ("Cyan Skillfish") est listé par LLVM mais AMD ne
# ship pas les bibliothèques rocBLAS/Tensile pour GFX1013 (rocblas_abort() au
# runtime). Le seul chemin de compute GPU qui fonctionne est Vulkan via
# Mesa/RADV. Source : https://github.com/akandr/bc250 (§2 Driver & Compute Stack)
# et https://elektricm.github.io/amd-bc250-docs/
#
# OS : Debian 12 (bookworm) stable (décision 03/08/2026) — Mesa 25.1+ via
# bookworm-backports, pas de compilation manuelle. Voir docs/deployment-guide.md §3
# (Machine 3) pour l'installation complète, dont le BIOS Forbidden-Darkness.
#
# STATUT : script de référence basé sur la doc communautaire, non testé sur le
# matériel réel de Michel — à valider étape par étape, pas en un seul run aveugle.
set -euo pipefail

echo "=== 0. Prérequis / rappels avant exécution ==="
cat <<'EOF'
- OS : Debian 12 (bookworm) stable (Mesa 25.1+ via bookworm-backports).
- Kernel : viser 6.18.18 LTS. ÉVITER 6.15.0-6.15.6 et 6.17.8-6.17.10
  (bugs GPU driver connus). Pinner via apt-mark hold (§3.2 du deployment-guide).
- BIOS : moddé Forbidden-Darkness (image complète, base P3.00 incluse —
  VRAM dynamique 512 MB persistant, core unlock CPU via service systemd §3.0bis).
  Voir docs/deployment-guide.md §3.0.
- Paramètre de boot nomodeset nécessaire à l'installation, à retirer une fois
  Mesa installé.
EOF

echo "=== 1. Vérification noyau ==="
uname -r
echo "TODO: comparer avec la liste des noyaux cassés ci-dessus avant de continuer"

echo "=== 2. Stack de base + Mesa 25.1+ (backports Debian 12) ==="
sudo apt update
sudo apt install -t bookworm-backports -y mesa-vulkan-drivers vulkan-tools mesa-utils
sudo apt install -y glmark2 linux-headers-\$(uname -r) build-essential gcc make git curl

echo "=== 3. Vérification ==="
glxinfo | grep "OpenGL version" || echo "glxinfo absent : sudo dnf install mesa-utils"
vulkaninfo --summary | grep -i "GFX1013\|deviceName" || true
echo "Attendu : Mesa 25.1.X+ et un GPU RADV GFX1013"

echo "=== 4. Paramètres kernel (grub) — triplet obligatoire ==="
echo "TODO: dans /etc/default/grub, GRUB_CMDLINE_LINUX_DEFAULT :"
echo "  amdgpu.gttsize=14750 ttm.pages_limit=3959290 ttm.page_pool_size=3959290 amdgpu.sg_display=0"
echo "  puis : sudo update-grub"
echo "  NE JAMAIS ajouter amd_iommu=on (bugs connus sur BC-250)."

echo "=== 5. Gouverneur GPU (obligatoire pour le scaling de fréquence) ==="
echo "Debian : pas de COPR. Compiler depuis source ou utiliser amdgpu-smi :"
cat <<'EOF'
  # Option A (recommandé) : compiler cyan-skillfish-governor-smu
  git clone https://github.com/cyan-skillfish-governor-smu/cyan-skillfish-governor-smu.git
  cd cyan-skillfish-governor-smu
  make
  sudo make install
  # Config safe-points : /etc/cyan-skillfish-governor-smu/config.toml
  #   1500 MHz / 900 mV pour un usage soutenu (cf. settings BC250_GOV_*)
  sudo systemctl enable --now cyan-skillfish-governor-smu.service

  # Option B (léger) : amdgpu-smi
  sudo apt install -y rocm-smi-lib
  # sudo amdgpu-smi --setperflevel=high --setfan=75
EOF

echo "=== 6. TTM pages_limit — CRITIQUE pour faire tourner des modèles 14B+ ==="
cat <<'EOF'
Sans ce réglage, les modèles 14B+ chargent mais échouent en HTTP 500 pendant
l'inférence (le KV cache ne peut pas s'étendre au-delà du plafond TTM,
~7.4 GiB par défaut au lieu des 16 GiB physiques disponibles).
EOF
echo "TODO (à exécuter et VÉRIFIER, cf. piège documenté ci-dessous) :"
cat <<'EOF'
  sudo sh -c 'echo options ttm pages_limit=3959290 page_pool_size=3959290 > /etc/modprobe.d/ttm-gpu-memory.conf'
  # ATTENTION : systemd-tmpfiles s'exécute APRÈS le boot et peut écraser cette
  # valeur si un fichier tmpfiles.d existant définit un autre chiffre. Le triplet
  # GRUB (§4) est la sécurité doublon. Vérifier après reboot :
  cat /sys/module/ttm/parameters/pages_limit
  # DOIT afficher 3959290 (~15 GiB).
EOF

echo "=== 7. Swap NVMe (16 GB RAM unifiée, modèles 11+ Go) ==="
echo "TODO: prévoir un swapfile ~16 Go sur NVMe, voir README pour la commande complète"

echo "=== Terminé — relire chaque TODO avant de considérer le nœud prêt ==="
