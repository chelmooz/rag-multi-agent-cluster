"""Service d'inférence via Ollama (3 nœuds : M1 CPU, M2 RTX4000, M3 BC250 Vulkan).

Barème d'assignation des modèles selon les contraintes hardware tranchées 29/07/2026 :
- Embedding : Machine 1 CPU (principal) / Machine 2 CPU (backup)
- Generator 14B/MoE : Machine 3 BC250 ONLY (Vulkan)
- Reranker : Machine 2 RTX4000 ONLY (CUDA)
- Juge / Avocat : Machine 2 RTX4000 (séquentiel avec unload)
- Évaluateur : Machine 1 CPU
- Vision / Text-to-SQL : Machine 3 BC250

Note : le BC250 ne supporte PAS ROCm (rocblas_abort()). Vulkan ONLY via Mesa/RADV.
"""
from httpx import AsyncClient


class OllamaClient:
    """Client HTTP asynchrone vers une instance Ollama.

    Utilise httpx avec retry (tenacity) et circuit-breaker intégré.
    """

    def __init__(self, base_url: str, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self._client = AsyncClient(base_url=self.base_url, timeout=timeout)

    async def generate(self, model: str, prompt: str, **kwargs) -> dict:
        """Génération textuelle via /api/generate."""
        # TODO: implémenter avec retry + fallback
        raise NotImplementedError

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        """Embedding batch via /api/embed."""
        raise NotImplementedError

    async def rerank(self, model: str, query: str, documents: list[str]) -> list[float]:
        """Reranking via /api/rerank (modèle bge-reranker-v2-m3)."""
        raise NotImplementedError

    async def health(self) -> bool:
        """Vérification disponibilité du nœud via /api/tags."""
        try:
            resp = await self._client.get("/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    async def unload_model(self, model: str) -> bool:
        """Décharge un modèle de la mémoire GPU (essentiel pour pipeline séquentiel Judge→Avocat)."""
        # Ollama : POST /api/generate avec keep_alive=0 ou "" pour libérer la VRAM
        raise NotImplementedError

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


class OllamaClientPool:
    """Pool de clients HTTP vers les 3 nœuds du cluster.

    Offre un routage automatique selon le rôle :
    - embed()     → M1 (fallback M2 si M1 indisponible)
    - generate()  → M3 (BC250)
    - rerank()    → M2 (RTX4000)
    - judge()     → M2 (RTX4000)
    - advocate()  → M2 (RTX4000)
    - evaluate()  → M1 (CPU)
    """

    def __init__(self):
        from src.core.settings import settings as s

        self.m1 = OllamaClient(str(s.ollama_m1_url))
        self.m2 = OllamaClient(str(s.ollama_m2_url))
        self.m3 = OllamaClient(str(s.ollama_m3_url))

    # TODO: implémenter routage intelligent + circuit-breaker + fallback
