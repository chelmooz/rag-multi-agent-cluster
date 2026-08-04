# Runbook — Incidents Cluster CTOS

Guide opérationnel réaction incidents pour cluster RAG multi-agents.
Chaque scénario = symptôme clé + commande de diagnostic + action correctrice.

| Scénario | Machine | Symptôme | Commande 1 |
|---|---|---|---|
| BC250 ne boote plus | M3 | Kernel panic / freeze post-upgrade | `ssh root@m3 journalctl -b -1 -p err` |
| RTX 4000 OOM | M2 | Juge/Avocat tué par OOM killer | `ssh root@m2 dmesg \| tail -20` |
| NFS stale handle | M1/M2 | Relay évaluation bloqué | `showmount -e m1` depuis M2 |
| Qdrant corruption | M1 | `/healthz` 503 ou erreur index | `curl -s localhost:6333/healthz` |
| OMV HDD failure | M2 | Cold save borg erreurs écriture | `ssh root@omv smartctl -a /dev/disk/by-id/...` |

---

## 1. BC250 ne boote plus
**Symptôme** : M3 (BC250) inaccessible après upgrade kernel. Core-unlock volatile (service systemd), cu-unlock perdu.

**Diagnostic** :
```bash
# Console IPMI Proxmox → VM M3 → logs
journalctl -b -1 -p err        # erreurs boot précédent
dmesg | grep -i "cu\|gpu\|drm" # unlock CUs perdu
```

**Action** :
```bash
# Re-déclencher le service systemd de core-unlock
systemctl restart bc250-core-unlock.service
# Vérifier CU count
cat /sys/class/drm/card0/device/gpu_num_cu  # attendu: 40
```

## 2. RTX 4000 OOM
**Symptôme** : LXC 200 (GPU passthrough) tue processes Juge/Avocat pour RAM saturée.

**Diagnostic** :
```bash
ssh root@m2 nvidia-smi          # VRAM utilisée
ssh root@m2 dmesg | grep -i "oom\|killed" | tail -5
curl -s localhost:11434/api/ps  # modèles chargés
```

**Action** :
```bash
# Redémarrer LXC 200 (GPU passthrough)
pct restart 200
# Vérifier recovery
ssh root@m2 nvidia-smi && curl -s localhost:11434/api/tags
```

## 3. NFS stale handle
**Symptôme** : `relay.json` inaccessible, erreur "Stale file handle" sur M2.

**Diagnostic** :
```bash
ssh root@m2 ls -la /data/shared          # stale ?
ssh root@m1 exportfs -v                  # export NFS actif
ping -c1 10.10.0.1                       # connectivité M2→M1
```

**Action** :
```bash
# Sur M2 : remount NFS
mount -o remount,nfsvers=4 10.10.0.1:/data/shared /data/shared
# Si persiste : restart NFS client
systemctl restart nfs-client.target
```

## 4. Qdrant corruption
**Symptôme** : `/healthz` de Qdrant renvoie 503 (Qdrant dégradé).

**Diagnostic** :
```bash
curl -s localhost:6333/healthz         # Qdrant health
curl -s localhost:6333/collections     # liste collections
tail -50 /var/log/qdrant/qdrant.log    # crash récent ?
```

**Action** :
- Si corruption index → restore depuis snapshot OMV (cold save).
```bash
# Sur LXC 101 (Qdrant)
QDRANT_SNAPSHOT=$(curl -s localhost:6333/snapshots)  # lister
# Restore via API : POST /collections/{col}/snapshots/{snap}/restore
```

## 5. OMV HDD failure
**Symptôme** : Borg errors en écriture, `smoke_test` backup échoue.

**Diagnostic** :
```bash
ssh root@omv smartctl -a /dev/disk/by-id/usb-... | grep "Health\|Reallocated_Sector"
ssh root@omv df -h /srv/backup
ssh root@omv dmesg | grep -i "I/O error"
```

**Action** :
- Remplacement HDD physique (hot-swap si possible).
- Recréer borg repo :
```bash
borg init --encryption=repokey /srv/backup/borg-repo
# Récupérer clef depuis sops Vault (0.16 — à configurer)
```

---

## Contacts urgence
| Role | Canaux |
|---|---|
| Infra Proxmox | `admin@lab.local` + IPMI `172.16.0.x` |
| BC250 GPU | Voir [docs/bc250-hardware-notes.md](bc250-hardware-notes.md) |
| pfSense firewall | `10.10.0.254` (admin web + SSH) |

*Runbook versionné avec le repo — PR pour toute modification.*
