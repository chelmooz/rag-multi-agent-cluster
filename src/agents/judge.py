"""Judge Agent — évalue la qualité de la réponse sur Machine 2 RTX 4000.

Modèle : qwen3.5:7b Q4_K_M (~5GB)
Pipeline : séquentiel après Generator, avant Avocat.
           1. Charge qwen3.5:7b
           2. Lit relay.json (réponse du Generator)
           3. Évalue qualité, précision, hallucinations
           4. Écrit judge.score + judge.critique → relay.json
           5. Unload modèle (libère VRAM pour Avocat)
"""


class JudgeAgent:
    """Évalue la qualité de la réponse (score 0.0-1.0 + critique textuelle)."""

    async def evaluate(self, query: str, response: str, context: list[dict]) -> dict:
        raise NotImplementedError

    async def unload(self) -> None:
        """Décharge le modèle de la VRAM RTX 4000 (essentiel pour le pipeline séquentiel)."""
        raise NotImplementedError
