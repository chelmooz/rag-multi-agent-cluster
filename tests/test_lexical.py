"""Tests LexicalSearch — build_query full-text BM25 natif (aucune dépendance réseau)."""
import pytest

from src.services.lexical import LexicalSearch, LexicalSearchError


@pytest.fixture
def lexical() -> LexicalSearch:
    return LexicalSearch()


class TestBuildQuery:
    def test_returns_query_text(self, lexical: LexicalSearch) -> None:
        q = lexical.build_query("hello world")
        assert q == "hello world"

    def test_empty_returns_none(self, lexical: LexicalSearch) -> None:
        assert lexical.build_query("") is None

    def test_whitespace_returns_none(self, lexical: LexicalSearch) -> None:
        assert lexical.build_query("   ") is None

    def test_strips_whitespace(self, lexical: LexicalSearch) -> None:
        q = lexical.build_query("  hello world  ")
        assert q == "hello world"

    def test_truncates_long_query(self) -> None:
        lx = LexicalSearch(max_query_length=10)
        q = lx.build_query("hello world this is too long")
        assert q == "hello worl"
        assert len(q) == 10

    def test_short_query_untouched(self, lexical: LexicalSearch) -> None:
        q = lexical.build_query("hi")
        assert q == "hi"

    def test_newline_stripped(self, lexical: LexicalSearch) -> None:
        q = lexical.build_query("\nhello\n")
        assert q == "hello"

    def test_special_chars_preserved(self, lexical: LexicalSearch) -> None:
        q = lexical.build_query("c++ vs python 3.12!")
        assert q == "c++ vs python 3.12!"


class TestProperties:
    def test_default_max_query_length(self) -> None:
        assert LexicalSearch().max_query_length == 512

    def test_custom_max_query_length(self) -> None:
        assert LexicalSearch(max_query_length=100).max_query_length == 100


class TestFromSettings:
    def test_from_settings_returns_instance(self) -> None:
        lx = LexicalSearch.from_settings()
        assert isinstance(lx, LexicalSearch)


class TestErrorClass:
    def test_lexical_search_error_raises(self) -> None:
        with pytest.raises(LexicalSearchError):
            raise LexicalSearchError("boom")
