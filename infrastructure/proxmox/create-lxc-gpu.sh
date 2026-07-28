#!/usr/bin/env bash
# Crée les LXC de la Machine 2 (GPU Worker) sur Proxmox VE 8.x :
#   200 Inference GPU (passthrough RTX 4000), 201 Workers Agents
# STATUT : stub non testé — voir ROADMAP.md.
set -euo pipefail

echo "TODO: pct create 200 ... (passthrough GPU RTX 4000, container privilégié)"
echo "TODO: pct create 201 ... (Workers Agents)"
echo "TODO: documenter la config du passthrough (vfio / mount des devices nvidia)"

exit 1
