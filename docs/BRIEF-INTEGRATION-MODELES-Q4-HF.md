# Brief d'intégration — Modèles Générateur/Juge/Avocat (Q4, sources Hugging Face)

> **Destinataire** : agent codeur (DeepSeek ou équivalent) chargé d'exécuter l'intégration dans `rag-multi-agent-cluster`.
> **Contrainte de méthode** : respecter la stratégie **Mock-first (D10)** déjà actée dans `ROADMAP.md` — cette tâche modifie des *configurations et de la documentation*, pas de pull de modèle réel (le pull reste en Phase C / tâche C4). Ne rien exécuter qui nécessite un accès réseau vers les machines M1/M2/M3.
> **Contrainte de source** : tous les modèles doivent être résolus **exclusivement depuis Hugging Face** (pas la bibliothèque curée `ollama.com/library`), via la syntaxe `hf.co/<repo>:<quant>` supportée nativement par Ollama.

---

## Intro — État de l'art actuel (mi-2026)

Trois tendances structurent aujourd'hui le déploiement de LLM en local, et expliquent les choix de ce brief :

1. **Le MoE (Mixture-of-Experts) est devenu la norme d'efficacité**, pas l'exception. Qwen3 (30B-A3B), Gemma 4 (26B-A4B) et la lignée DeepSeek-V3/R1 partagent la même logique : n'activer qu'une fraction des paramètres par token pour approcher la qualité d'un gros modèle dense au coût d'inférence d'un petit. Le piège classique (déjà rencontré sur ce projet) est d'oublier que **la mémoire se dimensionne sur le total de paramètres chargés, pas sur l'actif**.
2. **La distillation de raisonnement s'est généralisée.** DeepSeek a démontré avec R1 qu'on peut transférer une capacité de raisonnement Chain-of-Thought d'un modèle frontière (671B) vers des backbones denses beaucoup plus petits (Llama 8B/14B/70B, Qwen 1.5B→32B) avec une perte de qualité contenue. C'est ce qui rend un « juge » raisonneur crédible sur 8 Go de VRAM.
3. **GGUF Q4_K_M est le standard de facto du déploiement local**, et **Hugging Face a supplanté les bibliothèques propriétaires comme point de distribution unique** — Ollama, LM Studio et llama.cpp pointent tous directement vers des repos HF (`hf.co/<user>/<repo>:<quant>`) plutôt que vers des miroirs curés, ce qui élimine un intermédiaire et garantit la traçabilité de la source.

Ce projet s'inscrit dans ces trois tendances : générateur MoE sur BC-250 (Vulkan-only, cas d'usage non-NVIDIA typique de 2026), juge par distillation de raisonnement, et résolution 100% Hugging Face.

---

## Table des matières

1. [Rappel des contraintes matérielles](#1-rappel-des-contraintes-matérielles)
2. [Décisions de modèles (résultat final)](#2-décisions-de-modèles-résultat-final)
3. [Chain-of-Thought — justification étape par étape](#3-chain-of-thought--justification-étape-par-étape)
4. [Plan d'exécution — fichiers à modifier](#4-plan-dexécution--fichiers-à-modifier)
5. [Diffs précis](#5-diffs-précis)
6. [Checklist de validation](#6-checklist-de-validation)
7. [Ce que ce brief NE couvre PAS](#7-ce-que-ce-brief-ne-couvre-pas)

---

## 1. Rappel des contraintes matérielles

| Machine | Budget mémoire réel pour l'IA | Contrainte dure |
|---|---|---|
| M2 GPU Worker (RTX 4000) | 8 Go VRAM, **1 seul modèle chargé à la fois** (`relay.json`) | Reranker + Juge + Avocat se partagent ce budget en **séquentiel**, jamais en simultané |
| M3 BC-250 | ~15 Go (16 Go GDDR6 − 512 Mo carve-out BIOS, Debian headless ≈ 0 overhead) | **Vulkan/RADV uniquement** (pas de ROCm sur GFX1013) ; `ttm.pages_limit` obligatoire |

Cible de dimensionnement retenue : **60-65% de charge max par modèle** sur son budget disponible, pour laisser de la marge au KV cache (`OLLAMA_KV_CACHE_TYPE=q4_0`, contexte jusqu'à 65536 tokens côté générateur).

---

## 2. Décisions de modèles (résultat final)

| Rôle | Machine | Modèle | Repo Hugging Face | Fichier quant | Taille réelle vérifiée | Taux de charge |
|---|---|---|---|---|---|---|
| **Générateur** | M3 (BC-250) | Qwen3-14B | `Qwen/Qwen3-14B-GGUF` | `Qwen3-14B-Q4_K_M.gguf` | 9,0 Go | 60% de 15 Go |
| **Juge** | M2 (RTX 4000, hot-swap) | DeepSeek-R1-Distill-Llama-8B | `bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF` | `DeepSeek-R1-Distill-Llama-8B-Q4_K_M.gguf` | 4,92 Go | 61% de 8 Go |
| **Avocat du diable** | M2 (RTX 4000, hot-swap) | Ministral-8B-Instruct-2410 | `bartowski/Ministral-8B-Instruct-2410-GGUF` | `Ministral-8B-Instruct-2410-Q4_K_M.gguf` | 4,91 Go | 61% de 8 Go |

Les 7 autres rôles (embedding, reranker, évaluateur, générateur alternatif, text2sql, vision, fastcheck) ont été résolus Hugging Face via l'extension **C4.2** — cf. [§8](#8-extension-c42--résolution-hf-de-tous-les-modèles-01082026).

---

## 3. Chain-of-Thought — justification étape par étape

**Étape 1 — Corriger un bug de config avant tout.**
`ADVOCATE_MODEL=mistral-small-3.2:7b` dans `.env.example`/`settings.py` référence un modèle qui n'existe pas à cette taille : Mistral Small 3.2 n'existe qu'en **24B** (14,3 Go en Q4_K_M — vérifié sur `bartowski/mistralai_Mistral-Small-3.2-24B-Instruct-2506-GGUF`), ce qui dépasse à lui seul les 8 Go de VRAM de M2. → Ce n'est pas juste un changement de fournisseur, c'est un correctif de valeur par défaut cassée.

**Étape 2 — Choisir la taille Qwen pour le générateur.**
Contrainte : rester sur Qwen (demande explicite), tenir en Q4 sur ~15 Go avec marge KV cache. Qwen3-14B dense en Q4_K_M = 9,0 Go (chiffre officiel `Qwen/Qwen3-14B-GGUF`, pas une estimation tierce) → 6 Go de marge, suffisant pour un contexte long. Pas besoin de descendre en IQ-quant ni de prendre le MoE 30B-A3B pour ce rôle (déjà couvert par `generator_alt_model`, hors scope de ce brief).

**Étape 3 — Choisir la famille pour le juge.**
Demande : DeepSeek R1. Le R1 complet (671B) est hors de portée locale ; la voie réaliste est une **distillation officielle DeepSeek**. Deux backbones existent (Llama et Qwen) — retenir le backbone **Llama** pour préserver une vraie diversité de lignée face au générateur Qwen (l'intérêt du pattern juge/avocat est justement d'avoir des angles morts d'entraînement différents). Taille : le 8B tient à 61% de 8 Go de VRAM avec marge KV cache confortable ; le 14B (≈9 Go) ne laisserait quasiment aucune marge sur cette même carte partagée avec le reranker.

**Étape 4 — Choisir la taille Mistral pour l'avocat.**
Après correction du bug de l'étape 1, le vrai choix Mistral pour 8 Go de VRAM en hot-swap est **Ministral-8B-Instruct-2410** (8,02B paramètres, Q4_K_M = 4,91 Go) — pas Mistral-7B (obsolète, 2023) ni Mistral-Small (24B, trop gros). Bonus : sa taille est quasiment identique à celle du juge (4,91 vs 4,92 Go), ce qui symétrise les temps de chargement du hot-swap `relay.json`.

**Étape 5 — Vérifier la cohérence globale.**
Trois familles distinctes (Qwen / DeepSeek-Llama / Mistral) sur trois rôles différents → diversité de raisonnement recherchée. Chaque modèle reste sous ~65% de son budget mémoire → marge opérationnelle pour KV cache, pics de contexte, et futurs ajustements sans re-benchmarker tout le pipeline.

**Étape 6 — Vérifier la licence.**
Qwen3 et DeepSeek-R1-Distill-Llama-8B sont Apache 2.0 / licence permissive équivalente. Ministral-8B-Instruct-2410 est sous **Mistral Research License** (non-commercial sans accord séparé) — acceptable pour un cluster interne/recherche, à réévaluer si le projet devient commercial.

---

## 4. Plan d'exécution — fichiers à modifier

| # | Fichier | Nature du changement |
|---|---|---|
| M1 | `.env.example` | Remplacer les 3 valeurs `GENERATOR_MODEL`, `JUDGE_MODEL`, `ADVOCATE_MODEL` par les identifiants `hf.co/...` |
| M2 | `src/core/settings.py` | Mettre à jour les `default=` des 3 mêmes champs (garder les noms de champs et `validation_alias` inchangés) |
| M3 | `docs/architecture.md` | Mettre à jour le diagramme Mermaid (labels M2_200, M2_201, M3_models) avec les nouveaux noms de modèles |
| M4 | `ROADMAP.md` | Ajouter une ligne dans la table Phase C (tâche C4) référençant ce brief |
| M5 | `backlog.md` | Ajouter une entrée dans « Incohérences résolues » documentant le bug `mistral-small-3.2:7b` corrigé |
| M6 | `tests/test_settings.py` | Adapter les éventuelles assertions codées en dur sur les anciennes valeurs de modèles par défaut |

---

## 5. Diffs précis

### M1 — `.env.example`

```diff
- GENERATOR_MODEL=qwen3.5:14b
+ GENERATOR_MODEL=hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M
  # GENERATOR_MODEL_DIGEST=sha256:CHANGE_ME

  GENERATOR_ALT_MODEL=qwen3.5-35b-a3b
  # GENERATOR_ALT_MODEL_DIGEST=sha256:CHANGE_ME

  RERANKER_MODEL=bge-reranker-v2-m3
  # RERANKER_MODEL_DIGEST=sha256:CHANGE_ME

- JUDGE_MODEL=qwen3.5:7b
+ JUDGE_MODEL=hf.co/bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF:Q4_K_M
  # JUDGE_MODEL_DIGEST=sha256:CHANGE_ME

- ADVOCATE_MODEL=mistral-small-3.2:7b
+ ADVOCATE_MODEL=hf.co/bartowski/Ministral-8B-Instruct-2410-GGUF:Q4_K_M
  # ADVOCATE_MODEL_DIGEST=sha256:CHANGE_ME
```

### M2 — `src/core/settings.py`

```diff
      generator_model: str = Field(
-         default="qwen3.5:14b",
-         description="Modèle génération principal sur BC-250 (Q4_K_M ~9GB)",
+         default="hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M",
+         description="Modèle génération principal sur BC-250 — Qwen3-14B dense, Q4_K_M 9.0 Go vérifié HF",
          validation_alias="GENERATOR_MODEL",
      )
```

```diff
      judge_model: str = Field(
-         default="qwen3.5:7b",
+         default="hf.co/bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF:Q4_K_M",
+         description="Juge — distillation R1 sur backbone Llama 8B, Q4_K_M 4.92 Go, lignée distincte du générateur Qwen",
          validation_alias="JUDGE_MODEL",
      )
```

```diff
      advocate_model: str = Field(
-         default="mistral-small-3.2:7b",
+         default="hf.co/bartowski/Ministral-8B-Instruct-2410-GGUF:Q4_K_M",
+         description="Avocat du diable — Ministral-8B-Instruct-2410, Q4_K_M 4.91 Go (corrige bug: mistral-small-3.2 n'existe qu'en 24B/14.3 Go, incompatible RTX 4000 8 Go)",
          validation_alias="ADVOCATE_MODEL",
      )
```

### M4 — `ROADMAP.md` (table Phase C)

```diff
  | C4 | Pull des modèles (Ollama M1/M2/M3) + lock digests SHA256 dans `.env` | `.env`, docs |
+ | C4.1 | Résolution Hugging Face exclusive (hf.co/...) pour Générateur (Qwen3-14B), Juge (DeepSeek-R1-Distill-Llama-8B), Avocat (Ministral-8B-2410) — cf. `docs/BRIEF-INTEGRATION-MODELES-Q4-HF.md` | `.env`, `settings.py` |
```

### M5 — `backlog.md` (section Incohérences résolues)

```diff
  | `src/core/settings.py` | `postgres_password = "CHANGE_ME"` en dur | **✅ Validator prod** lève `InsecurePasswordConfigError` déjà en place |
+ | `.env.example` / `src/core/settings.py` | `ADVOCATE_MODEL=mistral-small-3.2:7b` — modèle inexistant à cette taille (Mistral Small 3.2 = 24B/14.3 Go, incompatible RTX 4000 8 Go) | **✅ remplacé par Ministral-8B-Instruct-2410 Q4_K_M (4.91 Go), résolu via hf.co/bartowski/...** |
```

---

## 6. Checklist de validation

- [ ] `.env.example` contient les 3 nouvelles valeurs `hf.co/...` exactes (copier-coller depuis la section 5, ne pas retaper)
- [ ] `settings.py` compile et les tests `tests/test_settings.py` passent (mock-first, aucun accès réseau requis)
- [ ] Aucune référence résiduelle à `mistral-small-3.2:7b`, `qwen3.5:7b` (juge) dans `.env.example` / `src/core/settings.py`
- [ ] `docs/architecture.md` reflète les nouveaux noms dans le diagramme Mermaid
- [ ] `ROADMAP.md` / `backlog.md` mis à jour avec traçabilité de la décision
- [ ] Le champ `*_MODEL_DIGEST` correspondant reste vide (`CHANGE_ME`) tant que le pull réel n'a pas eu lieu (Phase C) — ne pas inventer de digest SHA256

---

## 7. Ce que ce brief NE couvre PAS

- Le **pull réel** des modèles (`ollama pull hf.co/...`) : reste tâche **C4**, bloquée par la livraison matérielle des 3 machines (mock-first, D10).
- Le calcul des digests SHA256 de verrouillage : à faire **après** le premier pull réel, pas avant.
- `qwen2.5-vl` : alternative vision documentée dans `backlog.md` (Phase 5.2), non retenue comme valeur par défaut.
- Toute modification de `docker-compose.*.yml` ou des scripts Proxmox : aucun impact, ces fichiers ne référencent pas les noms de modèles.

---

## 8. Extension C4.2 — Résolution HF de tous les modèles (01/08/2026)

Extension du principe « Hugging Face exclusif » (contrainte de source du §intro) aux 7 modèles restants, initialement déclarés hors périmètre du brief C4.1.

| Rôle | Machine | Modèle | Repo Hugging Face | Quant | Taille |
|---|---|---|---|---|---|
| Embedding | M1 CPU | nomic-embed-text-v2-moe | `nomic-ai/nomic-embed-text-v2-moe-GGUF` | Q8_0 | 488 MiB |
| Reranker | M2 RTX 4000 | bge-reranker-v2-m3 | `gpustack/bge-reranker-v2-m3-GGUF` | Q4_K_M | ~437 Mo |
| Évaluateur | M1 CPU | Granite 4.1 8B | `ibm-granite/granite-4.1-8b-instruct-GGUF` | Q4_K_M | ~4,8 Go |
| Générateur alternatif | M3 BC-250 | Qwen3-30B-A3B | `Qwen/Qwen3-30B-A3B-GGUF` | Q2_K | 11,3 Go |
| Text-to-SQL | M3 BC-250 | Qwen3-Coder-30B-A3B | `unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF` | Q2_K | ~11 Go |
| Vision | M3 BC-250 | llava-v1.6-vicuna-13b | `cjpais/llava-v1.6-vicuna-13b-gguf` | Q4_K_M | 7,87 Go |
| Fast-check | M3 BC-250 | granite-4.0-h-tiny | `ibm-granite/granite-4.0-h-tiny-GGUF` | Q4_K_M | ~3 Go |

**Décisions de substitution** (modèles inexistants en réel sous les noms fictionnels du projet) :

- **Évaluateur** : `qwen3.5:3b` n'existe pas → **Granite 4.1 8B** (Q4_K_M ~4,8 Go, CPU M1) — diversification de lignée vs Générateur Qwen3-14B (décision 02/08/2026).
- **Générateur alternatif** : `qwen3.5-35b-a3b` → **Qwen3-30B-A3B officiel** ; Q2_K (11,3 Go) faute d'IQ2_M publié par Qwen.
- **Text-to-SQL** : `qwen3-coder-30b-a3b` → **Qwen3-Coder-30B-A3B-Instruct** ; Q2_K retenu (IQ2_M non vérifié dans les repos GGUF), ~11 Go dans le budget 12 Go du BC-250.
- **Vision** : `llava-next:13b` → **llava-v1.6-vicuna-13b** (Q4_K_M 7,87 Go, + mmproj géré par Ollama).

Les `*_MODEL_DIGEST` restent en `CHANGE_ME` tant que le pull réel (Phase C4) n'a pas eu lieu.

---

## État d'avancement (31/07/2026)

- [x] **M0** — Ce fichier de brief créé (traçabilité C4.1)
- [x] **M1** — `.env.example` : 3 valeurs `hf.co/...` posées
- [x] **M2** — `src/core/settings.py` : defaults + descriptions mis à jour
- [x] **M3** — `docs/architecture.md` : 6 labels Mermaid mis à jour
- [x] **M4** — `ROADMAP.md` : tâche C4.1 ajoutée
- [x] **M5** — `backlog.md` : entrée « Incohérences résolues » ajoutée
- [x] **M6** — `tests/test_settings.py` : aucune assertion sur les modèles (non-régression vérifiée)

## État d'avancement extension C4.2 (01/08/2026)

- [x] **M7** — `settings.py` / `.env.example` : 7 champs résolus `hf.co/...` (embedding, reranker, évaluateur, générateur alt, text2sql, vision, fastcheck)
- [x] **M8** — Mermaid : README (6 blocs), `docs/architecture.md` (2 blocs), `docs/diagrams/` 01/02/03/06 — labels à jour (noms courts)
- [x] **M9** — `docs/deployment-guide.md` : commandes `ollama pull hf.co/...@sha256:...` à jour
- [x] **M10** — `backlog.md` : tableaux/checklists modèles alignés
- [x] **M11** — `ROADMAP.md` : tâche C4.2 ajoutée
- [x] **M12** — Docstrings `src/agents/generator.py`, `src/agents/evaluator.py` mises à jour
