"""Chunking structurel markdown — frontières de sections, tableaux/fences entiers.

Algorithme ligne-à-ligne (KISS, aucun rendu HTML) :
- Titres ``#``…``######`` = frontières de section (chemin h1 > h2 > h3 conservé)
- Frontmatter YAML (``---`` en tête) ignoré
- Blocs tableau (lignes ``|`` consécutives) et blocs code (````` ``` ````…`````` ``` ````)
  jamais coupés par la découpe token
- Découpe token+overlap uniquement à l'intérieur d'une section ; les sous-chunks
  issus d'une section coupée reçoivent le chemin de section en préfixe (contexte
  de retrieval pour le full-text BM25).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import tiktoken

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")


@dataclass(frozen=True)
class Section:
    """Section markdown délimitée par un titre (ou le début du document)."""

    heading_path: list[str] = field(default_factory=list)
    heading_level: int = 0
    text: str = ""


@dataclass(frozen=True)
class StructuralChunk:
    """Chunk structurel : texte + chemin de section pour les métadonnées."""

    text: str
    heading_path: list[str] = field(default_factory=list)
    heading_level: int = 0
    token_count: int = 0


class MarkdownChunker:
    """Découpe un document markdown en sections puis en chunks token-budgetés."""

    def __init__(
        self,
        chunk_size: int = 1024,
        chunk_overlap: int = 128,
        encoding_name: str = "cl100k_base",
    ) -> None:
        if chunk_overlap >= chunk_size:
            msg = f"chunk_overlap ({chunk_overlap}) doit etre < chunk_size ({chunk_size})"
            raise ValueError(msg)
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._encoding = tiktoken.get_encoding(encoding_name)

    # ── Parsing en sections ─────────────────────────────────────

    def parse_sections(self, text: str) -> list[Section]:
        """Découpe le markdown en sections délimitées par les titres."""
        if not text or not text.strip():
            return []

        lines = text.splitlines()
        path: list[str] = []
        level = 0
        buffer: list[str] = []
        has_body = False
        sections: list[Section] = []

        def flush() -> None:
            nonlocal buffer, has_body
            content = "\n".join(buffer).strip()
            if content:
                sections.append(Section(list(path), level, content))
            buffer = []
            has_body = False

        in_fence = False
        in_table = False
        skip_frontmatter = bool(lines) and lines[0].strip() == "---"

        for idx, raw_line in enumerate(lines):
            line = raw_line.strip()

            # Frontmatter YAML : ignoré (métadonnées, pas du contenu)
            if skip_frontmatter:
                if idx > 0 and line == "---":
                    skip_frontmatter = False
                continue

            # Bloc code : tout est préservé tel quel, jamais découpé
            if line.startswith(("```", "~~~")):
                if in_fence:
                    buffer.append(raw_line)
                    flush()
                    in_fence = False
                else:
                    if has_body:
                        flush()
                    in_fence = True
                    buffer.append(raw_line)
                in_table = False
                continue
            if in_fence:
                buffer.append(raw_line)
                continue

            # Titre : nouvelle section — flush APRÈS mise à jour du chemin
            heading = _HEADING_RE.match(line)
            if heading:
                if has_body:
                    flush()
                new_level = len(heading.group(1))
                title = heading.group(2).strip("`").strip()
                while len(path) >= new_level:
                    path.pop()
                if title:
                    path.append(title)
                level = new_level
                buffer = [raw_line]
                in_table = False
                continue

            # Ligne tableau : bloc entier si consécutif
            is_table_row = _TABLE_ROW_RE.match(line) is not None
            if is_table_row:
                in_table = True
                buffer.append(raw_line)
                has_body = True
                continue
            if in_table:
                flush()
                in_table = False

            buffer.append(raw_line)
            has_body = True

        if in_fence:
            buffer.append("```")
        flush()
        return sections

    # ── Découpe token intra-section ──────────────────────────────

    def chunk_section(self, section: Section) -> list[StructuralChunk]:
        """Découpe une section en chunks token-budgetés avec overlap."""
        if not section.text.strip():
            return []

        tokens = self._encoding.encode(section.text)
        if not tokens:
            return []

        # Section entièrement dans le budget : un seul chunk
        if len(tokens) <= self._chunk_size:
            return [
                StructuralChunk(
                    text=section.text,
                    heading_path=list(section.heading_path),
                    heading_level=section.heading_level,
                    token_count=len(tokens),
                )
            ]

        # Section trop longue : fenêtre glissante, préfixe chemin de section
        path_str = " | ".join(section.heading_path)
        prefix = f"[{path_str}]\n\n" if path_str else ""
        chunks: list[StructuralChunk] = []
        start = 0
        while start < len(tokens):
            end = min(start + self._chunk_size, len(tokens))
            sub_text = self._encoding.decode(tokens[start:end])
            chunks.append(
                StructuralChunk(
                    text=f"{prefix}{sub_text}",
                    heading_path=list(section.heading_path),
                    heading_level=section.heading_level,
                    token_count=len(tokens[start:end]) + len(self._encoding.encode(prefix)),
                )
            )
            if end == len(tokens):
                break
            start += self._chunk_size - self._chunk_overlap
        return chunks

    # ── API publique ─────────────────────────────────────────────

    def chunk(self, text: str) -> list[StructuralChunk]:
        """Découpe un document markdown complet en chunks structurels."""
        chunks: list[StructuralChunk] = []
        for section in self.parse_sections(text):
            chunks.extend(self.chunk_section(section))
        return chunks
