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
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential


class OllamaError(Exception):
    """Erreur générique d'appel Ollama."""


class OllamaUnavailableError(OllamaError):
    """Nœud Ollama injoignable."""


class OllamaTimeoutError(OllamaError):
    """Timeout sur un appel Ollama."""


class CircuitBreakerOpenError(OllamaError):
    """Circuit breaker ouvert — appels bloqués temporairement."""


class OllamaHTTPError(OllamaError):
    """Erreur HTTP retournée par l'API Ollama."""


@dataclass
class CircuitBreakerState:
    failures: int = 0
    max_failures: int = 3
    open_until: float = 0.0
    cooldown: float = 30.0

    def record_failure(self) -> None:
        import time
        self.failures += 1
        if self.failures >= self.max_failures:
            self.open_until = time.time() + self.cooldown

    def record_success(self) -> None:
        self.failures = 0
        self.open_until = 0.0

    @property
    def is_open(self) -> bool:
        import time
        return time.time() < self.open_until

    def reset(self) -> None:
        self.failures = 0
        self.open_until = 0.0


class OllamaClient:
    """Client HTTP asynchrone vers une instance Ollama.

    Utilise httpx avec retry (tenacity) et circuit-breaker intégré.
    """

    def __init__(self, base_url: str, timeout: int = 120, max_retries: int = 2):
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)
        self._cb = CircuitBreakerState()

    # ── Appels Ollama ────────────────────────────────────────────

    async def generate(
        self, model: str, prompt: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Génération textuelle via /api/generate.

        Supporte : keep_alive, options (temperature, top_p, etc.), stream=False natif.
        Retourne la réponse JSON complète d'Ollama.
        """
        payload: dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
        payload.update(kwargs)
        data = await self._request("POST", "/api/generate", json=payload)
        return data

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        """Embedding batch via /api/embed.

        Retourne une liste de vecteurs [dim] pour chaque texte.
        """
        payload = {"model": model, "input": texts}
        data = await self._request("POST", "/api/embed", json=payload)
        # Ollama /api/embed retourne {"model":..., "embeddings": [[...], ...]}
        embeddings: list[list[float]] = data.get("embeddings", [])
        return embeddings

    async def rerank(self, model: str, query: str, documents: list[str]) -> list[float]:
        """Reranking via /api/rerank (modèle bge-reranker-v2-m3).

        Retourne les scores de pertinence dans l'ordre des documents.
        """
        payload = {
            "model": model,
            "query": query,
            "documents": documents,
        }
        data = await self._request("POST", "/api/rerank", json=payload)
        # Ollama /api/rerank retourne {"model":..., "results": [{"index":0,"score":0.95}, ...]}
        results = data.get("results", [])
        scores = [0.0] * len(documents)
        for r in results:
            idx = r.get("index", 0)
            scores[idx] = r.get("score", 0.0)
        return scores

    async def health(self) -> bool:
        """Vérification disponibilité du nœud via /api/tags."""
        try:
            resp = await self._client.get("/api/tags", timeout=5.0)
        except Exception:
            return False
        else:
            return resp.status_code == 200

    async def unload_model(self, model: str) -> bool:
        """Décharge un modèle de la mémoire GPU (essentiel pour pipeline Judge→Avocat).

        POST /api/generate avec keep_alive=0 force Ollama à libérer la VRAM.
        """
        payload = {"model": model, "prompt": "", "keep_alive": "0s"}
        try:
            data = await self._request("POST", "/api/generate", json=payload)
        except OllamaError:
            return False
        else:
            done: bool = data.get("done", False)
            return done

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> OllamaClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # ── Mécanismes internes : retry + circuit-breaker ─────────────

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Effectue une requête HTTP avec retry et circuit-breaker."""
        import time

        if self._cb.is_open:
            raise CircuitBreakerOpenError(
                f"Circuit breaker ouvert pour {self.base_url} "
                f"(réessai dans {self._cb.open_until - time.time():.0f}s)"
            ) from None

        retrier = AsyncRetrying(
            stop=stop_after_attempt(self._max_retries + 1),
            wait=wait_exponential(multiplier=1, min=1, max=4),
            retry=retry_if_exception_type(
                (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError)
            ),
            reraise=True,
        )

        last_exc: Exception | None = None
        attempt = 0

        async for attempt_state in retrier:
            attempt = attempt_state.attempt_number  # type: ignore[attr-defined]
            try:
                resp = await self._client.request(method, path, **kwargs)
                resp.raise_for_status()
                self._cb.record_success()
                return cast("dict[str, Any]", resp.json())
            except httpx.TimeoutException as e:
                last_exc = OllamaTimeoutError(f"Timeout {method} {path}: {e}")
                raise
            except httpx.HTTPStatusError as e:
                last_exc = OllamaError(
                    f"HTTP {e.response.status_code} {method} {path}: "
                    f"{e.response.text[:500]}"
                )
                self._cb.record_failure()
                raise
            except httpx.RequestError as e:
                last_exc = OllamaUnavailableError(
                    f"Impossible de joindre {self.base_url}: {e}"
                )
                self._cb.record_failure()
                raise

        # Ne devrait jamais arriver grâce à reraise=True + stop_after_attempt
        raise OllamaError(
            f"Échec après {attempt} tentative(s): {last_exc}"
        ) from last_exc

    def reset_circuit_breaker(self) -> None:
        """Réinitialisation manuelle du circuit breaker."""
        self._cb.reset()


class OllamaClientPool:
    """Pool de clients HTTP vers les 3 nœuds du cluster.

    Offre un routage automatique selon le rôle :
    - embed()     → M1 (fallback M2 si M1 indisponible)
    - generate()  → M3 (BC250)
    - rerank()    → M2 (RTX4000)
    - judge()     → M2 (RTX4000)
    - advocate()  → M2 (RTX4000)
    - evaluate()  → M1 (CPU)
    - text2sql()  → M3 (BC250)
    - vision()    → M3 (BC250)
    - fastcheck() → M3 (BC250)
    """

    def __init__(self) -> None:
        from src.core.settings import settings as s

        self.m1 = OllamaClient(str(s.ollama_m1_url))
        self.m2 = OllamaClient(str(s.ollama_m2_url))
        self.m3 = OllamaClient(str(s.ollama_m3_url))
        self._settings = s

    # ── Routage intelligent par rôle ──────────────────────────────

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embedding : M1 principal, fallback M2 si M1 indisponible."""
        model = self._settings.embedding_model
        try:
            return await self.m1.embed(model, texts)
        except (OllamaUnavailableError, OllamaTimeoutError, CircuitBreakerOpenError):
            pass
        if self._settings.embedding_host == "m1":
            return await self.m2.embed(self._settings.embedding_model, texts)
        raise

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Génération : M3 (BC250) uniquement."""
        model = kwargs.pop("model", self._settings.generator_model)
        return await self.m3.generate(model, prompt, **kwargs)

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Reranking : M2 (RTX4000) uniquement."""
        return await self.m2.rerank(self._settings.reranker_model, query, documents)

    async def judge(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Juge : M2 (RTX4000), puis unload."""
        result = await self.m2.generate(self._settings.judge_model, prompt, **kwargs)
        await self.m2.unload_model(self._settings.judge_model)
        return result

    async def advocate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Avocat : M2 (RTX4000), puis unload."""
        result = await self.m2.generate(self._settings.advocate_model, prompt, **kwargs)
        await self.m2.unload_model(self._settings.advocate_model)
        return result

    async def evaluate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Évaluateur : M1 (CPU)."""
        return await self.m1.generate(self._settings.evaluator_model, prompt, **kwargs)

    async def text2sql(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Text-to-SQL : M3 (BC250)."""
        model = kwargs.pop("model", self._settings.text2sql_model)
        return await self.m3.generate(model, prompt, **kwargs)

    async def vision(self, prompt: str, image_base64: str, **kwargs: Any) -> dict[str, Any]:
        """Vision : M3 (BC250) avec image."""
        model = kwargs.pop("model", self._settings.vision_model)
        payload = {
            "model": model,
            "prompt": prompt,
            "images": [image_base64],
            "stream": False,
        }
        payload.update(kwargs)
        return await self.m3._request("POST", "/api/generate", json=payload)

    async def fastcheck(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Fast-check lexical : M3 (BC250)."""
        model = kwargs.pop("model", self._settings.fastcheck_model)
        return await self.m3.generate(model, prompt, **kwargs)

    # ── Health & maintenance ──────────────────────────────────────

    async def health_all(self) -> dict[str, bool]:
        """Vérifie la santé des 3 nœuds en parallèle."""
        import asyncio

        m1, m2, m3 = await asyncio.gather(
            self.m1.health(), self.m2.health(), self.m3.health(),
        )
        return {"m1": m1, "m2": m2, "m3": m3}

    async def close(self) -> None:
        import asyncio
        await asyncio.gather(self.m1.close(), self.m2.close(), self.m3.close())

    def reset_all_circuit_breakers(self) -> None:
        self.m1.reset_circuit_breaker()
        self.m2.reset_circuit_breaker()
        self.m3.reset_circuit_breaker()
