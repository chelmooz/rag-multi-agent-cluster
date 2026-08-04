"""Configuration centralisée via Pydantic Settings — sous-modèles composés.

Single source of truth pour toute la stack. Charge .env au démarrage.

Architecture (item 3 de la roadmap d'audit) :
- Une section `BaseSettings` par service (Ollama, Qdrant, Redis, SSH, ...)
  avec préfixes/aliases d'environnement conservés à l'identique (`.env` intact).
- `Settings` compose les sections ; les réglages transverses patchables par
  les tests restent des champs racine (similarity_threshold, monitoring_offline,
  memory_manager_enabled, chat_max_context_chars, bloc PostgreSQL).
- Façade de compatibilité : `__getattr__`/`__setattr__` déléguent les accès
  plats (`settings.ollama_m1_url`) vers les sections, pour préserver les
  ~80 call-sites existants et les écritures directes des tests sans migration.
  Les nouveaux accès peuvent utiliser la forme pointée (`settings.ollama.m1_url`).
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, HttpUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def _section_config(env_prefix: str = "") -> SettingsConfigDict:
    return SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix=env_prefix,
    )


class InsecurePasswordConfigError(ValueError):
    def __init__(self) -> None:
        super().__init__("postgres_password='CHANGE_ME' interdit avec environment='production'")


# ──────────────────────────────────────────────
# Sections par service
# ──────────────────────────────────────────────


class ApiSettings(BaseSettings):
    """API Cluster (LXC 100, exposée via pfSense VM 104)."""

    model_config = _section_config()

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


class VaultSettings(BaseSettings):
    """Obsidian Vault (pattern Karpathy)."""

    model_config = _section_config()

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


class OllamaSettings(BaseSettings):
    """Endpoints Ollama (3 nœuds)."""

    model_config = _section_config(env_prefix="OLLAMA_")

    m1_url: HttpUrl = Field(  # type: ignore[assignment]
        default="http://10.10.0.1:11434",
        description="Ollama Machine 1 (Master) — Embedding CPU principal + Evaluator + fallback",
    )

    m2_url: HttpUrl = Field(  # type: ignore[assignment]
        default="http://10.10.0.2:11434",
        description="Ollama Machine 2 (GPU Worker) — Reranker, Judge, Avocat, Backup Embedding CPU",
    )

    m3_url: HttpUrl = Field(  # type: ignore[assignment]
        default="http://10.10.0.3:11434",
        description=(
            "Ollama Machine 3 (BC-250 Baremetal) — "
            "Generator 14B/MoE, Text-to-SQL, Vision, Vulkan ONLY"
        ),
    )


class ModelsSettings(BaseSettings):
    """Modèles par rôle (digests SHA256 lockés dans .env pour reproductibilité)."""

    model_config = _section_config()

    # Embedding
    embedding_model: str = Field(
        default="hf.co/nomic-ai/nomic-embed-text-v2-moe-GGUF:Q8_0",
        description=(
            "Modèle embedding principal (768d, dense+sparse via bge-m3 fallback) "
            "— nomic-embed-text-v2-moe Q8_0 via HF"
        ),
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
        default="hf.co/ibm-granite/granite-4.1-8b-instruct-GGUF:Q4_K_M",
        description="Évaluateur — Granite 4.1 8B Q4_K_M (CPU M1, HF, diversification lignée)",
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


class QdrantSettings(BaseSettings):
    """Vector Store (Qdrant)."""

    model_config = _section_config(env_prefix="QDRANT_")

    url: HttpUrl = Field(  # type: ignore[assignment]
        default="http://10.10.0.1:6333",
        description="Qdrant sur Machine 1 (LXC 101)",
    )

    collection: str = Field(
        default="rag-wiki",
        description="Nom de la collection Qdrant (hybrid search natif: dense + sparse BM25)",
    )

    api_key: str | None = Field(
        default=None,
        description="API key Qdrant si activée (optionnel en LAN de confiance)",
    )


class RedisSettings(BaseSettings):
    """Cache, queue orchestrateur, sessions."""

    model_config = _section_config(env_prefix="REDIS_")

    url: str = Field(
        default="redis://10.10.0.1:6379/0",
        description="URL Redis (cache, queue, sessions)",
    )


class RelaySettings(BaseSettings):
    """NFS Relay (évaluation séquentielle Judge → Avocat)."""

    model_config = _section_config()

    nfs_relay_path: Path = Field(
        default=Path("/data/shared/evaluation-relay.json"),
        description=(
            "Fichier relay partagé M1↔M2 via NFS (/data/shared exporté par M1, monté sur M2)"
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


class SSHSettings(BaseSettings):
    """Accès SSH (MemoryManager — monitoring M2/M3)."""

    model_config = _section_config()

    m2_ssh_host: str = Field(
        default="10.10.0.2",
        description="Adresse M2 pour SSH (monitoring nvidia-smi)",
        validation_alias="M2_SSH_HOST",
    )
    m2_ssh_user: str = Field(
        default="root",
        description="Utilisateur SSH M2 (clé déployée via cloud-init Proxmox)",
        validation_alias="M2_SSH_USER",
    )
    m2_ssh_port: int = Field(
        default=22,
        validation_alias="M2_SSH_PORT",
    )
    m2_ssh_key_path: Path | None = Field(
        default=Path("/root/.ssh/id_rsa"),
        description="Chemin privé SSH M2 (dans LXC 100 orchestrateur)",
        validation_alias="M2_SSH_KEY_PATH",
    )

    m3_ssh_host: str = Field(
        default="10.10.0.3",
        description="Adresse M3 BC-250 pour SSH (monitoring free, loadavg)",
        validation_alias="M3_SSH_HOST",
    )
    m3_ssh_user: str = Field(
        default="root",
        description="Utilisateur SSH M3 (clé déployée via cloud-init Proxmox)",
        validation_alias="M3_SSH_USER",
    )
    m3_ssh_port: int = Field(
        default=22,
        validation_alias="M3_SSH_PORT",
    )
    m3_ssh_key_path: Path | None = Field(
        default=Path("/root/.ssh/id_rsa"),
        description="Chemin privé SSH M3 (dans LXC 100 orchestrateur)",
        validation_alias="M3_SSH_KEY_PATH",
    )


class MonitoringSettings(BaseSettings):
    """Memory Manager — configuration, seuils et Glances."""

    model_config = _section_config()

    memory_manager_persist_to_qdrant: bool = Field(
        default=False,
        description=(
            "Persister historique alertes mémoire dans collection Qdrant "
            "(cluster_memory_history) — trend analysis"
        ),
        validation_alias="MEMORY_MANAGER_PERSIST_TO_QDRANT",
    )
    memory_snapshot_interval_seconds: int = Field(
        default=60,
        description="Intervalle entre snapshots mémoire (monitoring continu)",
        validation_alias="MEMORY_SNAPSHOT_INTERVAL_SECONDS",
    )
    memory_manager_log_alerts: bool = Field(
        default=True,
        description="Log structuré des alertes mémoire",
        validation_alias="MEMORY_MANAGER_LOG_ALERTS",
    )

    # Seuils M1 (Master)
    m1_qdrant_ram_threshold_mb: int = Field(
        default=28_000,
        description="Seuil alerte Qdrant RAM (28 GB sur 32 GB)",
        validation_alias="M1_QDRANT_RAM_THRESHOLD_MB",
    )
    m1_embedding_cpu_threshold_percent: float = Field(
        default=80.0,
        description="Seuil alerte CPU embedding % (avant throttle)",
        validation_alias="M1_EMBEDDING_CPU_THRESHOLD_PERCENT",
    )

    # Seuils M2 (GPU Worker)
    m2_rtx4000_vram_threshold_mb: int = Field(
        default=7_680,
        description="Seuil alerte RTX4000 VRAM (7.5 GB sur 8 GB)",
        validation_alias="M2_RTX4000_VRAM_THRESHOLD_MB",
    )
    m2_rtx4000_vram_reserve_mb: int = Field(
        default=5_500,
        description="Réserve requise M2 pour charger un 8B Q4_K_M (~5.5 GB)",
        validation_alias="M2_RTX4000_VRAM_RESERVE_MB",
    )
    m2_rtx4000_vram_total_mb: int = Field(
        default=8_192,
        description="VRAM totale RTX 4000 (8 GB = 8192 MB)",
        validation_alias="M2_RTX4000_VRAM_TOTAL_MB",
    )

    # Seuils M3 (BC-250)
    m3_bc250_unified_threshold_mb: int = Field(
        default=14_500,
        description="Seuil alerte BC-250 unified GDDR6 (14.5 GB sur 16 GB)",
        validation_alias="M3_BC250_UNIFIED_THRESHOLD_MB",
    )
    m3_bc250_cpu_load_threshold: float = Field(
        default=0.5,
        description="Seuil alerte charge CPU BC-250 (doit rester ~0 pendant inférence)",
        validation_alias="M3_BC250_CPU_LOAD_THRESHOLD",
    )
    m3_bc250_cpu_idle_timeout_seconds: int = Field(
        default=30,
        description="Timeout avant retry assert_bc250_cpu_idle()",
        validation_alias="M3_BC250_CPU_IDLE_TIMEOUT_SECONDS",
    )

    # Glances BC-250
    glances_m3_url: HttpUrl = Field(  # type: ignore[assignment]
        default="http://10.10.0.3:61208",
        description="Glances web API BC-250 (M3, Debian 12, port 61208)",
        validation_alias="GLANCES_M3_URL",
    )


class LoggingSettings(BaseSettings):
    """Logging & Observabilité."""

    model_config = _section_config()

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


class MtlSSettings(BaseSettings):
    """mTLS / Sécurité interne (Phase 0.13)."""

    model_config = _section_config(env_prefix="MTLS_")

    enabled: bool = Field(
        default=False,
        description="Activer mTLS pour communications inter-services (certs pfSense CA)",
    )
    ca_path: Path | None = Field(default=None)
    cert_path: Path | None = Field(default=None)
    key_path: Path | None = Field(default=None)


class RagSettings(BaseSettings):
    """Paramètres pipeline RAG."""

    model_config = _section_config()

    chunk_size: int = Field(default=1024, validation_alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=128, validation_alias="CHUNK_OVERLAP")
    top_k_retrieval: int = Field(default=20, validation_alias="TOP_K_RETRIEVAL")
    top_k_rerank: int = Field(default=8, validation_alias="TOP_K_RERANK")
    evaluation_enabled: bool = Field(
        default=False,
        description=(
            "Boucle d'évaluation multi-agents (Judge → Advocate → Evaluator) — "
            "défaut OFF en pré-déploiement (aucun LLM pullé, latence 4 appels LLM/requête). "
            "Décision D12 : activation optionnelle par requête/endpoint."
        ),
        validation_alias="EVALUATION_ENABLED",
    )
    semantic_cache_enabled: bool = Field(
        default=False,
        description=(
            "Cache sémantique Redis (R5) — OFF par défaut : aucune latence ajoutée "
            "tant que la fonctionnalité n'est pas validée sur cluster."
        ),
        validation_alias="SEMANTIC_CACHE_ENABLED",
    )
    semantic_cache_threshold: float = Field(
        default=0.95,
        description="Seuil de similarité cosinus (embedding) pour servir le cache.",
        validation_alias="SEMANTIC_CACHE_THRESHOLD",
    )
    semantic_cache_ttl_seconds: int = Field(
        default=3600,
        description="Durée de vie d'une entrée du cache sémantique.",
        validation_alias="SEMANTIC_CACHE_TTL_SECONDS",
    )


class Bc250Settings(BaseSettings):
    """BC-250 Baremetal (Machine 3 — Vulkan ONLY)."""

    model_config = _section_config(env_prefix="BC250_")

    enabled: bool = Field(
        default=True,
        description="BC-250 présent et configuré dans le cluster",
    )
    cu_count: int = Field(
        default=24,
        ge=24,
        le=40,
        description="Compute Units actifs (24 stock, 40 via unlock patch duggasco)",
    )
    cpu_cores_unlocked: bool = Field(
        default=False,
        description=(
            "CPU core unlock appliqué (8c/16t via service systemd bc250-core-unlock.service "
            "au boot, PAS BIOS persistant — SMU msg 0x98 volatil, cold boot = relance)"
        ),
    )
    vram_gib: int = Field(
        default=16,
        ge=8,
        description="VRAM GDDR6 unifiée en GiB (cpu+gpu même pool)",
    )
    tdp_watts: int = Field(
        default=235,
        description="TDP max watts (cpu+gpu combiné, format compact)",
    )
    vulkan_mesa_version: str = Field(
        default="25.1.3",
        description="Version minimum Mesa/RADV (Debian Experimental, pin-priority 500)",
    )
    kernel_version: str = Field(
        default="6.18.18",
        description="Version noyau cible (pin apt-mark hold, éviter 6.15/6.17 buggés)",
    )
    grub_cmdline: str = Field(
        default="amdgpu.gttsize=14750 ttm.pages_limit=3959290 ttm.page_pool_size=3959290",
        description="Paramètres GRUB obligatoires (triplet VRAM — jamais amd_iommu=on)",
    )
    ttm_pages_limit: int = Field(
        default=3959290,
        description="ttm.pages_limit sysfs (plafond mémoire GPU, ~15 GiB)",
    )
    ttm_page_pool_size: int = Field(
        default=3959290,
        description="ttm.page_pool_size (identique à pages_limit)",
    )
    gov_freq_mhz: int = Field(
        default=1500,
        description="Fréquence GPU max MHz (safe-point governor pour usage soutenu)",
    )
    gov_voltage_mv: int = Field(
        default=900,
        description="Voltage GPU mV (safe-point governor)",
    )
    gov_config_path: str = Field(
        default="/etc/cyan-skillfish-governor-smu/config.toml",
        description="Chemin absolu config cyan-skillfish-governor-smu",
    )
    setup_dir: str = Field(
        default="infrastructure/bc250",
        description="Chemin relatif (depuis racine projet) vers scripts BC-250",
    )

    # ── Helpers ────────────────────────────────
    @property
    def cu_unlock_script(self) -> str:
        return f"{self.setup_dir}/enable-40cu-unlock.sh"

    @property
    def core_unlock_script(self) -> str:
        return f"{self.setup_dir}/enable-cpu-core-unlock.sh"

    @property
    def vulkan_setup_script(self) -> str:
        return f"{self.setup_dir}/setup-vulkan-stack.sh"

    @property
    def grub_cmdline_inject(self) -> str:
        """Triplet GRUB prêt pour GRUB_CMDLINE_LINUX_DEFAULT."""
        return self.grub_cmdline

    @property
    def ollama_systemd_override(self) -> dict[str, str]:
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

    def healthcheck_cmds(self) -> list[str]:
        """Commandes de vérification post-reboot BC-250."""
        cmds = []
        if self.cu_count > 24:
            cmds.append("sudo dmesg | grep active_cu_number")
            cmds.append("RADV_DEBUG=info vulkaninfo --summary 2>&1 | grep num_cu")
        if self.cpu_cores_unlocked:
            cmds.append("lscpu | grep -E 'CPU\\(s\\)|Core\\(s\\) per socket'")
            cmds.append("sudo dmesg | grep -E 'smp|lapic' | tail -5")
        cmds.extend(
            [
                f"cat /sys/module/ttm/parameters/pages_limit  # expect {self.ttm_pages_limit}",
                "vulkaninfo --summary 2>&1 | grep deviceName",
            ]
        )
        return cmds


class OkfSettings(BaseSettings):
    """OKF (Open Knowledge Format) v0.2."""

    model_config = _section_config(env_prefix="OKF_")

    stale_after_days: int = Field(
        default=180,
        description="Jours avant qu'une page wiki soit marquée stale (frontmatter stale_after)",
    )
    trust_tiers: list[str] = Field(
        default=["unverified", "machine-confirmed", "human-reviewed"],
        description="Tiers de confiance OKF pour champ verified.status",
    )


class DashboardSettings(BaseSettings):
    """Dashboard CTOS (frontend single-page chat + monitoring)."""

    model_config = _section_config(env_prefix="DASHBOARD_")

    enabled: bool = Field(
        default=True,
        description="Active le dashboard web (GET /, partials, /api/v1/monitoring)",
    )
    refresh_sec: int = Field(
        default=10,
        ge=2,
        description="Intervalle de rafraîchissement du panneau monitoring (s)",
    )
    semi_light: bool = Field(
        default=False,
        description="Thème semi-éclairé par défaut (toggle UI sinon)",
    )


class ChatSettings(BaseSettings):
    """Contexte chat (fenêtre glissante anti lost-in-the-middle)."""

    model_config = _section_config(env_prefix="CHAT_")

    history_max: int = Field(
        default=10,
        ge=2,
        le=50,
        description="Nombre max de messages (paires user/assistant) gardés en contexte chat",
    )


# ──────────────────────────────────────────────
# Settings racine (composition)
# ──────────────────────────────────────────────


class Settings(BaseSettings):
    """Configuration globale du cluster RAG multi-agents.

    Réglages transverses conservés à plat : soit parce que les tests les
    patchent directement (`src.api.main.settings.X`), soit parce que le
    validateur production et les kwargs `Settings(POSTGRES_PASSWORD=...)`
    l'exigent (bloc PostgreSQL).
    """

    model_config = _section_config()

    # ── Environnement d'exécution ──────────────
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        validation_alias="ENVIRONMENT",
    )

    # ── Sections composées ─────────────────────
    api: ApiSettings = Field(default_factory=ApiSettings)
    vault: VaultSettings = Field(default_factory=VaultSettings)
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    models: ModelsSettings = Field(default_factory=ModelsSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    relay: RelaySettings = Field(default_factory=RelaySettings)
    ssh: SSHSettings = Field(default_factory=SSHSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    mtls: MtlSSettings = Field(default_factory=MtlSSettings)
    rag: RagSettings = Field(default_factory=RagSettings)
    bc250: Bc250Settings = Field(default_factory=Bc250Settings)
    okf: OkfSettings = Field(default_factory=OkfSettings)
    dashboard: DashboardSettings = Field(default_factory=DashboardSettings)
    chat: ChatSettings = Field(default_factory=ChatSettings)

    # ── PostgreSQL (conversations, feedback, mémoire long-terme) ──
    postgres_host: str = Field(default="10.10.0.1", validation_alias="POSTGRES_HOST")
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

    # ── Réglages transverses (patchables par les tests) ──────────
    memory_manager_enabled: bool = Field(
        default=True,
        description="Activer MemoryManager pour monitoring cluster",
        validation_alias="MEMORY_MANAGER_ENABLED",
    )

    similarity_threshold: float = Field(
        default=0.7,
        description="Seuil de similarité minimal (retrieval + rerank)",
        validation_alias="SIMILARITY_THRESHOLD",
    )

    monitoring_offline: bool = Field(
        default=False,
        description="Prédéploiement : monitoring sans sonde réseau (cartes n/a immédiates)",
        validation_alias="MONITORING_OFFLINE",
    )

    chat_max_context_chars: int = Field(
        default=12000,
        ge=2000,
        description="Plafond de caractères du contexte envoyé au LLM (anti lost-in-the-middle)",
        validation_alias="CHAT_MAX_CONTEXT_CHARS",
    )

    # ── Helpers ────────────────────────────────
    @property
    def api_prefix(self) -> str:
        return f"/api/{self.api.api_version}"

    @property
    def embedding_endpoint(self) -> str:
        host_url = self.ollama.m1_url if self.models.embedding_host == "m1" else self.ollama.m2_url
        return f"{host_url}/api/embed"

    @property
    def generator_endpoint(self) -> str:
        return f"{self.ollama.m3_url}/api/generate"

    @property
    def rerank_endpoint(self) -> str:
        return f"{self.ollama.m2_url}/api/rerank"

    @property
    def judge_endpoint(self) -> str:
        return f"{self.ollama.m2_url}/api/generate"

    @property
    def advocate_endpoint(self) -> str:
        return f"{self.ollama.m2_url}/api/generate"

    @property
    def evaluator_endpoint(self) -> str:
        return f"{self.ollama.m1_url}/api/generate"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ── Façade de compatibilité (accès plats) ─────────────────────

    def _sections(self) -> Iterator[tuple[str, BaseSettings]]:
        """Itère (nom, section) les sections composées instanciées."""
        for field_name in type(self).model_fields:
            try:
                section = object.__getattribute__(self, field_name)
            except AttributeError:
                continue
            if isinstance(section, BaseSettings):
                yield field_name, section

    def _resolve_flat(self, name: str) -> Any:
        """Retrouve un champ plat (ex. `ollama_m1_url`) dans les sections."""
        for section_name, section in self._sections():
            if name in type(section).model_fields:
                return getattr(section, name)
            if name.startswith(f"{section_name}_"):
                field = name[len(section_name) + 1 :]
                if field in type(section).model_fields:
                    return getattr(section, field)
        raise AttributeError(name)

    def __getattr__(self, name: str) -> Any:
        """Délègue les accès plats (ex. settings.ollama_m1_url) aux sections."""
        if name.startswith("_"):
            raise AttributeError(name)
        return self._resolve_flat(name)

    def __setattr__(self, name: str, value: Any) -> None:
        """Délègue les écritures plates (ex. tests patchant _settings.X) aux sections."""
        if name.startswith("_") or name in type(self).model_fields:
            return super().__setattr__(name, value)
        for section_name, section in self._sections():
            if name in type(section).model_fields:
                return setattr(section, name, value)
            if name.startswith(f"{section_name}_"):
                field = name[len(section_name) + 1 :]
                if field in type(section).model_fields:
                    return setattr(section, field, value)
        return super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        """Délègue les suppressions plates (ex. `patch.object` à la sortie)."""
        if name.startswith("_") or name in type(self).model_fields:
            return super().__delattr__(name)
        for section_name, section in self._sections():
            if name in type(section).model_fields:
                return delattr(section, name)
            if name.startswith(f"{section_name}_"):
                field = name[len(section_name) + 1 :]
                if field in type(section).model_fields:
                    return delattr(section, field)
        return super().__delattr__(name)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Instance singleton de la configuration (cache LRU)."""
    return Settings()


settings = get_settings()
