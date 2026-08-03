"""Tests MarkdownChunker — découpe structurelle (aucune dépendance réseau)."""
import pytest

from src.services.ingestion import IngestionService
from src.services.structural_chunker import MarkdownChunker, Section, StructuralChunk


@pytest.fixture
def chunker() -> MarkdownChunker:
    return MarkdownChunker(chunk_size=512, chunk_overlap=64)


class TestParseSections:
    def test_empty_text(self, chunker: MarkdownChunker) -> None:
        assert chunker.parse_sections("") == []
        assert chunker.parse_sections("   \n ") == []

    def test_flat_text_single_section(self, chunker: MarkdownChunker) -> None:
        sections = chunker.parse_sections("un paragraphe\nsans titre")
        assert len(sections) == 1
        assert sections[0].heading_path == []
        assert "un paragraphe" in sections[0].text

    def test_headings_split_sections(self, chunker: MarkdownChunker) -> None:
        md = "# Introduction\ncontenu intro\n## Installation\ncontenu install"
        sections = chunker.parse_sections(md)
        assert len(sections) == 2
        assert sections[0].heading_path == ["Introduction"]
        assert sections[0].heading_level == 1
        assert "contenu intro" in sections[0].text
        assert sections[1].heading_path == ["Introduction", "Installation"]
        assert sections[1].heading_level == 2

    def test_nested_heading_closes_deeper(self, chunker: MarkdownChunker) -> None:
        md = "# A\n## B\n### C\ncontenu c\n## D\ncontenu d"
        sections = chunker.parse_sections(md)
        paths = [s.heading_path for s in sections]
        assert paths == [["A", "B", "C"], ["A", "D"]]

    def test_frontmatter_skipped(self, chunker: MarkdownChunker) -> None:
        md = "---\ntitle: test\nstatus: unverified\n---\n# Vrai titre\ncontenu"
        sections = chunker.parse_sections(md)
        assert len(sections) == 1
        assert sections[0].heading_path == ["Vrai titre"]
        assert "title: test" not in sections[0].text

    def test_code_fence_preserved_whole(self, chunker: MarkdownChunker) -> None:
        md = "# Code\n```python\ndef f():\n    return 1\n```\nfin"
        sections = chunker.parse_sections(md)
        assert len(sections) == 2
        assert "def f():" in sections[0].text

    def test_fence_heading_inside_not_parsed(self, chunker: MarkdownChunker) -> None:
        md = "# A\n```\n# pas un titre\n```\n# B\ncontenu"
        sections = chunker.parse_sections(md)
        paths = [s.heading_path for s in sections]
        assert paths == [["A"], ["B"]]

    def test_table_rows_kept_in_section(self, chunker: MarkdownChunker) -> None:
        md = "# Tableau\n| col1 | col2 |\n|------|------|\n| a    | b    |"
        sections = chunker.parse_sections(md)
        assert len(sections) == 1
        assert "col1" in sections[0].text


class TestChunkSection:
    def test_small_section_single_chunk(self, chunker: MarkdownChunker) -> None:
        section = Section(heading_path=["Intro"], heading_level=1, text="petit contenu")
        chunks = chunker.chunk_section(section)
        assert len(chunks) == 1
        assert chunks[0].text == "petit contenu"
        assert chunks[0].heading_path == ["Intro"]
        assert chunks[0].token_count > 0

    def test_long_section_split_with_prefix(self, chunker: MarkdownChunker) -> None:
        text = "mot " * 2000  # bien au-delà de 512 tokens
        section = Section(heading_path=["Guide", "Install"], heading_level=2, text=text)
        chunks = chunker.chunk_section(section)
        assert len(chunks) > 1
        assert all(c.heading_path == ["Guide", "Install"] for c in chunks)
        assert all(c.text.startswith("[Guide | Install]") for c in chunks)

    def test_split_chunks_cover_all_tokens(self, chunker: MarkdownChunker) -> None:
        text = "phrase unique " * 1000
        section = Section(text=text)
        chunks = chunker.chunk_section(section)
        assert len(chunks) > 1
        assert all(c.token_count <= 512 + 128 for c in chunks)

    def test_empty_section(self, chunker: MarkdownChunker) -> None:
        assert chunker.chunk_section(Section(text="")) == []
        assert chunker.chunk_section(Section(text="  \n ")) == []


class TestChunk:
    def test_full_document_order(self, chunker: MarkdownChunker) -> None:
        md = "# A\ncontenu a\n# B\ncontenu b"
        chunks = chunker.chunk(md)
        assert [c.heading_path for c in chunks] == [["A"], ["B"]]

    def test_returns_structural_chunks(self, chunker: MarkdownChunker) -> None:
        chunks = chunker.chunk("# Titre\ncorps")
        assert isinstance(chunks[0], StructuralChunk)

    def test_overlap_guard(self) -> None:
        with pytest.raises(ValueError, match="chunk_overlap"):
            MarkdownChunker(chunk_size=100, chunk_overlap=100)


class TestIngestionIntegration:
    def test_md_source_uses_structural_chunking(self) -> None:
        svc = IngestionService(chunk_size=512, chunk_overlap=64)
        chunks = svc.chunk_text("# Intro\ncontenu\n# Suite\nautre", "s1", "md")
        assert len(chunks) == 2
        assert chunks[0].metadata["section_title"] == "Intro"
        assert chunks[0].metadata["heading_path"] == ["Intro"]
        assert chunks[1].metadata["section_title"] == "Suite"

    def test_markdown_like_text_auto_detected(self) -> None:
        svc = IngestionService(chunk_size=512, chunk_overlap=64)
        chunks = svc.chunk_text("# Titre\ncorps de texte", "s1", "text")
        assert chunks[0].metadata.get("section_title") == "Titre"

    def test_plain_text_stays_flat(self) -> None:
        svc = IngestionService(chunk_size=512, chunk_overlap=64)
        chunks = svc.chunk_text("juste du texte sans markdown", "s1", "text")
        assert len(chunks) == 1
        assert "section_title" not in chunks[0].metadata
