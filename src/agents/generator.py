"""Generator Agent — inférence sur Machine 3 BC-250 (Vulkan ONLY).

Modèle : qwen3.5:14b Q4_K_M (~9GB) ou qwen3.5-35b-a3b IQ2_M (~11GB)
Contrainte : 16 GB RAM unifiée, CPU au repos pendant inference (règle d'or BC-250)
"""


class GeneratorAgent:
    """Génère la réponse brute sur BC-250, écrit dans relay.json pour Judge/Avocat."""

    async def generate(self, query: str, context: list[dict]) -> dict:
        raise NotImplementedError
