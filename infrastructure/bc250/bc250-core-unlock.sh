#!/usr/bin/env bash
# Wrapper systemd pour le core-unlock CPU du BC-250 (6c/12t -> 8c/16t).
# Le patch SMU (msg 0x98) est volatil : ne survit pas au cold boot.
# Ce script est appelé par setup-core-unlock.service à chaque démarrage.
set -euo pipefail

REPO_DIR="/usr/src/bc250-core-unlock"
SCRIPT="$REPO_DIR/bc250-unlock-cores.py"

echo "=== BC-250 CPU Core Unlock (cold boot) ==="

# 1. Arrêter le gouverneur SMU s'il tourne (conflit d'accès queue SMU)
if systemctl is-active --quiet cyan-skillfish-governor-smu.service 2>/dev/null; then
    echo "Arrêt temporaire du gouverneur SMU..."
    systemctl stop cyan-skillfish-governor-smu.service
    _GOV_STOPPED=1
else
    _GOV_STOPPED=0
fi

# 2. Cloner si pas déjà présent
if [ ! -d "$REPO_DIR" ]; then
    echo "Clonage du repo bc250-core-unlock..."
    git clone https://github.com/rw-r-r-0644/bc250-core-unlock.git "$REPO_DIR"
    chmod +x "$SCRIPT"
fi

# 3. Vérifier le masque actuel (0x77 = 6/8 cores)
CURRENT=$(python3 -c "
import smbus, struct
bus = smbus.SMBus(3)  # queue SMU
bus.write_i2c_block_data(0x38, 0, [0x70, 0xa8, 0x15, 0x01])  # addr SMN 0x0115a870
data = bus.read_i2c_block_data(0x38, 0, 4)
mask = struct.unpack('<I', bytes(data))[0]
print(hex(mask))
" 2>/dev/null || echo "0x77")

echo "Masque CPU actuel : $CURRENT"

if [ "$CURRENT" = "0xff" ]; then
    echo "Core unlock déjà actif (0xff) — rien à faire."
    EXIT_CODE=0
else
    echo "Application du patch SMU msg 0x98..."
    python3 "$SCRIPT" || {
        echo "ÉCHEC du core-unlock — consulter dmesg pour diagnostic"
        EXIT_CODE=1
    }
    EXIT_CODE=0
fi

# 4. Redémarrer le gouverneur SMU
if [ "$_GOV_STOPPED" = "1" ]; then
    echo "Redémarrage du gouverneur SMU..."
    systemctl start cyan-skillfish-governor-smu.service
fi

# 5. Vérification
if [ "$EXIT_CODE" = "0" ]; then
    CPU_COUNT=$(lscpu | grep -E '^CPU\(s\):' | awk '{print $2}')
    if [ "$CPU_COUNT" = "16" ]; then
        echo "Core unlock OK — 8c/16t actifs"
    else
        echo "ATTENTION : $CPU_COUNT CPU(s) détectés (attendu: 16)"
    fi
fi

exit $EXIT_CODE