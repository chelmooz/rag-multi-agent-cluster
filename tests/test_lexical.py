"""Tests LexicalSearch — encodage sparse BM25 (aucune dépendance réseau)."""
import math

import pytest
from qdrant_client.http import models as qmodels

from src.services.lexical import LexicalSearch, LexicalSearchError


@pytest.fixture
def lexical() -> LexicalSearch:
    return LexicalSearch()


class TestEncode:
    def test_encode_returns_sparse_vector(self, lexical: LexicalSearch) -> None:
        vec = lexical.encode("hello world")
        assert isinstance(vec, qmodels.SparseVector)
        assert vec.indices
        assert vec.values
        assert len(vec.indices) == len(vec.values)

    def test_encode_normalized_l2(self, lexical: LexicalSearch) -> None:
        vec = lexical.encode("un test avec plusieurs mots répétés répétés")
        norm = math.sqrt(sum(v * v for v in vec.values))
        assert norm == pytest.approx(1.0, abs=1e-6)

    def test_encode_case_insensitive(self, lexical: LexicalSearch) -> None:
        v1 = lexical.encode("HELLO WORLD")
        v2 = lexical.encode("hello world")
        assert v1.indices == v2.indices
        assert v1.values == v2.values

    def test_encode_repeated_token_normalized(self, lexical: LexicalSearch) -> None:
        v = lexical.encode("test test test")
        norm = math.sqrt(sum(x * x for x in v.values))
        assert norm == pytest.approx(1.0, abs=1e-6)

    def test_encode_respects_sparse_dim(self) -> None:
        lx = LexicalSearch(sparse_dim=128)
        vec = lx.encode("a b c d")
        assert all(i < 128 for i in vec.indices)

    def test_encode_empty_text(self, lexical: LexicalSearch) -> None:
        vec = lexical.encode("")
        assert vec.indices == []
        assert vec.values == []

    def test_encode_batch(self, lexical: LexicalSearch) -> None:
        vecs = lexical.encode_batch(["un", "deux", "trois"])
        assert len(vecs) == 3
        assert all(isinstance(v, qmodels.SparseVector) for v in vecs)

    def test_encode_batch_empty(self, lexical: LexicalSearch) -> None:
        assert lexical.encode_batch([]) == []

    def test_encode_to_dict(self, lexical: LexicalSearch) -> None:
        d = lexical.encode_to_dict("hello world")
        assert isinstance(d, dict)
        assert all(isinstance(k, int) and isinstance(v, float) for k, v in d.items())

    def test_encode_to_dict_normalized(self, lexical: LexicalSearch) -> None:
        d = lexical.encode_to_dict("mots mots mots répétés")
        norm = math.sqrt(sum(v * v for v in d.values()))
        assert norm == pytest.approx(1.0, abs=1e-6)

    def test_encode_batch_to_dict(self, lexical: LexicalSearch) -> None:
        result = lexical.encode_batch_to_dict(["un", "deux"])
        assert len(result) == 2
        assert all(isinstance(d, dict) for d in result)

    def test_sparse_dim_property(self, lexical: LexicalSearch) -> None:
        assert lexical.sparse_dim == 100000

    def test_sparse_dim_custom(self) -> None:
        assert LexicalSearch(sparse_dim=42).sparse_dim == 42


class TestMergeSparseVectors:
    def test_merge_empty_returns_empty(self, lexical: LexicalSearch) -> None:
        vec = lexical.merge_sparse_vectors([])
        assert vec.indices == []
        assert vec.values == []

    def test_merge_single(self, lexical: LexicalSearch) -> None:
        v = qmodels.SparseVector(indices=[1, 2], values=[0.5, 0.5])
        merged = lexical.merge_sparse_vectors([v])
        assert merged.indices == [1, 2]
        norm = math.sqrt(sum(x * x for x in merged.values))
        assert norm == pytest.approx(1.0, abs=1e-6)

    def test_merge_two_vectors_renormalized(self, lexical: LexicalSearch) -> None:
        v1 = qmodels.SparseVector(indices=[1], values=[1.0])
        v2 = qmodels.SparseVector(indices=[1], values=[1.0])
        merged = lexical.merge_sparse_vectors([v1, v2])
        norm = math.sqrt(sum(x * x for x in merged.values))
        assert norm == pytest.approx(1.0, abs=1e-6)

    def test_merge_with_weights(self, lexical: LexicalSearch) -> None:
        v1 = qmodels.SparseVector(indices=[1], values=[1.0])
        v2 = qmodels.SparseVector(indices=[2], values=[1.0])
        merged = lexical.merge_sparse_vectors([v1, v2], weights=[2.0, 1.0])
        assert merged.indices == [1, 2]
        assert merged.values[0] > merged.values[1]

    def test_merge_disjoint_indices(self, lexical: LexicalSearch) -> None:
        v1 = qmodels.SparseVector(indices=[1, 2], values=[0.3, 0.7])
        v2 = qmodels.SparseVector(indices=[3, 4], values=[0.4, 0.6])
        merged = lexical.merge_sparse_vectors([v1, v2])
        assert sorted(merged.indices) == [1, 2, 3, 4]


class TestFromSettings:
    def test_from_settings_returns_instance(self) -> None:
        lx = LexicalSearch.from_settings()
        assert isinstance(lx, LexicalSearch)


class TestErrorClass:
    def test_lexical_search_error_raises(self) -> None:
        with pytest.raises(LexicalSearchError):
            raise LexicalSearchError("boom")
