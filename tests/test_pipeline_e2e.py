"""E2E pipeline (R7.1) — contrats fakes, aucune I/O réseau ni LLM.

Vérifie le flux complet plan → rewrite → retrieve → assemble → generate
→ (judge → advocate → evaluate) → wiki avec des fakes injectés dans
``PipelineServices`` : le graphe LangGraph réel est compilé et exécuté.
"""

from unittest.mock import AsyncMock

from src.agents.context_assembler import ContextAssembler
from src.agents.generator import GeneratorOutput
from src.agents.langgraph_orchestrator import PipelineServices, run_pipeline

_EMBEDDING = [0.1, 0.2, 0.3, 0.4]


class FakeOutput:
    """Contrat minimal des sorties d'agents (objets avec ``model_dump()``)."""

    def __init__(self, **data: object) -> None:
        self._data = dict(data)

    def model_dump(self) -> dict[str, object]:
        return dict(self._data)


def _search_results() -> list[dict]:
    return [
        {
            "id": "pt1",
            "score": 0.91,
            "payload": {"source_id": "s1", "text": "le backup Qdrant est quotidien"},
        },
        {
            "id": "pt2",
            "score": 0.85,
            "payload": {"source_id": "s2", "text": "les snapshots vont sur OMV"},
        },
    ]


def _services(**agents: object) -> PipelineServices:
    pool = AsyncMock()
    pool.embed = AsyncMock(return_value=[_EMBEDDING])
    vector = AsyncMock()
    vector.hybrid_search = AsyncMock(return_value=_search_results())
    return PipelineServices(
        pool=pool,
        vector=vector,
        lexical=AsyncMock(),
        reranker=None,
        assembler=ContextAssembler(),
        **agents,  # type: ignore[arg-type]
    )


class TestPipelineE2eFlow:
    async def test_generate_flow_without_evaluation(self) -> None:
        wikidb = {"write_page": AsyncMock(), "update_index": AsyncMock(), "append_log": AsyncMock()}
        wiki = AsyncMock()
        wiki.write_page, wiki.update_index, wiki.append_log = (
            wikidb["write_page"],
            wikidb["update_index"],
            wikidb["append_log"],
        )
        generator = AsyncMock()
        generator.generate = AsyncMock(
            return_value=GeneratorOutput(answer="réponse finalisée", confidence=0.87)
        )

        services = _services(generator=generator, wiki=wiki)
        state = await run_pipeline("comment sauvegarder Qdrant ?", services=services)

        assert len(state.search_results) == 2
        assert state.assembled is not None
        assert [c.source_id for c in state.assembled.chunks] == ["s1", "s2"]
        assert state.generated is not None
        assert state.generated.answer == "réponse finalisée"
        assert state.evaluator is None
        wiki.write_page.assert_awaited_once()
        wiki.append_log.assert_awaited_once()
        # Pas d'évaluation demandée : aucun appel judge/advocate/evaluator
        generator.generate.assert_awaited_once()

    async def test_evaluation_flow_runs_all_nodes(self) -> None:
        wiki = AsyncMock()
        wiki.write_page = AsyncMock()
        wiki.update_index = AsyncMock()
        wiki.append_log = AsyncMock()
        generator = AsyncMock()
        generator.generate = AsyncMock(return_value=GeneratorOutput(answer="A", confidence=0.8))
        judge = AsyncMock()
        judge.evaluate = AsyncMock(return_value=FakeOutput(score=0.9, critique="ok"))
        advocate = AsyncMock()
        advocate.challenge = AsyncMock(return_value=FakeOutput(score=0.7, faille="mineure"))
        evaluator = AsyncMock()
        evaluator.synthesize = AsyncMock(
            return_value=FakeOutput(final_score=0.83, decision="publish")
        )

        services = _services(
            generator=generator,
            judge=judge,
            advocate=advocate,
            evaluator=evaluator,
            wiki=wiki,
        )
        state = await run_pipeline(
            "question", services=services, evaluation_enabled=True
        )

        assert state.judge is not None
        assert state.judge["score"] == 0.9
        assert state.advocate is not None
        assert state.advocate["faille"] == "mineure"
        assert state.evaluator is not None
        assert state.evaluator["final_score"] == 0.83
        judge.evaluate.assert_awaited_once()
        advocate.challenge.assert_awaited_once()
        evaluator.synthesize.assert_awaited_once()
        # Publish → index mis à jour dans le wiki
        wiki.update_index.assert_awaited_once()

    async def test_no_generator_returns_empty_answer(self) -> None:
        services = _services()
        state = await run_pipeline("question", services=services)
        assert state.generated is None
        assert state.wiki_note is None
