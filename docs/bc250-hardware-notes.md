# Notes hardware BC-250 — sources de référence

Sources faisant autorité (à consulter avant toute modification des scripts `infrastructure/bc250/`) :

- **Doc communautaire générale** : https://elektricm.github.io/amd-bc250-docs/ (repo : [elektricM/amd-bc250-docs](https://github.com/elektricM/amd-bc250-docs))
- **Guide spécifique IA/LLM** : https://github.com/akandr/bc250 — Ollama + Vulkan, benchmarks détaillés, tuning mémoire
- **Patch 40 CU unlock** : https://github.com/duggasco/bc250-40cu-unlock

## Faits clés à ne pas perdre

- GPU = GFX1013 "Cyan Skillfish" ("RDNA 1.5" informel). **ROCm ne fonctionne pas** (pas de rocBLAS pour GFX1013). Seul **Vulkan (Mesa/RADV)** fonctionne pour le compute GPU.
- Mémoire : **16 GB GDDR6 unifiée**, partagée CPU+GPU (pas de VRAM dédiée séparée). 512 MB carve-out BIOS pour le framebuffer.
- CU : 40 physiques, **24 actifs en stock** (masqués en usine), 40 après le patch communautaire (gain mesuré : +32% à +61% tok/s en génération selon le modèle).
- Deux réglages kernel obligatoires avant de faire tourner des modèles 14B+ :
  - `ttm.pages_limit=3959290` (~15 GiB) — sinon plafond silencieux ~7.4 GiB et échecs HTTP 500 en cours d'inférence
  - Vérifier la valeur **après reboot**, pas seulement après l'avoir posée (piège `systemd-tmpfiles` documenté)
- Ollama : `OLLAMA_VULKAN=1`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q4_0` (KV cache 4-bit, quasi aucune perte de vitesse, 2x plus de contexte utilisable), `OLLAMA_CONTEXT_LENGTH=65536` comme plafond raisonnable pour de l'interactif.
- Swap NVMe recommandé (~16 Go) : les modèles 11+ Go sur une machine à 16 Go RAM unifiée ont besoin de cette marge.
- Gouverneur GPU obligatoire (`cyan-skillfish-governor-smu`) pour le scaling de fréquence — sans lui, pas de contrôle de clock fiable sur cette puce.
- OS : **Fedora 43** (décision 02/08/2026) — Mesa 25.1+ en mainline, pas de experimental/compilation manuelle. Debian Testing/Sid abandonné. antiX-26 réservé au poste de travail de Michel, pas au BC-250.
- BIOS : **moddé Forbidden-Darkness** (image complète, base P3.00 incluse — flash UEFI direct, aucun flash P3.00 stock préalable). Core unlock → **8c/16t persistant** (2 cores débloqués dès le boot) + carve-out VRAM dynamique 512 MB. Plus besoin du script volatil SMU (rw-r-r-0644), gardé en fallback.

## Ce que ce projet ne couvre pas encore

Le patch 40 CU dépend du kernel exact et doit être reconstruit à chaque mise à jour noyau (out-of-tree). Les scripts fournis ici sont des scripts de référence transcrits depuis la documentation — **non testés sur le matériel réel**, à valider étape par étape.
