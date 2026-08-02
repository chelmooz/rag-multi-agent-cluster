#!/usr/bin/env bash
# Active les 16 CU supplémentaires du BC-250 (24 → 40 CU actifs).
#
# Patch communautaire par duggasco : https://github.com/duggasco/bc250-40cu-unlock
# Résumé technique : le die GFX1013 a 40 Compute Units physiques, le firmware
# d'usine en masque 16. Le patch réécrit deux registres GFX10
# (CC_GC_SHADER_ARRAY_CONFIG + SPI_PG_ENABLE_STATIC_WGP_MASK) au chargement du
# module amdgpu. Gain mesuré (A/B contrôlé) : +32% à +61% tok/s en génération
# selon le modèle, +50% en moyenne en prefill. Coût : +30W, +4°C.
#
# OS : Debian 12 (bookworm) stable (décision 03/08/2026) — OS 8 cores déjà
# débloqués par le service systemd bc250-core-unlock.service (cf. §3.0bis du
# deployment-guide), CE script ne concerne que les CU GPU.
#
# STATUT : script de référence, non testé sur le matériel réel de Michel.
set -euo pipefail

echo "=== 0. Pré-requis : le patch amdgpu doit déjà être fonctionnel (Mesa/Vulkan OK) ==="
echo "    Voir setup-vulkan-stack.sh — ne pas lancer ce script avant que Vulkan tourne."

echo "=== 1. Vérifier le harvest pattern du board avant de patcher ==="
cat <<'EOF'
Tous les boards ne se débloquent pas proprement : un pattern contigu (CU 0-5
actifs, 6-9 fusionnés, identique sur les 4 shader arrays) se débloque
généralement en 40 CU stables. Un pattern dispersé peut révéler des CU
réellement défectueux qui passent l'énumération mais échouent sous charge.
EOF

echo "=== 2. Cloner le repo du patch ==="
echo "  git clone https://github.com/duggasco/bc250-40cu-unlock.git"
echo "  cd bc250-40cu-unlock"
echo "  ./scripts/cu_map.sh   # à lancer et lire AVANT de patcher quoi que ce soit"

echo "=== 3. Dépendances de build (Debian 12) ==="
echo "  sudo apt install -y linux-headers-\$(uname -r) build-essential gcc make zstd git"

echo "=== 4. Build + activation (Debian 12) ==="
echo "  sudo ./scripts/bc250-enable-40cu.sh build"
echo "  sudo ./scripts/bc250-enable-40cu.sh enable    # écrit la config modprobe et reboote"

echo "=== 5. Vérification post-reboot (OBLIGATOIRE — ne pas supposer que ça a marché) ==="
cat <<'EOF'
  cat /sys/module/amdgpu/parameters/bc250_cc_write_mode
  # doit afficher 3

  sudo dmesg | grep -E 'bc250-40cu|active_cu_number'
  # doit afficher : active_cu_number 40

  RADV_DEBUG=info vulkaninfo --summary 2>&1 | grep num_cu
  # doit afficher : num_cu = 40

Le check faisant foi est dmesg | grep active_cu_number — c'est documenté comme
plus fiable que le sous-commande "status" du wrapper.
EOF

echo "=== 6. Gouverneur — plafonner à 1500 MHz / 900 mV pour un usage soutenu ==="
cat <<'EOF'
40 CU au 2 GHz par défaut du gouverneur pousse à 96-100°C en refroidissement
stock, avec des pics mesurés jusqu'à 220-230W en charge soutenue. 1500 MHz /
900 mV capture ~1.61x du gain théorique sans risque thermique. Voir
/etc/cyan-skillfish-governor-smu/config.toml (safe-points) dans la doc BC-250.
EOF

echo "=== 7. En cas de CU défectueux détecté (pattern dispersé) ==="
echo "  sudo ./scripts/bc250-cu-health-test.sh start"
echo "  ./scripts/bc250-cu-mask.sh --results /var/lib/bc250-cu-health-test/results.tsv --install"

echo "=== Rollback si besoin ==="
echo "  sudo ./scripts/bc250-enable-40cu.sh disable   # retour au 24 CU stock"
echo "  sudo ./scripts/bc250-enable-40cu.sh restore   # restaure le module amdgpu d'origine"

echo "=== Terminé — chaque apt upgrade du kernel écrase ce patch ==="
echo "Hook automatique installé : cp infrastructure/bc250/kernel-postinst-hook.sh /etc/kernel/postinst.d/bc250-rebuild-40cu"
