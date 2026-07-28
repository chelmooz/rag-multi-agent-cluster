#!/usr/bin/env bash
# Met en place la stack de compute réelle du BC-250 : Vulkan (RADV/Mesa), PAS ROCm.
#
# Correction importante par rapport à la v1 de ce projet : ROCm ne fonctionne pas
# sur cette puce. Le GFX1013 ("Cyan Skillfish") est listé par LLVM mais AMD ne
# ship pas les bibliothèques rocBLAS/Tensile pour GFX1013 (rocblas_abort() au
# runtime). Le seul chemin de compute GPU qui fonctionne est Vulkan via
# Mesa/RADV. Source : https://github.com/akandr/bc250 (§2 Driver & Compute Stack)
# et https://elektricm.github.io/amd-bc250-docs/linux/debian/
#
# STATUT : script de référence basé sur la doc communautaire, non testé sur le
# matériel réel de Michel — à valider étape par étape, pas en un seul run aveugle.
set -euo pipefail

echo "=== Prérequis / rappels avant exécution ==="
cat <<'EOF'
- OS : Debian Testing/Sid requis (Debian Stable est trop ancien pour Mesa 25.1+).
  TODO Michel : trancher Debian Testing/Sid vs antiX-26 (déjà en place selon
  tes notes) — vérifier que la version Mesa disponible sur antiX satisfait le
  minimum 25.1.3 avant de partir sur ce script tel quel.
- Kernel : viser 6.18.18 LTS ou 6.19.x. ÉVITER 6.15.0-6.15.6 et 6.17.8-6.17.10
  (bugs GPU driver connus).
- BIOS : P3.00+ avec VRAM dynamique 512MB (voir bios/flashing dans la doc BC-250).
- Paramètre de boot nomodeset nécessaire à l'installation, à retirer une fois
  Mesa installé.
EOF

echo "=== 1. Vérification noyau ==="
uname -r
echo "TODO: comparer avec la liste des noyaux cassés ci-dessus avant de continuer"

echo "=== 2. Dépôt experimental (Mesa 25.1+ n'est pas dans testing/sid standard) ==="
if ! grep -q "^deb .*experimental" /etc/apt/sources.list 2>/dev/null; then
  echo "deb http://deb.debian.org/debian experimental main contrib non-free non-free-firmware" \
    | sudo tee -a /etc/apt/sources.list
fi

sudo tee /etc/apt/preferences.d/experimental >/dev/null <<'EOF'
Package: *
Pin: release a=experimental
Pin-Priority: 1

Package: mesa-vulkan-drivers libgl1-mesa-dri
Pin: release a=experimental
Pin-Priority: 500
EOF

sudo apt update

echo "=== 3. Installation Mesa 25.1+ depuis experimental ==="
sudo apt install -t experimental mesa-vulkan-drivers libgl1-mesa-dri

echo "=== 4. Vérification ==="
glxinfo | grep "OpenGL version" || echo "glxinfo absent : sudo apt install mesa-utils"
vulkaninfo --summary | grep -i "GFX1013\|deviceName" || true
echo "Attendu : Mesa 25.1.X+ et un GPU RADV GFX1013"

echo "=== 5. Paramètres kernel (grub) ==="
echo "TODO: ajouter amdgpu.sg_display=0 à GRUB_CMDLINE_LINUX_DEFAULT dans /etc/default/grub, puis sudo update-grub"

echo "=== 6. Gouverneur GPU (obligatoire pour le scaling de fréquence) ==="
echo "TODO: installer cyan-skillfish-governor-smu depuis"
echo "  https://github.com/Magnap/cyan-skillfish-governor/releases (ou filippor/cyan-skillfish-governor)"
echo "  wget <url .deb> && sudo dpkg -i cyan-skillfish-governor-smu_amd64.deb"
echo "  sudo systemctl enable --now cyan-skillfish-governor-smu.service"

echo "=== 7. TTM pages_limit — CRITIQUE pour faire tourner des modèles 14B+ ==="
cat <<'EOF'
Sans ce réglage, les modèles 14B+ chargent mais échouent en HTTP 500 pendant
l'inférence (le KV cache ne peut pas s'étendre au-delà du plafond TTM,
~7.4 GiB par défaut au lieu des 16 GiB physiques disponibles).
EOF
echo "TODO (à exécuter et VÉRIFIER, cf. piège documenté ci-dessous) :"
cat <<'EOF'
  echo 4194304 | sudo tee /sys/module/ttm/parameters/pages_limit
  echo 4194304 | sudo tee /sys/module/ttm/parameters/page_pool_size
  echo "options ttm pages_limit=4194304 page_pool_size=4194304" | sudo tee /etc/modprobe.d/ttm-gpu-memory.conf
  # ATTENTION : systemd-tmpfiles s'exécute APRÈS le boot et peut écraser cette
  # valeur si un fichier tmpfiles.d existant définit un autre chiffre.
  # Vérifier après reboot : cat /sys/module/ttm/parameters/pages_limit
  # DOIT afficher 4194304 (16 GiB), pas 3145728 (12 GiB, plafond silencieux
  # documenté sur du matériel similaire).
EOF

echo "=== 8. Swap NVMe (16 GB RAM unifiée, modèles 11+ Go) ==="
echo "TODO: prévoir un swapfile ~16 Go sur NVMe, voir README pour la commande complète"

echo "=== Terminé — relire chaque TODO avant de considérer le nœud prêt ==="
