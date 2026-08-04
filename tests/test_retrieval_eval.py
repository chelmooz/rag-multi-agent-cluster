"""Tests des métriques retrieval (R4.2) — valeurs calculées à la main."""

import math

from src.services.retrieval_eval import (
    evaluate_retrieval,
    from_search_results,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


class TestPrecisionRecall:
    def test_precision_top_k(self) -> None:
        assert precision_at_k({"a", "b"}, ["a", "c", "b"], k=2) == 0.5

    def test_precision_no_k_uses_all(self) -> None:
        assert precision_at_k({"a"}, ["a", "b"]) == 0.5

    def test_precision_empty_retrieved(self) -> None:
        assert precision_at_k({"a"}, [], k=5) == 0.0

    def test_recall_top_k(self) -> None:
        assert recall_at_k({"a", "b"}, ["a"], k=5) == 0.5

    def test_recall_no_relevant(self) -> None:
        assert recall_at_k(set(), ["a"]) == 0.0

    def test_recall_all_found(self) -> None:
        assert recall_at_k({"a", "b"}, ["b", "a", "c"], k=2) == 1.0


class TestReciprocalRank:
    def test_first_position(self) -> None:
        assert reciprocal_rank({"b"}, ["b", "a"]) == 1.0

    def test_third_position(self) -> None:
        assert reciprocal_rank({"c"}, ["a", "b", "c"]) == 1 / 3

    def test_not_found(self) -> None:
        assert reciprocal_rank({"x"}, ["a", "b"]) == 0.0


class TestNdcg:
    def test_perfect_ranking(self) -> None:
        assert ndcg_at_k({"a", "b"}, ["a", "b", "c"], k=3) == 1.0

    def test_worst_ranking(self) -> None:
        assert ndcg_at_k({"a", "b"}, ["c", "d", "a", "b"], k=2) == 0.0

    def test_partial(self) -> None:
        # DCG = 1 + 1/log2(3) ; IDCG = 1 + 1/log2(3) + 1/log2(4) = 1 + 1/2 + 1/2
        dcg = 1.0 + 1.0 / math.log2(3)
        idcg = 1.0 + 1.0 / math.log2(3) + 1.0 / 2
        assert abs(ndcg_at_k({"a", "b", "c"}, ["a", "b", "x"], k=3) - dcg / idcg) < 1e-9

    def test_empty_relevant(self) -> None:
        assert ndcg_at_k(set(), ["a", "b"]) == 0.0


class TestEvaluate:
    def test_averages_across_cases(self) -> None:
        cases = [({"a"}, ["a", "b"]), ({"x", "y"}, ["y", "a", "x"])]
        out = evaluate_retrieval(cases, ks=(2,))
        assert out["queries"] == 2.0
        assert out["precision@2"] == 0.5  # (1/2 + 1/2) / 2
        assert out["recall@2"] == 0.75  # (1 + 1/2) / 2 (x classé 3e, hors top-2)
        assert out["mrr"] == 1.0  # (1 + 1) / 2
        # cas 1 : ndcg = 1 ; cas 2 : top2=["y","a"] → DCG=1, IDCG=1+1/log2(3)
        idcg2 = 1.0 + 1.0 / math.log2(3)
        assert abs(out["ndcg@2"] - (1.0 + 1.0 / idcg2) / 2) < 1e-9

    def test_empty_dataset(self) -> None:
        out = evaluate_retrieval([])
        assert out == {"queries": 0.0}

    def test_miss_affects_mrr(self) -> None:
        cases = [({"a"}, ["z"]), ({"b"}, ["b"])]
        out = evaluate_retrieval(cases, ks=(1,))
        assert out["mrr"] == 0.5
        assert out["recall@1"] == 0.5


class TestFromSearchResults:
    def test_normalizes_ids_to_strings(self) -> None:
        relevant, retrieved = from_search_results(
            {"relevant": [1, 2], "retrieved": ["1", "3", 2]}
        )
        assert relevant == {"1", "2"}
        assert retrieved == ["1", "3", "2"]

    def test_missing_keys(self) -> None:
        relevant, retrieved = from_search_results({})
        assert relevant == set()
        assert retrieved == []
