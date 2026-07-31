"""Configuration centralisée via Pydantic Settings.

Single source of truth pour toute la stack. Charge .env au démarrage.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class InsecurePasswordConfigError(ValueError):
    def __init__(self) -> None:
        super().__init__(
            "postgres_password='CHANGE_ME' interdit avec environment='production'"
        )


class Settings(BaseSettings):
    """Configuration globale du cluster RAG multi-agents."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ──────────────────────────────────────────────
    # Environnement d'exécution
    # ──────────────────────────────────────────────
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        validation_alias="ENVIRONMENT",
    )

    # ──────────────────────────────────────────────
    # API Cluster (LXC 100, exposée via pfSense VM 104)
    # ──────────────────────────────────────────────
    cluster_api_url: HttpUrl = Field(  # type: ignore[assignment]
        default="http://localhost:8000",
        description="URL de base de l'API cluster (exposée via pfSense VM 104)",
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
    ollama_m1_url: HttpUrl = Field(  # type: ignore[assignment]
        default="http://10.10.0.1:11434",
        description="Ollama Machine 1 (Master) — Embedding CPU principal + Evaluator + fallback",
        validation_alias="OLLAMA_M1_URL",
    )

    ollama_m2_url: HttpUrl = Field(  # type: ignore[assignment]
        default="http://10.10.0.2:11434",
        description="Ollama Machine 2 (GPU Worker) — Reranker, Judge, Avocat, Backup Embedding CPU",
        validation_alias="OLLAMA_M2_URL",
    )

    ollama_m3_url: HttpUrl = Field(  # type: ignore[assignment]
        default="http://10.10.0.3:11434",
        description=(
            "Ollama Machine 3 (BC-250 Baremetal) — "
            "Generator 14B/MoE, Text-to-SQL, Vision, Vulkan ONLY"
        ),
        validation_alias="OLLAMA_M3_URL",
    )

    # ──────────────────────────────────────────────
    # Modèles par rôle (digests SHA256 lockés dans .env pour reproductibilité)
    # ──────────────────────────────────────────────
    # Embedding
    embedding_model: str = Field(
        default="hf.co/nomic-ai/nomic-embed-text-v2-moe-GGUF:Q8_0",
        description="Modèle embedding principal (768d, dense+sparse via bge-m3 fallback) — nomic-embed-text-v2-moe Q8_0 via HF",
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
        default="hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M",
        description="Modèle génération principal sur BC-250 — Qwen3-14B dense, Q4_K_M 9.0 Go (HF)",
        validation_alias="GENERATOR_MODEL",
    )
    generator_model_digest: str | None = Field(
        default=None,
        validation_alias="GENERATOR_MODEL_DIGEST",
    )
    generator_alt_model: str = Field(
        default="hf.co/Qwen/Qwen3-30B-A3B-GGUF:Q2_K",
        description="Modèle génération alternatif MoE — Qwen3-30B-A3B Q2_K ~11.3 Go (HF)",
        validation_alias="GENERATOR_ALT_MODEL",
    )
    generator_alt_model_digest: str | None = Field(
        default=None,
        validation_alias="GENERATOR_ALT_MODEL_DIGEST",
    )

    # Reranker (RTX 4000)
    reranker_model: str = Field(
        default="hf.co/gpustack/bge-reranker-v2-m3-GGUF:Q4_K_M",
        description="Reranker multilingue — bge-reranker-v2-m3 Q4_K_M via HF (RTX 4000)",
        validation_alias="RERANKER_MODEL",
    )
    reranker_model_digest: str | None = Field(
        default=None,
        validation_alias="RERANKER_MODEL_DIGEST",
    )

    # Judge (RTX 4000)
    judge_model: str = Field(
        default="hf.co/bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF:Q4_K_M",
        description=(
            "Juge — distillation R1 sur backbone Llama 8B, Q4_K_M 4.92 Go, "
            "lignée distincte du générateur Qwen"
        ),
        validation_alias="JUDGE_MODEL",
    )
    judge_model_digest: str | None = Field(
        default=None,
        validation_alias="JUDGE_MODEL_DIGEST",
    )

    # Avocat du diable (RTX 4000)
    advocate_model: str = Field(
        default="hf.co/bartowski/Ministral-8B-Instruct-2410-GGUF:Q4_K_M",
        description=(
            "Avocat du diable — Ministral-8B-Instruct-2410, Q4_K_M 4.91 Go "
            "(corrige bug: mistral-small-3.2 n'existe qu'en 24B/14.3 Go, "
            "incompatible RTX 4000 8 Go)"
        ),
        validation_alias="ADVOCATE_MODEL",
    )
    advocate_model_digest: str | None = Field(
        default=None,
        validation_alias="ADVOCATE_MODEL_DIGEST",
    )

    # Evaluator (Master CPU)
    evaluator_model: str = Field(
        default="hf.co/Qwen/Qwen3-4B-GGUF:Q4_K_M",
        description="Évaluateur — Qwen3-4B Q4_K_M ~2.5 Go (CPU M1, HF)",
        validation_alias="EVALUATOR_MODEL",
    )
    evaluator_model_digest: str | None = Field(
        default=None,
        validation_alias="EVALUATOR_MODEL_DIGEST",
    )

    # Text-to-SQL / Code (BC-250)
    text2sql_model: str = Field(
        default="hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q2_K",
        description="Text-to-SQL / Code — Qwen3-Coder-30B-A3B Q2_K ~11 Go (BC-250, HF)",
        validation_alias="TEXT2SQL_MODEL",
    )
    text2sql_model_digest: str | None = Field(
        default=None,
        validation_alias="TEXT2SQL_MODEL_DIGEST",
    )

    # Vision (BC-250)
    vision_model: str = Field(
        default="hf.co/cjpais/llava-v1.6-vicuna-13b-gguf:Q4_K_M",
        description="Vision — llava-v1.6-vicuna-13b Q4_K_M 7.87 Go (BC-250, HF)",
        validation_alias="VISION_MODEL",
    )
    vision_model_digest: str | None = Field(
        default=None,
        validation_alias="VISION_MODEL_DIGEST",
    )

    # Fast-check lexical (BC-250)
    fastcheck_model: str = Field(
        default="hf.co/ibm-granite/granite-4.0-h-tiny-GGUF:Q4_K_M",
        description="Fast-check lexical — granite-4.0-h-tiny Q4_K_M ~3 Go (BC-250, HF)",
        validation_alias="FASTCHECK_MODEL",
    )
    fastcheck_model_digest: str | None = Field(
        default=None,
        validation_alias="FASTCHECK_MODEL_DIGEST",
    )

    # ──────────────────────────────────────────────
    # Vector Store (Qdrant)
    # ──────────────────────────────────────────────
    qdrant_url: HttpUrl = Field(  # type: ignore[assignment]
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

    @model_validator(mode="after")
    def _forbid_default_password_in_production(self) -> Settings:
        if self.environment == "production" and self.postgres_password == "CHANGE_ME":
            raise InsecurePasswordConfigError
        return self

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
        description=(
            "Fichier relay partagé M1↔M2 via NFS "
            "(/data/shared exporté par M1, monté sur M2)"
        ),
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
    evaluation_enabled: bool = Field(
        default=False,
        description=(
            "Boucle d'évaluation multi-agents (Judge → Advocate → Evaluator) — "
            "défaut OFF en pré-déploiement (aucun LLM pullé, latence 4 appels LLM/requête). "
            "Décision D12 : activation optionnelle par requête/endpoint."
        ),
        validation_alias="EVALUATION_ENABLED",
    )

    # ──────────────────────────────────────────────
    # BC-250 Baremetal (Machine 3 — Vulkan ONLY)
    # ──────────────────────────────────────────────
    bc250_enabled: bool = Field(
        default=True,
        description="BC-250 présent et configuré dans le cluster",
        validation_alias="BC250_ENABLED",
    )
    bc250_cu_count: int = Field(
        default=24, ge=24, le=40,
        description="Compute Units actifs (24 stock, 40 via unlock patch duggasco)",
        validation_alias="BC250_CU_COUNT",
    )
    bc250_cpu_cores_unlocked: bool = Field(
        default=False,
        description="CPU core unlock appliqué (6c/12t → 8c/16t via SMU msg 0x98 rw-r-r-0644)",
        validation_alias="BC250_CPU_CORES_UNLOCKED",
    )
    bc250_vram_gib: int = Field(
        default=16, ge=8,
        description="VRAM GDDR6 unifiée en GiB (cpu+gpu même pool)",
        validation_alias="BC250_VRAM_GIB",
    )
    bc250_tdp_watts: int = Field(
        default=235,
        description="TDP max watts (cpu+gpu combiné, format compact)",
        validation_alias="BC250_TDP_WATTS",
    )
    bc250_vulkan_mesa_version: str = Field(
        default="25.1.3",
        description="Version minimum Mesa/RADV (Debian Experimental, pin-priority 500)",
        validation_alias="BC250_VULKAN_MESA_VERSION",
    )
    bc250_kernel_version: str = Field(
        default="6.18.18",
        description="Version noyau cible (pin apt-mark hold, éviter 6.15/6.17 buggés)",
        validation_alias="BC250_KERNEL_VERSION",
    )
    bc250_grub_cmdline: str = Field(
        default="amdgpu.gttsize=14750 ttm.pages_limit=3959290 ttm.page_pool_size=3959290",
        description="Paramètres GRUB obligatoires (triplet VRAM — jamais amd_iommu=on)",
        validation_alias="BC250_GRUB_CMDLINE",
    )
    bc250_ttm_pages_limit: int = Field(
        default=3959290,
        description="ttm.pages_limit sysfs (plafond mémoire GPU, ~15 GiB)",
        validation_alias="BC250_TTM_PAGES_LIMIT",
    )
    bc250_ttm_page_pool_size: int = Field(
        default=3959290,
        description="ttm.page_pool_size (identique à pages_limit)",
        validation_alias="BC250_TTM_PAGE_POOL_SIZE",
    )
    bc250_gov_freq_mhz: int = Field(
        default=1500,
        description="Fréquence GPU max MHz (safe-point governor pour usage soutenu)",
        validation_alias="BC250_GOV_FREQ_MHZ",
    )
    bc250_gov_voltage_mv: int = Field(
        default=900,
        description="Voltage GPU mV (safe-point governor)",
        validation_alias="BC250_GOV_VOLTAGE_MV",
    )
    bc250_gov_config_path: str = Field(
        default="/etc/cyan-skillfish-governor-smu/config.toml",
        description="Chemin absolu config cyan-skillfish-governor-smu",
        validation_alias="BC250_GOV_CONFIG_PATH",
    )
    bc250_setup_dir: str = Field(
        default="infrastructure/bc250",
        description="Chemin relatif (depuis racine projet) vers scripts BC-250",
        validation_alias="BC250_SETUP_DIR",
    )

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

    # ── BC-250 helpers ────────────────────────────
    @property
    def bc250_cu_unlock_script(self) -> str:
        return f"{self.bc250_setup_dir}/enable-40cu-unlock.sh"

    @property
    def bc250_core_unlock_script(self) -> str:
        return f"{self.bc250_setup_dir}/enable-cpu-core-unlock.sh"

    @property
    def bc250_vulkan_setup_script(self) -> str:
        return f"{self.bc250_setup_dir}/setup-vulkan-stack.sh"

    @property
    def bc250_grub_cmdline_inject(self) -> str:
        """Triplet GRUB prêt pour GRUB_CMDLINE_LINUX_DEFAULT."""
        return self.bc250_grub_cmdline

    @property
    def bc250_ollama_systemd_override(self) -> dict[str, str]:
        """Envs Vulkan pour systemd override Ollama (Service/Environment)."""
        return {
            "HSA_OVERRIDE_GFX_VERSION": "10.3.0",
            "AMD_VULKAN_ICD": "RADV",
            "RADV_FORCE_VRS": "false",
            "OLLAMA_USE_VULKAN": "1",
            "OLLAMA_INTEL_GPU": "false",
            "OLLAMA_CUDA": "false",
            "OLLAMA_HIP_VISIBLE_DEVICES": "",
            "OLLAMA_LLM_LIBRARY": "llama.cpp",
            "GGML_VULKAN_DEVICE": "0",
        }

    def bc250_healthcheck_cmds(self) -> list[str]:
        """Commandes de vérification post-reboot BC-250."""
        cmds = []
        if self.bc250_cu_count > 24:
            cmds.append("sudo dmesg | grep active_cu_number")
            cmds.append("RADV_DEBUG=info vulkaninfo --summary 2>&1 | grep num_cu")
        if self.bc250_cpu_cores_unlocked:
            cmds.append("lscpu | grep -E 'CPU\\(s\\)|Core\\(s\\) per socket'")
            cmds.append("sudo dmesg | grep -E 'smp|lapic' | tail -5")
        cmds.extend([
            f"cat /sys/module/ttm/parameters/pages_limit  # expect {self.bc250_ttm_pages_limit}",
            "vulkaninfo --summary 2>&1 | grep deviceName",
        ])
        return cmds


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Instance singleton de la configuration (cache LRU)."""
    return Settings()


settings = get_settings()
