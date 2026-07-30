# Roadmap

État réel au 30/07/2026 : phase de conception documentaire terminée. Aucun code n'existe encore dans ce dépôt. Les cases cochées ci-dessous concernent uniquement la documentation, pas l'implémentation.

**Alignement OKF v0.2** : Frontmatter wiki migré vers format OKF v0.2 (type obligatoire, verified/trust tier, status/stale_after, sources enrichis). CLI `okf` + plugin Obsidian `okf-enforcer` identifiés pour lint futur — pas de dépendance dure tant que pré-1.0.

## Documentation
- [x] README consolidé (architecture, infra, stack, guide d'installation, intégration Obsidian Vault)
- [x] Schéma d'architecture (`docs/architecture.svg`)
- [ ] Documentation API (OpenAPI/Swagger)
- [ ] Tutoriel d'installation pas-à-pas testé de bout en bout
- [ ] **Template OKF `docs/claude-md-template.md` → `/data/wiki/CLAUDE.md`** (frontmatter OKF v0.2)
- [ ] **Script `scripts/okf-lint.py` : validation frontmatter OKF + détection stale/orphelins/contradictions** (remplace/partiel `/api/v1/lint`)

## Infrastructure
- [ ] Trancher Debian Testing/Sid vs antiX-26 pour le nœud BC-250 (antiX déjà en place selon les notes de Michel — vérifier que Mesa 25.1.3+ y est disponible avant d'exécuter le script tel quel)
- [ ] Tester `infrastructure/bc250/setup-vulkan-stack.sh` sur le matériel réel (script de référence non validé)
- [ ] Tester `infrastructure/bc250/enable-40cu-unlock.sh`, lancer `cu_map.sh` en premier pour vérifier le harvest pattern du board
- [ ] Vérifier après reboot que `ttm.pages_limit` tient à 4194304 (piège documenté : `systemd-tmpfiles` peut l'écraser après boot)
- [ ] Script `infrastructure/proxmox/create-lxc-master.sh`
- [ ] Script `infrastructure/proxmox/create-lxc-gpu.sh`
- [ ] `infrastructure/docker/docker-compose.orchestrator.yml`
- [ ] `infrastructure/docker/docker-compose.vector-db.yml`

## Backend RAG
- [ ] Pipeline RAG de base (chunking, embedding, indexation)
- [ ] Recherche hybride (lexicale + vectorielle)
- [ ] Reranking
- [ ] Choix orchestrateur d'agents : CrewAI vs LangGraph
- [ ] Agents Juge / Avocat du diable / Évaluateur
- [ ] Endpoint `/api/v1/query`
- [ ] Actions WikiTools (read_page, write_page, append_log, update_index, lint)
- [ ] **Endpoints OKF : `/api/v1/okf/validate`, `/api/v1/okf/list`, `/api/v1/okf/show`** (wrappers CLI `okf`)

## Intégration Obsidian Vault (pattern Karpathy)
- [ ] Bind mount vault partagé (NFS/SMB entre LXC 100 et client)
- [ ] Structure vault : index.md, log.md, entities/, concepts/, sources/, synthesis/
- [ ] Workflow ingestion : source → pages wiki (avec évaluation multi-agents)
- [ ] Workflow query : question → recherche wiki → synthèse avec citations
- [ ] Workflow lint : détection contradictions, orphelins, gaps
- [ ] **Structure OKF : `index.md` (catalogue §8) + `log.md` (chronologie §9) + frontmatter validé**

## Fonctionnalités futures
- [ ] Text-to-SQL sur le nœud BC250
- [ ] Dashboard Grafana (tokens/sec par nœud)
- [ ] Mémoire long-terme distribuée
- [ ] Benchmarks comparatifs RTX 4000 vs BC250
- [ ] Support modèles vision (LLaVA)

## Divers à ne pas oublier avant publication GitHub
- [ ] Renseigner l'email de contact dans le README (placeholder actuel à remplacer)
- [ ] Vérifier qu'aucune IP ou mot de passe n'est codé en dur (utiliser `.env`)
- [ ] Ajouter les tests avant tout premier merge sur `main`
