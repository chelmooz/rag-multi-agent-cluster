"""Point d'entrée CLI / développement du cluster RAG multi-agents.

Usage:
    python -m src.main             # Lance le serveur FastAPI (dev, reload)
    python -m src.api.main         # Lance le serveur FastAPI
"""

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
