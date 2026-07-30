"""Configuration centralisée via Pydantic Settings.

Single source of truth pour toute la stack. Charge .env au démarrage.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration globale du cluster RAG multi-agents."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parents[3] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ──────────────────────────────────────────────
    # API Cluster (LXC 102 : API Gateway / nginx)
    # ──────────────────────────────────────────────
    cluster_api_url: HttpUrl = Field(
        default="http://localhost:8000",
        description="URL de base de l'API cluster (exposée via nginx LXC 102)",
        validation_alias="CLUSTER_API_URL",
    )

    api_version: str = Field(
        default="v1",
        description="Version API dans l'URL path (/api/v1/)",
        validation_alias="API_VERSION",
    )

    # ──────────────────────────────────────────────
    # Obsidian Vault (pattern Karpathy)
    # ──────────────────────────────────────────────
    wiki_vault_path: Path = Field(
        default=Path("/data/wiki"),
        description="Chemin absolu du vault partagé sur LXC Master (bind mount ou NFS)",
        validation_alias="WIKI_VAULT_PATH",
    )

    raw_data_path: Path = Field(
        default=Path("/data/raw"),
        description="Sources brutes ingérées (immutable)",
        validation_alias="RAW_DATA_PATH",
    )

    index_data_path: Path = Field(
        default=Path("/data/index"),
        description="Index/search auxiliaires",
        validation_alias="INDEX_DATA_PATH",
    )

    # ──────────────────────────────────────────────
    # Ollama Endpoints (3 nœuds)
    # ──────────────────────────────────────────────
    ollama_m1_url: HttpUrl = Field(
        default="http://10.10.0.1:11434",
        description="Ollama Machine 1 (Master) — Embedding CPU principal + Evaluator + fallback",
        validation_alias="OLLAMA_M1_URL",
    )

    ollama_m2_url: HttpUrl = Field(
        default="http://10.10.0.2:11434",
        description="Ollama Machine 2 (GPU Worker) — Reranker, Judge, Avocat, Backup Embedding CPU",
        validation_alias="OLLAMA_M2_URL",
    )

    ollama_m3_url: HttpUrl = Field(
        default="http://10.10.0.3:11434",
        description="Ollama Machine 3 (BC-250 Baremetal) — Generator 14B/MoE, Text-to-SQL, Vision, Vulkan ONLY",
        validation_alias="OLLAMA_M3_URL",
    )

    # ──────────────────────────────────────────────
    # Modèles par rôle (digests SHA256 lockés dans .env pour reproductibilité)
    # ──────────────────────────────────────────────
    # Embedding
    embedding_model: str = Field(
        default="nomic-embed-text-v2-moe",
        description="Modèle embedding principal (768d, dense+sparse via bge-m3 fallback)",
        validation_alias="EMBEDDING_MODEL",
    )
    embedding_model_digest: str | None = Field(
        default=None,
        description="Digest SHA256 pour verrouiller la version (ex: sha256:abc123...)",
        validation_alias="EMBEDDING_MODEL_DIGEST",
    )
    embedding_host: Literal["m1", "m2"] = Field(
        default="m1",
        description="Hôte d'embedding principal (m1=Master CPU, m2=GPU Worker CPU backup)",
        validation_alias="EMBEDDING_HOST",
    )

    # Generator (BC-250)
    generator_model: str = Field(
        default="qwen3.5:14b",
        description="Modèle génération principal sur BC-250 (Q4_K_M ~9GB)",
        validation_alias="GENERATOR_MODEL",
    )
    generator_model_digest: str | None = Field(
        default=None,
        validation_alias="GENERATOR_MODEL_DIGEST",
    )
    generator_alt_model: str = Field(
        default="qwen3.5-35b-a3b",
        description="Modèle génération alternatif MoE (IQ2_M ~11GB)",
        validation_alias="GENERATOR_ALT_MODEL",
    )
    generator_alt_model_digest: str | None = Field(
        default=None,
        validation_alias="GENERATOR_ALT_MODEL_DIGEST",
    )

    # Reranker (RTX 4000)
    reranker_model: str = Field(
        default="bge-reranker-v2-m3",
        validation_alias="RERANKER_MODEL",
    )
    reranker_model_digest: str | None = Field(
        default=None,
        validation_alias="RERANKER_MODEL_DIGEST",
    )

    # Judge (RTX 4000)
    judge_model: str = Field(
        default="qwen3.5:7b",
        validation_alias="JUDGE_MODEL",
    )
    judge_model_digest: str | None = Field(
        default=None,
        validation_alias="JUDGE_MODEL_DIGEST",
    )

    # Avocat du diable (RTX 4000)
    advocate_model: str = Field(
        default="mistral-small-3.2:7b",
        validation_alias="ADVOCATE_MODEL",
    )
    advocate_model_digest: str | None = Field(
        default=None,
        validation_alias="ADVOCATE_MODEL_DIGEST",
    )

    # Evaluator (Master CPU)
    evaluator_model: str = Field(
        default="qwen3.5:3b",
        validation_alias="EVALUATOR_MODEL",
    )
    evaluator_model_digest: str | None = Field(
        default=None,
        validation_alias="EVALUATOR_MODEL_DIGEST",
    )

    # Text-to-SQL / Code (BC-250)
    text2sql_model: str = Field(
        default="qwen3-coder-30b-a3b",
        validation_alias="TEXT2SQL_MODEL",
    )
    text2sql_model_digest: str | None = Field(
        default=None,
        validation_alias="TEXT2SQL_MODEL_DIGEST",
    )

    # Vision (BC-250)
    vision_model: str = Field(
        default="llava-next:13b",
        validation_alias="VISION_MODEL",
    )
    vision_model_digest: str | None = Field(
        default=None,
        validation_alias="VISION_MODEL_DIGEST",
    )

    # Fast-check lexical (BC-250)
    fastcheck_model: str = Field(
        default="granite-4.0-h-tiny",
        validation_alias="FASTCHECK_MODEL",
    )
    fastcheck_model_digest: str | None = Field(
        default=None,
        validation_alias="FASTCHECK_MODEL_DIGEST",
    )

    # ──────────────────────────────────────────────
    # Vector Store (Qdrant)
    # ──────────────────────────────────────────────
    qdrant_url: HttpUrl = Field(
        default="http://10.10.0.1:6333",
        description="Qdrant sur Machine 1 (LXC 101)",
        validation_alias="QDRANT_URL",
    )
    qdrant_collection: str = Field(
        default="rag-wiki",
        description="Nom de la collection Qdrant (hybrid search natif: dense + sparse BM25)",
        validation_alias="QDRANT_COLLECTION",
    )
    qdrant_api_key: str | None = Field(
        default=None,
        description="API key Qdrant si activée (optionnel en LAN de confiance)",
        validation_alias="QDRANT_API_KEY",
    )

    # ──────────────────────────────────────────────
    # PostgreSQL (conversations, feedback, mémoire long-terme)
    # ──────────────────────────────────────────────
    postgres_host: str = Field(
        default="10.10.0.1",
        validation_alias="POSTGRES_HOST",
    )
    postgres_port: int = Field(default=5432, validation_alias="POSTGRES_PORT")
    postgres_db: str = Field(default="rag_cluster", validation_alias="POSTGRES_DB")
    postgres_user: str = Field(default="rag_user", validation_alias="POSTGRES_USER")
    postgres_password: str = Field(
        default="CHANGE_ME",
        description="DOIT être changé via .env — jamais en dur",
        validation_alias="POSTGRES_PASSWORD",
    )

    # ──────────────────────────────────────────────
    # Redis (cache, queue orchestrateur, sessions)
    # ──────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://10.10.0.1:6379/0",
        validation_alias="REDIS_URL",
    )

    # ──────────────────────────────────────────────
    # NFS Relay (évaluation séquentielle Judge → Avocat)
    # ──────────────────────────────────────────────
    nfs_relay_path: Path = Field(
        default=Path("/data/shared/evaluation-relay.json"),
        description="Fichier relay partagé M1↔M2 via NFS (/data/shared exporté par M1, monté sur M2)",
        validation_alias="NFS_RELAY_PATH",
    )
    relay_ttl_seconds: int = Field(
        default=300,
        description="TTL du fichier relay (stale si > 300s sans mise à jour)",
        validation_alias="RELAY_TTL_SECONDS",
    )
    judge_timeout_seconds: int = Field(
        default=120,
        description="Timeout Judge avant passage au Avocat avec status=timeout",
        validation_alias="JUDGE_TIMEOUT_SECONDS",
    )

    # ──────────────────────────────────────────────
    # Logging & Observabilité
    # ──────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        validation_alias="LOG_LEVEL",
    )
    log_format: Literal["json", "console"] = Field(
        default="json",
        description="JSON pour Loki/Grafana, console pour dev local",
        validation_alias="LOG_FORMAT",
    )
    correlation_id_header: str = Field(
        default="X-Correlation-ID",
        description="Header HTTP pour propagation correlation ID (traces distribuées)",
        validation_alias="CORRELATION_ID_HEADER",
    )

    # ──────────────────────────────────────────────
    # mTLS / Sécurité interne (Phase 0.13)
    # ──────────────────────────────────────────────
    mtls_enabled: bool = Field(
        default=False,
        description="Activer mTLS pour communications inter-services (certs pfSense CA)",
        validation_alias="MTLS_ENABLED",
    )
    mtls_ca_path: Path | None = Field(
        default=None,
        validation_alias="MTLS_CA_PATH",
    )
    mtls_cert_path: Path | None = Field(
        default=None,
        validation_alias="MTLS_CERT_PATH",
    )
    mtls_key_path: Path | None = Field(
        default=None,
        validation_alias="MTLS_KEY_PATH",
    )

    # ──────────────────────────────────────────────
    # Paramètres pipeline RAG
    # ──────────────────────────────────────────────
    chunk_size: int = Field(default=1024, validation_alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=128, validation_alias="CHUNK_OVERLAP")
    top_k_retrieval: int = Field(default=20, validation_alias="TOP_K_RETRIEVAL")
    top_k_rerank: int = Field(default=8, validation_alias="TOP_K_RERANK")
    similarity_threshold: float = Field(default=0.7, validation_alias="SIMILARITY_THRESHOLD")

    # ──────────────────────────────────────────────
    # OKF (Open Knowledge Format) v0.2
    # ──────────────────────────────────────────────
    okf_stale_after_days: int = Field(
        default=180,
        description="Jours avant qu'une page wiki soit marquée stale (frontmatter stale_after)",
        validation_alias="OKF_STALE_AFTER_DAYS",
    )
    okf_trust_tiers: list[str] = Field(
        default=["unverified", "machine-confirmed", "human-reviewed"],
        description="Tiers de confiance OKF pour champ verified.status",
        validation_alias="OKF_TRUST_TIERS",
    )

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────
    @property
    def api_prefix(self) -> str:
        return f"/api/{self.api_version}"

    @property
    def embedding_endpoint(self) -> str:
        host_url = self.ollama_m1_url if self.embedding_host == "m1" else self.ollama_m2_url
        return f"{host_url}/api/embed"

    @property
    def generator_endpoint(self) -> str:
        return f"{self.ollama_m3_url}/api/generate"

    @property
    def rerank_endpoint(self) -> str:
        return f"{self.ollama_m2_url}/api/rerank"

    @property
    def judge_endpoint(self) -> str:
        return f"{self.ollama_m2_url}/api/generate"

    @property
    def advocate_endpoint(self) -> str:
        return f"{self.ollama_m2_url}/api/generate"

    @property
    def evaluator_endpoint(self) -> str:
        return f"{self.ollama_m1_url}/api/generate"

    @property
    def postgres_dsn(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Instance singleton de la configuration (cache LRU)."""
    return Settings()


settings = get_settings()