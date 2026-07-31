"""Generator Agent — inférence sur Machine 3 BC-250 (Vulkan ONLY).

Modèle : hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M (~9GB) ou hf.co/Qwen/Qwen3-30B-A3B-GGUF:Q2_K (~11.3GB)
Contrainte : 16 GB RAM unifiée, CPU au repos pendant inference (règle d'or BC-250)
"""


class GeneratorAgent:
    """Génère la réponse brute sur BC-250, écrit dans relay.json pour Judge/Avocat."""

    async def generate(self, query: str, context: list[dict]) -> dict:
        raise NotImplementedError
