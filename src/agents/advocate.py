"""Avocat du diable Agent — cherche activement les failles/contradictions/hallucinations.

Modèle : hf.co/bartowski/Ministral-8B-Instruct-2410-GGUF:Q4_K_M (~5GB)
Pipeline : séquentiel après Judge.
           1. Charge hf.co/bartowski/Ministral-8B-Instruct-2410-GGUF:Q4_K_M
           2. Lit relay.json complet (query + response + critique Judge)
           3. Cherche activement les failles, biais, hallucinations
           4. Écrit advocate.score + advocate.faille → relay.json
           5. Unload modèle (libère VRAM)
"""


class AdvocateAgent:
    """Avocat du diable : cherche failles/hallucinations dans la réponse."""

    async def challenge(
        self, query: str, response: str, context: list[dict], judge_critique: dict
    ) -> dict:
        raise NotImplementedError

    async def unload(self) -> None:
        raise NotImplementedError
