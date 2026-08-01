# SSH Keys Deployment (MemoryManager)

## Contexte

LXC 100 (orchestrateur M1) doit accéder SSH (passwordless) à M2 et M3 pour
le monitoring MemoryManager :

- **M2** : `nvidia-smi` (VRAM RTX 4000)
- **M3** : `free -b`, `/proc/loadavg` (BC-250 unified GDDR6 + règle d'or CPU)

Utilisateur : `root` partout (confirmé 01/08/2026) — nvidia-smi nécessite root.

## Déploiement des clés (une fois)

### 1. Générer la clé sur LXC 100 (orchestrateur)

```bash
# Dans LXC 100
ssh-keygen -t ed25519 -N "" -f /root/.ssh/id_ed25519
cat /root/.ssh/id_ed25519.pub
# → copier la clé publique
```

> ⚠️ Si vous utilisez une clé RSA (`/root/.ssh/id_rsa`), mettre à jour
> `M2_SSH_KEY_PATH` / `M3_SSH_KEY_PATH` dans `.env` en conséquence.
> Le default settings pointe sur `/root/.ssh/id_rsa`.

### 2. Autoriser la clé sur M2 et M3

```bash
# Sur M2 (host ou LXC — où nvidia-smi est visible)
mkdir -p /root/.ssh && chmod 700 /root/.ssh
echo "ssh-ed25519 AAAA... root@lxc100" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys

# Idem sur M3 (baremetal BC-250)
```

### 3. Tester depuis LXC 100

```bash
ssh -o StrictHostKeyChecking=no root@10.10.0.2 "nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits"
ssh -o StrictHostKeyChecking=no root@10.10.0.3 "free -b | grep -E '^Mem'"
ssh -o StrictHostKeyChecking=no root@10.10.0.3 "cat /proc/loadavg"
```

## Vérification API

```bash
# Snapshot mémoire du cluster (nécessite services initialisés)
curl -s http://localhost:8000/api/v1/health/memory
```

## Alternatives (futures)

- **Proxmox cloud-init** : inclure la clé publique dans userData à chaque boot
- **Ansible** : playbook de distribution des clés
- **Certificats SSH court-lived** (Phase 7, secrets management)
