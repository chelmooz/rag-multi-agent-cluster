"""Tests des politiques d'accès retrieval (R6.3)."""

from qdrant_client import models

from src.services.access_policy import NoAuthPolicy, ScopePolicy, build_policy


class TestNoAuthPolicy:
    def test_returns_no_filter(self) -> None:
        assert NoAuthPolicy().build_filter(None, None) is None

    def test_ignores_payload_credentials(self) -> None:
        assert NoAuthPolicy().build_filter("alice", "finance") is None


class TestScopePolicy:
    def test_scope_only(self) -> None:
        f = ScopePolicy().build_filter(None, "finance")
        assert f is not None
        assert f.must is not None
        assert len(f.must) == 1
        cond = f.must[0]
        assert isinstance(cond, models.FieldCondition)
        assert cond.key == "access_scope"
        assert cond.match == models.MatchValue(value="finance")

    def test_user_only(self) -> None:
        f = ScopePolicy().build_filter("alice", None)
        assert f is not None
        assert f.must is not None
        assert f.must[0].key == "owner"

    def test_scope_and_user_combined(self) -> None:
        f = ScopePolicy().build_filter("alice", "finance")
        assert f is not None
        assert f.must is not None
        assert len(f.must) == 2
        assert {c.key for c in f.must} == {"access_scope", "owner"}

    def test_no_credentials_returns_no_filter(self) -> None:
        assert ScopePolicy().build_filter(None, None) is None


class TestBuildPolicy:
    def test_scope_selects_scope_policy(self) -> None:
        assert isinstance(build_policy("finance"), ScopePolicy)

    def test_no_scope_selects_noauth(self) -> None:
        assert isinstance(build_policy(None), NoAuthPolicy)
