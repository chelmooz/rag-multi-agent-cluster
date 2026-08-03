"""Protocoles d'injection de dépendance pour OCR — test sans GPU CUDA.

Permet de mocker le moteur d'inférence OCR (modèle CUDA ``baidu/Unlimited-OCR``)
via ``spec=OcrEngineProtocol`` au lieu de ``MagicMock`` nu, évitant les
régressions comme R1 (§5.8) où un mock non contraint masquait une API disparue.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class OcrEngineProtocol(Protocol):
    """Interface du moteur OCR consommé par ``PdfOcrSidecar``.

    Contractuellement, seul ``ocr_pdf`` est utilisé par la logique métier
    (``_process_pdf``). La classe concrète ``PdfOcrSidecar`` l'implémente
    via ``_ocr_pdf``.
    """

    def ocr_pdf(self, pdf_path: Path) -> str: ...
