"""LangGraph Orchestrator — graphe d'état explicite du pipeline multi-agents.

Workflow :
1. Planifier (intention + stratégie)
2. Réécrire la requête (conversationnel)
3. Recherche hybride (BM25 + vectoriel) + rerank
4. Assembler le contexte (chunks + savoir interne)
5. Générer réponse (BC250)
6. Évaluer (Judge → Avocat → Évaluateur)
7. Mettre à jour le wiki (pages, index, log)
8. Retourner la réponse utilisateur
"""


def build_graph():
    """Construit le graphe LangGraph du pipeline."""
    # TODO: implémenter les nœuds et arêtes du graphe
    raise NotImplementedError


def main():
    """Point d'entrée pour le conteneur Docker langgraph-orchestrator."""
    build_graph()
    # TODO: lancer le serveur de workflow


if __name__ == "__main__":
    main()
