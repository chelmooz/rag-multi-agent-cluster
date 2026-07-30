"""Évaluateur Agent — synthèse finale sur Machine 1 CPU (qwen3.5:3b).

Pipeline :
1. Lit relay.json complet (response + Judge + Avocat)
2. Synthétise les avis en décision finale
3. Calcule un score de confiance global
4. Écrit verified: human-reviewed dans le frontmatter OKF des pages validées
"""


class EvaluatorAgent:
    """Synthèse finale : combine Judge + Avocat en réponse finale et décision de publication."""

    async def synthesize(self, relay_data: dict) -> dict:
        raise NotImplementedError

    async def update_frontmatter(self, page_path: str, trust_tier: str) -> None:
        """Met à jour le champ verified: human-reviewed dans le frontmatter OKF."""
        raise NotImplementedError
