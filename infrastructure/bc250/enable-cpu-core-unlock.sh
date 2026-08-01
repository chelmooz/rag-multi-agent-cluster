#!/usr/bin/env bash
# Débloque les 2 cores CPU désactivés du BC-250 (6c/12t → 8c/16t).
#
# VOIE PRINCIPALE (décision 02/08/2026) : flash BIOS Forbidden-Darkness —
# https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script
# (core unlock PERSISTANT + carve-out VRAM dynamique 512 MB). Voir
# docs/deployment-guide.md §3.0. CE SCRIPT n'est gardé qu'en FALLBACK.
#
# Patch communautaire par rw-r-r-0644 : https://github.com/rw-r-r-0644/bc250-core-unlock
# Résumé technique : le die (PS5 Oberon) a 8 cores physiques, l'AGESA/PSP en
# masque 2 en usine. Le SMU (queue 3, msg 0x98) accepte une écriture SMN non
# bornée ; ce script cible uniquement le registre du masque de présence des
# cores (smn 0x0115a870, lit 0x77 = 6/8 cores) et y écrit 0xff. Au reboot
# suivant, l'AGESA énumère 8 cores, construit une MADT à 16 entrées, et le
# PSP les libère toutes. Un patch MADT seul ne suffit pas : les cores seraient
# annoncés mais jamais libérés par le PSP (timeout INIT/SIPI).
#
# Gain mesuré par l'auteur (BIOS 3.0, kernel 6.18.40, reproduit 3/3, dont 2
# fois à froid) : 16 threads actifs (bogomips 76690 → 102245), 44°C → 55°C
# sous charge 16 threads, aucune MCE observée, conso idle quasi inchangée
# (72.68 W vs 72.43 W).
#
# STATUT : script de référence, non testé sur le matériel réel de Michel.
set -euo pipefail

echo "=== 0. Pré-requis ==="
cat <<'EOF'
- BIOS 3.0 confirmé par l'auteur ; BIOS 5 (SMU 0.58.7.1) a un dispatch slot
  différent, msg 0x98 probablement identique mais NON TESTÉ sur ce firmware.
- Le patch amdgpu / gouverneur SMU (cyan-skillfish-governor-smu) doit déjà
  être installé, voir setup-vulkan-stack.sh.
- CE PATCH EST VOLATIL : il ne survit pas à une coupure d'alimentation
  complète (cold boot). À refaire après chaque cold boot, pas après un
  simple reboot chaud.
EOF

echo "=== 1. Cloner le repo ==="
echo "  git clone https://github.com/rw-r-r-0644/bc250-core-unlock.git"
echo "  cd bc250-core-unlock"
echo "  chmod +x bc250-unlock-cores.py"

echo "=== 2. Arrêter le gouverneur SMU AVANT de patcher ==="
cat <<'EOF'
Le gouverneur et le script se disputeraient sinon l'accès à la queue SMU.
  sudo systemctl stop cyan-skillfish-governor-smu
EOF

echo "=== 3. Lancer le unlock et reboot ==="
echo "  sudo ./bc250-unlock-cores.py"
echo "  sudo reboot"

echo "=== 4. Vérification post-reboot (OBLIGATOIRE) ==="
cat <<'EOF'
  lscpu | grep -E 'CPU\(s\)|Core\(s\) per socket|Thread\(s\) per core'
  # attendu : 16 CPU(s), 8 cores per socket, 2 threads per core

  sudo dmesg | grep -iE 'smp|lapic' | tail -20
  # attendu : "16 cpus, no timeouts", 16 entrées lapic MADT, apicid 0..15
  # contigus (6/7/14/15 absents avant patch)
EOF

echo "=== 5. Ne PAS faire confiance à 3 boots + un test rapide ==="
cat <<'EOF'
L'auteur ignore pourquoi ces 2 cores sont désactivés en usine (die PS5
Oberon) — l'hypothèse par défaut est un tri qualité/harvest, pas forcément
un défaut. Avant tout usage soutenu :
  sudo dnf install stress-ng   # ou mprime
  stress-ng --cpu 16 --timeout 4h
  sudo dmesg | grep -i mce      # doit rester vide

Un run de l'auteur a démarré sans carte réseau active — la NIC est connue
pour être capricieuse sur ce kernel indépendamment du patch ; à surveiller
mais pas nécessairement causé par ce script.
EOF

echo "=== 6. Reconduire le gouverneur SMU une fois validé ==="
echo "  sudo systemctl start cyan-skillfish-governor-smu"

echo "=== Optionnel — bc250-dfps.py (P-state mémoire/fabric, même mailbox SMU) ==="
cat <<'EOF'
Même auteur, même technique d'accès SMU. Permet de forcer un palier
fclk/uclk/memclk (~22 W d'écart idle entre le palier bas et le palier haut) :
  sudo ./bc250-dfps.py table
  sudo ./bc250-dfps.py set 1
Table repère (0=bas, 3=défaut) :
  idx 0 : fclk 250  uclk 225  memclk 450   3.6 Gbps
  idx 1 : fclk 750  uclk 425  memclk 850   6.8 Gbps
  idx 2 : fclk 1200 uclk 875  memclk 1750 14.0 Gbps (défaut)
Non testé sur le matériel de Michel — à valider séparément du core unlock.
EOF

echo "=== ATTENTION SÉCURITÉ ==="
cat <<'EOF'
Le mailbox SMU (msg 0x98) écrit à n'importe quelle adresse SMN passée en
argument, sans vérification de plage — seule protection : addr != 0.
bc250-unlock-cores.py ne cible QUE 0x0115a870 et vérifie que le masque lu
vaut bien 0x77 avant d'écrire. Ne pas modifier ce script pour cibler une
autre adresse sans une bonne raison documentée : une mauvaise adresse peut
figer ou corrompre la carte.
EOF

echo "=== Terminé — patch volatil, à refaire après chaque cold boot ==="
