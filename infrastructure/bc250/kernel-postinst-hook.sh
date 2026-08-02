#!/bin/sh
# Hook apt kernel-postinst : rebuild automatique du patch 40 CU après upgrade kernel.
# Copier dans /etc/kernel/postinst.d/bc250-rebuild-40cu
# Compatible Debian (hook initramfs-tools) — ne pas utiliser sur Fedora (dracut).
set -e

CU_DIR="/usr/src/bc250-40cu-unlock"
CU_SCRIPT="$CU_DIR/scripts/bc250-enable-40cu.sh"

if [ ! -d "$CU_DIR" ]; then
    echo "bc250-40cu-unlock: répertoire absent ($CU_DIR) — skip rebuild"
    exit 0
fi

echo "=== bc250-40cu-unlock: rebuild pour kernel $1 ==="

cd "$CU_DIR"
./scripts/bc250-enable-40cu.sh build || {
    echo "ÉCHEC build patch 40 CU pour kernel $1"
    exit 1
}

echo "Patch 40 CU rebuild OK pour kernel $1"
echo "Remarque : le module est déjà chargé dans le nouveau kernel —"
echo "          un redémarrage est nécessaire pour activer les 40 CU."
echo "          Exécuter ./scripts/bc250-enable-40cu.sh enable si ce n'est pas un reboot."