"""Tests PdfOcrSidecar — moteur OCR injecté via OcrEngineProtocol (§5.6).

Pas de CUDA/transformers requis : le moteur est mocké avec ``spec``,
validant que ``_process_pdf``/_write_vault_note`` fonctionnent réellement.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.services.ocr_engine_protocol import OcrEngineProtocol
from src.services.ocr_sidecar import PdfOcrSidecar


@pytest.fixture
def fake_engine() -> MagicMock:
    engine: OcrEngineProtocol = MagicMock(spec=OcrEngineProtocol)
    engine.ocr_pdf = MagicMock(return_value="# Test PDF\n\nContenu OCR factice")
    return engine  # type: ignore[return-value]


@pytest.fixture
def sidecar(tmp_path: Path, fake_engine: MagicMock) -> PdfOcrSidecar:
    return PdfOcrSidecar(ocr_engine=fake_engine)


class TestOcrEngineProtocol:
    """PdfOcrSidecar implémente OcrEngineProtocol par défaut."""

    def test_self_is_engine_by_default(self) -> None:
        """Sans injection, _ocr_engine == self → PdfOcrSidecar implémente le Protocol."""
        s = PdfOcrSidecar()
        assert s._ocr_engine is s
        assert isinstance(s, OcrEngineProtocol)


class TestWriteVaultNote:
    """Tests réels de _write_vault_note (pas de CUDA)."""

    def test_writes_note_with_frontmatter(self, sidecar: PdfOcrSidecar, tmp_path: Path) -> None:
        """Note markdown créée avec frontmatter type:source."""
        pdf_path = tmp_path / "rapport.pdf"
        body = "# Rapport\n\nSection 1"

        note_path = sidecar._write_vault_note(pdf_path, body)

        content = note_path.read_text(encoding="utf-8")
        assert "---\n" in content
        assert "type: source\n" in content
        assert "source_kind: pdf\n" in content
        assert "rapport.md" in str(note_path)
        assert content.endswith("Section 1\n")
        assert "ingested_by: ocr_sidecar" in content

    def test_slug_normalizes_spaces(self, sidecar: PdfOcrSidecar, tmp_path: Path) -> None:
        """Stem avec espaces → slug en minuscules avec tirets."""
        pdf_path = tmp_path / "Mon Rapport.pdf"
        note_path = sidecar._write_vault_note(pdf_path, "x")
        assert note_path.name == "mon-rapport.md"
