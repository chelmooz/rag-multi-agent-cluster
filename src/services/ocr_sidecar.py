"""Sidecar OCR — PDF -> Markdown -> Vault -> Ingestion (offline, hors chemin critique requête).

Convertit les PDFs déposés dans `raw_data_path` en notes markdown dans le vault
Obsidian (`wiki_vault_path/sources/`), puis les indexe dans Qdrant via
IngestionService — exactement comme n'importe quelle autre note du vault.

Nécessite un GPU CUDA (modèle baidu/Unlimited-OCR, 3B, BF16). Le BC-250 (M3) est
Vulkan-only et ne peut pas l'exécuter : ce sidecar tourne sur M2 (RTX 4000 8 GB),
seul GPU CUDA du cluster. Le modèle est chargé une seule fois par run puis
explicitement déchargé (VRAM libérée) pour ne jamais monopoliser durablement le
GPU partagé avec Reranker/Juge/Avocat.

Deux modes d'exécution :
- CLI batch (cron, ex: fenêtre creuse 02:30 comme le rsync de backup) :
    python -m src.services.ocr_sidecar --once
- Mini-serveur (déclenchement manuel, UI = Swagger auto-généré par FastAPI) :
    python -m src.services.ocr_sidecar --serve --port 8090
    -> http://<M2>:8090/docs, bouton "Try it out" sur POST /run
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.core.settings import get_settings
from src.services.ingestion import IngestionService

logger = logging.getLogger("ocr_sidecar")

_PROCESSED_DIRNAME = "_processed"
_FAILED_DIRNAME = "_failed"
_MODEL_NAME = "baidu/Unlimited-OCR"

_DET_RE = re.compile(r"<\|det\|>([^<\s]+)(?:\s*\[[^\]]*\])?\s*<\|/det\|>(.*)", re.DOTALL)


@dataclass
class OcrSidecarResult:
    """Résumé d'un passage du sidecar (retourné en CLI et via /status)."""
    processed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    chunks_indexed: int = 0


class PdfOcrSidecar:
    """Pipeline PDF -> texte structuré -> note vault -> index Qdrant.

    Le modèle Unlimited-OCR n'est chargé qu'au premier PDF rencontré dans un
    run, et explicitement déchargé (`_unload_model`) une fois le run terminé —
    pas de process long-vivant qui garde la VRAM du RTX 4000 occupée en
    permanence.
    """

    def __init__(self, ingestion_service: IngestionService | None = None) -> None:
        settings = get_settings()
        self._inbox: Path = settings.raw_data_path
        self._vault_sources: Path = settings.wiki_vault_path / "sources"
        self._ingestion = ingestion_service
        self._model = None
        self._tokenizer = None

    # ── Modèle (chargement paresseux, une fois par run) ──────────

    def _load_model(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoModel, AutoTokenizer

        logger.info("Chargement %s sur CUDA (BF16)...", _MODEL_NAME)
        self._tokenizer = AutoTokenizer.from_pretrained(_MODEL_NAME, trust_remote_code=True)
        self._model = (
            AutoModel.from_pretrained(
                _MODEL_NAME,
                trust_remote_code=True,
                use_safetensors=True,
                torch_dtype=torch.bfloat16,
            )
            .eval()
            .cuda()
        )

    def _unload_model(self) -> None:
        """Libère la VRAM en fin de run — ne pas monopoliser le RTX 4000."""
        if self._model is None:
            return
        import gc

        import torch

        self._model = None
        self._tokenizer = None
        gc.collect()
        torch.cuda.empty_cache()

    # ── PDF -> images -> texte ────────────────────────────────────

    def _pdf_to_images(self, pdf_path: Path, dpi: int = 300) -> list[Path]:
        import fitz  # PyMuPDF

        tmp_dir = Path(tempfile.mkdtemp(prefix="ocr_sidecar_"))
        doc = fitz.open(pdf_path)
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        paths: list[Path] = []
        for i, page in enumerate(doc):
            out = tmp_dir / f"page_{i + 1:04d}.png"
            page.get_pixmap(matrix=mat).save(str(out))
            paths.append(out)
        doc.close()
        return paths

    def _ocr_pdf(self, pdf_path: Path) -> str:
        """OCR un PDF entier en un seul passage multi-page."""
        self._load_model()
        image_paths = self._pdf_to_images(pdf_path)
        try:
            raw = self._model.infer_multi(
                self._tokenizer,
                prompt="<image>Multi page parsing.",
                image_files=[str(p) for p in image_paths],
                output_path=None,
                image_size=1024,
                max_length=32768,
                no_repeat_ngram_size=35,
                ngram_window=1024,
                save_results=False,
            )
        finally:
            if image_paths:
                shutil.rmtree(image_paths[0].parent, ignore_errors=True)
        return self._clean_det_tags(raw)

    @staticmethod
    def _clean_det_tags(raw: str) -> str:
        """Retire les balises `<|det|>type [bbox]<|/det|>` de mise en page.

        Regroupe les lignes d'un même bloc, sépare les blocs par une ligne
        vide (cf. post-traitement documenté par le repo officiel).
        """
        blocks: list[list[str]] = []
        current: list[str] | None = None
        for line in raw.splitlines():
            line = line.rstrip()
            if not line:
                continue
            m = _DET_RE.match(line)
            if m:
                category, content = m.group(1).strip(), m.group(2).strip()
                if category == "image":
                    continue
                if current is not None:
                    blocks.append(current)
                current = [content] if content else []
                continue
            if current is None:
                current = []
            current.append(line)
        if current is not None:
            blocks.append(current)
        return "\n\n".join("\n".join(b) for b in blocks).strip()

    # ── Écriture vault ────────────────────────────────────────────

    def _write_vault_note(self, pdf_path: Path, markdown_body: str) -> Path:
        """Écrit une note dans `sources/` avec un frontmatter minimal.

        NOTE : le schéma OKF v0.2 complet n'est pas encore formalisé dans le
        repo (backlog 4.3, encore ouvert) — ce frontmatter reprend les seuls
        champs déjà utilisés ailleurs (`verified.status`, tiers de confiance
        settings.okf_trust_tiers). À aligner une fois 4.3 clos.
        """
        self._vault_sources.mkdir(parents=True, exist_ok=True)
        slug = pdf_path.stem.replace(" ", "-").lower()
        note_path = self._vault_sources / f"{slug}.md"
        now = datetime.now(UTC).isoformat()

        frontmatter = (
            "---\n"
            f'title: "{pdf_path.stem}"\n'
            "type: source\n"
            "source_kind: pdf\n"
            f'source_file: "{pdf_path.name}"\n'
            f"ingested_at: {now}\n"
            "ingested_by: ocr_sidecar\n"
            "ingestion_method: unlimited-ocr\n"
            "verified:\n"
            "  status: machine-confirmed\n"
            "tags: [source, ocr, pdf]\n"
            "---\n\n"
        )
        note_path.write_text(frontmatter + markdown_body + "\n", encoding="utf-8")
        return note_path

    # ── Pipeline complet ──────────────────────────────────────────

    async def run_once(self) -> OcrSidecarResult:
        """Scanne l'inbox, OCRise chaque PDF, écrit la note, indexe, archive."""
        result = OcrSidecarResult()
        if not self._inbox.exists():
            logger.warning("Dossier inbox introuvable: %s", self._inbox)
            return result

        pdfs = sorted(self._inbox.glob("*.pdf"))
        if not pdfs:
            logger.info("Aucun PDF à traiter dans %s", self._inbox)
            return result

        processed_dir = self._inbox / _PROCESSED_DIRNAME
        failed_dir = self._inbox / _FAILED_DIRNAME
        processed_dir.mkdir(exist_ok=True)
        failed_dir.mkdir(exist_ok=True)

        try:
            for pdf_path in pdfs:
                try:
                    logger.info("OCR: %s", pdf_path.name)
                    markdown_body = self._ocr_pdf(pdf_path)
                    if not markdown_body.strip():
                        raise ValueError("Sortie OCR vide")

                    note_path = self._write_vault_note(pdf_path, markdown_body)

                    if self._ingestion is not None:
                        ingest_result = await self._ingestion.ingest(
                            text=markdown_body,
                            source_type="file",
                            source_id=pdf_path.stem,
                            metadata={
                                "source_file": pdf_path.name,
                                "vault_note": str(note_path),
                            },
                        )
                        result.chunks_indexed += ingest_result.chunks_indexed

                    shutil.move(str(pdf_path), str(processed_dir / pdf_path.name))
                    result.processed.append(pdf_path.name)

                except Exception as e:
                    logger.exception("Échec OCR sur %s", pdf_path.name)
                    shutil.move(str(pdf_path), str(failed_dir / pdf_path.name))
                    result.failed.append(f"{pdf_path.name}: {e}")
        finally:
            self._unload_model()

        return result


# ── Mini-serveur (déclenchement manuel via UI Swagger) ───────────

def _build_app():
    from fastapi import BackgroundTasks, FastAPI

    app = FastAPI(
        title="OCR Sidecar",
        description=(
            "Déclenchement manuel du pipeline PDF -> Vault -> Qdrant "
            "(Unlimited-OCR, à faire tourner sur M2 / RTX 4000)."
        ),
        docs_url="/docs",
    )

    state: dict = {"running": False, "last_result": None}

    async def _run_and_store() -> None:
        state["running"] = True
        try:
            async with IngestionService.from_settings() as ingestion:
                sidecar = PdfOcrSidecar(ingestion_service=ingestion)
                state["last_result"] = await sidecar.run_once()
        finally:
            state["running"] = False

    @app.post("/run", tags=["OCR Sidecar"])
    async def run(background_tasks: BackgroundTasks) -> dict:
        """Déclenche un passage (scan inbox -> OCR -> vault -> Qdrant).

        Tâche de fond : répond immédiatement, résultat consultable via
        GET /status une fois terminé.
        """
        if state["running"]:
            return {"status": "already_running"}
        background_tasks.add_task(_run_and_store)
        return {"status": "started"}

    @app.get("/status", tags=["OCR Sidecar"])
    async def status() -> dict:
        result: OcrSidecarResult | None = state["last_result"]
        return {
            "running": state["running"],
            "last_run": None
            if result is None
            else {
                "processed": result.processed,
                "failed": result.failed,
                "chunks_indexed": result.chunks_indexed,
            },
        }

    @app.get("/health", tags=["OCR Sidecar"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


# ── CLI ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Sidecar OCR PDF -> Vault (Unlimited-OCR)")
    parser.add_argument(
        "--once", action="store_true", help="Traite l'inbox une fois et quitte (mode cron)"
    )
    parser.add_argument(
        "--serve", action="store_true", help="Démarre le mini-serveur de déclenchement manuel"
    )
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.once:
        async def _run() -> None:
            async with IngestionService.from_settings() as ingestion:
                sidecar = PdfOcrSidecar(ingestion_service=ingestion)
                result = await sidecar.run_once()
                logger.info(
                    "Terminé: %d traité(s), %d échec(s), %d chunks indexés",
                    len(result.processed),
                    len(result.failed),
                    result.chunks_indexed,
                )

        asyncio.run(_run())
    elif args.serve:
        import uvicorn

        uvicorn.run(_build_app(), host="0.0.0.0", port=args.port)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
