"""Tests du cache sémantique (R5.3) — stub storage dict, aucun Redis réel."""

import hashlib
import json

import pytest

from src.services.semantic_cache import SemanticCache, cosine_similarity


class FakeRedis:
    """Stub minimal de redis.asyncio : dict en mémoire (scan_iter/get/set)."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def scan_iter(self, match: str = "*") -> object:
        for key in list(self._store):
            if key.startswith(match.replace("*", "")):
                yield key

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value

    async def aclose(self) -> None:
        pass


def _static_embed(values: dict[str, list[float]]) -> object:
    async def embed(query: str) -> list[float] | None:
        return values.get(query)
    return embed


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def vectors() -> dict[str, list[float]]:
    return {
        "question sur les backups": [1.0, 0.0, 0.0],
        "question proche des backups": [0.99, 0.05, 0.0],
        "question autre sujet": [0.0, 0.0, 1.0],
    }


class TestCosineSimilarity:
    def test_identical(self) -> None:
        assert cosine_similarity([1.0, 2.0], [1.0, 2.0]) == pytest.approx(1.0)

    def test_orthogonal(self) -> None:
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_empty_vector_returns_zero(self) -> None:
        assert cosine_similarity([], [1.0, 0.0]) == 0.0

    def test_zero_norm_returns_zero(self) -> None:
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


class TestDisabledByDefault:
    async def test_get_is_noop_when_disabled(self, fake_redis: FakeRedis) -> None:
        cache = SemanticCache(embed=lambda q: None, redis=fake_redis)  # type: ignore[arg-type]
        assert await cache.get("question") is None
        assert fake_redis._store == {}

    async def test_put_is_noop_when_disabled(self, fake_redis: FakeRedis) -> None:
        cache = SemanticCache(embed=lambda q: None, redis=fake_redis)  # type: ignore[arg-type]
        await cache.put("question", "réponse")
        assert fake_redis._store == {}

    async def test_no_redis_means_noop(self) -> None:
        cache = SemanticCache(embed=lambda q: None, enabled=True)
        assert await cache.get("q") is None
        await cache.put("q", "a")


class TestCacheHitAndMiss:
    async def test_put_then_get_returns_entry(
        self, fake_redis: FakeRedis, vectors: dict[str, list[float]]
    ) -> None:
        cache = SemanticCache(
            embed=_static_embed(vectors),
            redis=fake_redis,  # type: ignore[arg-type]
            enabled=True,
            threshold=0.95,
        )
        await cache.put("question sur les backups", "réponse A", confidence=0.8, sources=["s1"])
        hit = await cache.get("question sur les backups")
        assert hit is not None
        assert hit["answer"] == "réponse A"
        assert hit["confidence"] == 0.8
        assert hit["sources"] == ["s1"]
        assert hit["similarity"] == pytest.approx(1.0)

    async def test_similar_question_hits_above_threshold(
        self, fake_redis: FakeRedis, vectors: dict[str, list[float]]
    ) -> None:
        cache = SemanticCache(
            embed=_static_embed(vectors),
            redis=fake_redis,  # type: ignore[arg-type]
            enabled=True,
            threshold=0.95,
        )
        await cache.put("question sur les backups", "réponse A")
        hit = await cache.get("question proche des backups")
        assert hit is not None
        assert hit["answer"] == "réponse A"

    async def test_different_question_misses(
        self, fake_redis: FakeRedis, vectors: dict[str, list[float]]
    ) -> None:
        cache = SemanticCache(
            embed=_static_embed(vectors),
            redis=fake_redis,  # type: ignore[arg-type]
            enabled=True,
            threshold=0.95,
        )
        await cache.put("question sur les backups", "réponse A")
        assert await cache.get("question autre sujet") is None

    async def test_threshold_strict(self, fake_redis: FakeRedis) -> None:
        cache = SemanticCache(
            embed=_static_embed(
                {"q1": [1.0, 0.0], "q2": [0.9, 0.3]}
            ),
            redis=fake_redis,  # type: ignore[arg-type]
            enabled=True,
            threshold=0.99,
        )
        await cache.put("q1", "A")
        assert await cache.get("q2") is None

    async def test_corrupted_entry_ignored(self, fake_redis: FakeRedis) -> None:
        fake_redis._store["rag:cache:garbage"] = "not json"
        cache = SemanticCache(
            embed=_static_embed({"q": [1.0, 0.0]}),
            redis=fake_redis,  # type: ignore[arg-type]
            enabled=True,
            threshold=0.9,
        )
        assert await cache.get("q") is None


class TestStorageFormat:
    async def test_key_is_sha256_of_embedding(self, fake_redis: FakeRedis) -> None:
        cache = SemanticCache(
            embed=_static_embed({"q": [1.0, 2.0]}),
            redis=fake_redis,  # type: ignore[arg-type]
            enabled=True,
        )
        await cache.put("q", "A")
        expected = "rag:cache:" + hashlib.sha256(b"[1.0, 2.0]").hexdigest()[:16]
        assert list(fake_redis._store) == [expected]

    async def test_reput_overwrites_same_key(self, fake_redis: FakeRedis) -> None:
        cache = SemanticCache(
            embed=_static_embed({"q": [1.0, 0.0]}),
            redis=fake_redis,  # type: ignore[arg-type]
            enabled=True,
        )
        await cache.put("q", "A")
        await cache.put("q", "B")
        assert len(fake_redis._store) == 1

    async def test_entry_is_json_with_metadata(self, fake_redis: FakeRedis) -> None:
        cache = SemanticCache(
            embed=_static_embed({"q": [1.0, 0.0]}),
            redis=fake_redis,  # type: ignore[arg-type]
            enabled=True,
        )
        await cache.put("q", "A", confidence=0.5, sources=["s"])
        raw = next(iter(fake_redis._store.values()))
        entry = json.loads(raw)
        assert entry["query"] == "q"
        assert entry["answer"] == "A"
        assert entry["confidence"] == 0.5
        assert entry["sources"] == ["s"]
        assert "created_at" in entry

    async def test_close_closes_redis(self, fake_redis: FakeRedis) -> None:
        cache = SemanticCache(
            embed=_static_embed({"q": [1.0, 0.0]}),
            redis=fake_redis,  # type: ignore[arg-type]
            enabled=True,
        )
        await cache.close()
