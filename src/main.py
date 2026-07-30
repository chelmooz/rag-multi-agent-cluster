"""Point d'entrée CLI / développement du cluster RAG multi-agents.

Usage:
    python -m src.api.main          # Lance le serveur FastAPI (dev)
    python -m src.core.settings     # Affiche la config résolue
"""
from src.api.main import app

if __name__ == "__main__":
    import uvicorn
    from src.core.settings import get_settings

    settings = get_settings()
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower(),
    )