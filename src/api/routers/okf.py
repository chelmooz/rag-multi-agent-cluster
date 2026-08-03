"""Routes OKF (Phase 0.8/B8) + lint du vault (B8/Wiki)."""

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request

from src.agents.wiki_agent import WikiAgent
from src.api.schemas import OkfValidateRequest

router = APIRouter()


def _wiki_agent(app: FastAPI) -> WikiAgent:
    """Retourne le WikiAgent (lazy : injecté par les tests via app.state)."""
    wiki = getattr(app.state, "wiki_agent", None)
    if wiki is None:
        wiki = WikiAgent()
        app.state.wiki_agent = wiki
    return wiki


@router.post("/okf/validate", tags=["OKF"])
async def okf_validate(request: OkfValidateRequest, http_request: Request) -> dict[str, Any]:
    """Valide le frontmatter OKF v0.2 d'une page du vault."""
    try:
        result = await _wiki_agent(http_request.app).validate_frontmatter(request.path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"path": request.path, **result}


@router.get("/okf/list", tags=["OKF"])
async def okf_list(http_request: Request) -> dict[str, Any]:
    """Liste les pages du vault (hors index.md/log.md)."""
    pages = await _wiki_agent(http_request.app).list_pages()
    return {"pages": pages, "count": len(pages)}


@router.get("/okf/show", tags=["OKF"])
async def okf_show(path: str, http_request: Request) -> dict[str, Any]:
    """Affiche une page du vault (frontmatter + contenu markdown)."""
    try:
        return await _wiki_agent(http_request.app).read_page(path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/lint", tags=["Wiki"])
async def lint(http_request: Request) -> dict[str, Any]:
    """Lint du vault : pages orphelines, stale, contradictions, gaps."""
    return await _wiki_agent(http_request.app).lint()
