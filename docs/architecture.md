# Architecture RAG multi-agents

> Cluster Proxmox 3 nœuds : Machine 1 Master (Xeon CPU embedding + Qdrant + Wiki), Machine 2 GPU Worker (RTX 4000 Reranker/Juge/Avocat), Machine 3 BC-250 baremetal (Vulkan-only Generator 14B/MoE + Text-to-SQL + Vision). BC-250 CPU au repos.

## Flux logique — pattern Karpathy, ingestion, requête

```mermaid
flowchart TB
    classDef schema fill:#f5f3ff,stroke:#8b5cf6,stroke-width:2px
    classDef wiki fill:#eff6ff,stroke:#2563eb,stroke-width:2px
    classDef src fill:#fff7ed,stroke:#f97316,stroke-width:2px
    classDef m1 fill:#f0f9ff,stroke:#0ea5e9,stroke-width:2px
    classDef m2 fill:#f0fdf4,stroke:#22c55e,stroke-width:2px
    classDef m3 fill:#fff7ed,stroke:#f97316,stroke-width:2px
    classDef op fill:#ffffff,stroke:#8b5cf6,stroke-width:1.5px,stroke-dasharray: 3 3
    classDef final fill:#ffffff,stroke:#2563eb,stroke-width:2px

    subgraph Karpathy["Pattern Karpathy — 3 couches + 3 opérations"]
        Schema["📐 Schema<br/>AGENTS.md (structure, prompts)"]:::schema
        WikiPersist["📓 Wiki Persistant<br/>Pages markdown interreliées"]:::wiki
        Sources["📄 Sources Brutes<br/>Articles, fichiers, images"]:::src
        Ingest["⬇ Ingest<br/>Source → Wiki"]:::op
        Lint["🔍 Lint<br/>Contradictions, gaps"]:::op
    end

    Documents["Documents<br/>Sources brutes"]:::src
    Chunking["Chunking<br/>Chevauchement"]:::m1
    Augment["Augmentation<br/>Métadonnées, contexte"]:::m1
    BM25["Index lexical (BM25)<br/>Qdrant sparse — M1"]:::m1
    EmbedCPU["Embedding CPU<br/>nomic-v2-moe 768d — M1"]:::m1
    VectorDB["VectorDB (Qdrant)<br/>Index vectoriel — M1 LXC 101"]:::m1

    Requete["Requête<br/>Question posée"]:::final
    Planif["Planificateur<br/>Stratégie + outils"]:::m2
    Rewrite["Réécriture<br/>Contexte conversationnel"]:::m2
    RechLex["Recherche lexicale<br/>BM25 — Machine 1"]:::m1
    RechVec["Vectorielle<br/>Similarité — Machine 1"]:::m1
    Variantes["Variantes<br/>SQL/Img — Machine 3 (BC250)"]:::m3
    Rerank["Reranker<br/>bge-v2-m3 — RTX 4000 M2"]:::m2
    SavoirInterne["Savoir interne<br/>Entraînement"]:::src
    Contexte["Contexte<br/>Assemblage enrichi"]:::m2
    CourtTerme["Court terme<br/>Fenêtre contextuelle"]:::src
    ModeleGen["Modèle génératif<br/>qwen3.5:14b/35b MoE — M3"]:::m3
    JugeLLM["Juge (LLM)<br/>qwen3.5:7b — RTX 4000 M2"]:::m2
    Avocat["Avocat du diable<br/>mistral-small-3.2:7b — M2"]:::m2
    Evaluateur["Évaluateur<br/>qwen3.5:3b CPU — M1"]:::m1
    Relay["📄 relay.json<br/>Handoff séquentiel — 1 seul modèle<br/>chargé à la fois sur RTX 4000"]:::op
    ReponseFinale["Réponse finale<br/>Retour à l'utilisateur"]:::final

    Schema -.->|gouverne| WikiPersist -.-> Sources
    Ingest -.-> Lint

    Documents --> Chunking --> Augment
    Augment --> BM25
    Augment --> EmbedCPU --> VectorDB
    VectorDB -.->|Ingest, MAJ index.md| WikiPersist

    Requete --> Planif --> Rewrite
    Rewrite --> RechLex
    Rewrite --> RechVec
    Rewrite --> Variantes
    RechLex --> Rerank
    RechVec --> Rerank
    Variantes --> Rerank
    Rerank --> SavoirInterne
    Rerank --> Contexte
    Rerank --> CourtTerme
    Contexte --> ModeleGen
    ModeleGen -.->|relay.json ①, réponse brute| Relay
    Relay -.-> JugeLLM
    JugeLLM -.->|relay.json ②, unload VRAM| Relay
    Relay -.-> Avocat
    Avocat -.->|relay.json ③, unload VRAM| Relay
    Relay -.-> Evaluateur
    Evaluateur --> ReponseFinale
    Evaluateur -.->|feedback| Planif
    ReponseFinale -.->|compounding, archivage| WikiPersist
    Lint -.->|pages orphelines, contradictions, entités manquantes, données obsolètes| Requete
```

## Mapping infrastructure — cluster (3 machines)

```mermaid
flowchart TB
    classDef m1 fill:#f0f9ff,stroke:#0ea5e9,stroke-width:2px
    classDef m2 fill:#f0fdf4,stroke:#22c55e,stroke-width:2px
    classDef m3 fill:#fff7ed,stroke:#f97316,stroke-width:2px
    classDef warn fill:#fef2f2,stroke:#ef4444,stroke-width:2px,stroke-dasharray: 2 2
    classDef cold fill:#fef3c7,stroke:#d97706,stroke-width:2px
    classDef op fill:#ffffff,stroke:#8b5cf6,stroke-width:1.5px,stroke-dasharray: 3 3

    subgraph Machine1["Machine 1: Master · 2× Xeon 2699 v4 / 32GB ECC"]
        M1_100["LXC 100: Orchestrator + Wiki"]:::m1
        M1_101["LXC 101: Qdrant VectorDB"]:::m1
        M1_104["VM 104: pfSense (reverse proxy + firewall)"]:::m1
        M1_vault["/data/wiki vault"]:::m1
        M1_models["Modèles CPU (M1)<br/>Embedding: nomic-v2-moe 768d Q8_0 (primary)<br/>Evaluator: qwen3.5:3b Q4_K_M"]:::m1
        M1_wiki["Agent Wiki Maintainer<br/>Ingest / Query / Lint / Index.md + Log.md"]:::m1
    end

    subgraph Machine2["Machine 2: GPU Worker · Xeon 2698 v4 / 64GB ECC · RTX 4000 8GB"]
        M2_200["LXC 200: Inference GPU<br/>Reranker: bge-v2-m3 Q4_K_M<br/>Judge: qwen3.5:7b Q4_K_M"]:::m2
        M2_201["LXC 201: Workers Agents<br/>Avocat: mistral-3.2:7b Q4_K_M<br/>Backup Embedding CPU (Xeon 20c/40t idle)"]:::m2
    end

    subgraph Machine3["Machine 3: BC250 · Baremetal Debian Sid · 16GB GDDR6 (12GB IA) · 40 CU · Vulkan-only · CPU au repos"]
        M3_models["Modèles Vulkan (M3)<br/>Generator: qwen3.5:14b Q4_K_M ou 35b-a3b MoE IQ2_M<br/>Text-to-SQL: qwen3-coder 30b-a3b MoE IQ2_M<br/>Vision: llava-next:13b Q4<br/>Fast-check: granite-4.0-h-tiny"]:::m3
        M3_warn["⚠ RÈGLE D'OR BC250<br/>CPU = serviteur du GPU<br/>Aucune charge CPU (embedding, batch) quand le GPU infère"]:::warn
    end

    Relay["📄 relay.json<br/>Handoff séquentiel — 1 seul modèle<br/>chargé à la fois sur RTX 4000"]:::op

    Cold["🧊 Cold save<br/>OMV LXC 105 (M2) → HDD 2TB (LUKS)<br/>borg pull M1/M3 + rsync — Qdrant + wiki + configs<br/>cron 02:00-05:00 · retention 14j/3m"]:::cold

    M1_100 --> M1_101
    M1_wiki --> M1_vault
    M1_100 -.->|reranking| M2_200
    M1_101 -.->|recherche| M2_200
    M2_200 -.->|relay.json ① Juge| Relay
    Relay -.->|relay.json ② Avocat| M2_201
    M2_201 -.->|relay.json ③ Évaluateur| M1_100
    M1_100 -.->|génération| M3_models
    M2_200 -.->|contexte enrichi| M3_models
    M1_101 -.->|snapshot 02:00| Cold
    M1_100 -.->|rsync 02:30| Cold
```
