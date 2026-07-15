import json
from pathlib import Path

from nexus.core.context_hub import ContextDependencies, ContextHub
from nexus.services.wiki_knowledge_agent import WikiKnowledgeAgent, verify_runtime_integration


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_retrieval_reads_index_and_graph_and_ranks_current_authority():
    agent = WikiKnowledgeAgent(REPO_ROOT)

    result = agent.retrieve("CLI gate", max_results=3)

    index = json.loads(
        (REPO_ROOT / "nexus_wiki_vault/99_Schema/generated/agent-index.json").read_text()
    )
    graph = json.loads(
        (REPO_ROOT / "nexus_wiki_vault/99_Schema/generated/wikilink-graph.json").read_text()
    )
    assert result["status"] == "PASS"
    assert result["source_fingerprint"] == index["source_fingerprint"] == graph["source_fingerprint"]
    assert result["selected_sources"]
    assert result["retrieval_receipt"]["results"][0]["authority_classification"] == "current_verified"
    assert result["retrieval_receipt"]["results"][0]["source_page"]
    assert result["retrieval_receipt"]["results"][0]["retrieval_score"] > 0
    assert result["retrieval_receipt"]["results"][0]["source_fingerprint"] == result["source_fingerprint"]
    assert "source_page:" in result["context"]


def test_context_hub_diagnostic_pack_consumes_wiki_context():
    agent = WikiKnowledgeAgent(REPO_ROOT)
    hub = ContextHub(
        str(REPO_ROOT),
        deps=ContextDependencies(wiki_knowledge_agent=agent),
        strict_deps=True,
    )

    pack = hub.assemble_diag_pack([], "CLI gate")

    assert pack["wiki_retrieval"]["status"] == "PASS"
    assert pack["wiki_retrieval"]["selected_sources"]
    assert pack["wiki_retrieval"]["retrieval_receipt"]["source_fingerprint"]
    assert "authority_classification:" in pack["wiki_context"]


def test_missing_artifact_fails_closed(tmp_path: Path):
    result = WikiKnowledgeAgent(tmp_path).retrieve("CLI gate")

    assert result["status"] == "RETURN"
    assert result["context"] == ""
    assert "missing_wiki_artifact:agent-index.json" in result["blockers"]


def test_no_result_does_not_hallucinate():
    result = WikiKnowledgeAgent(REPO_ROOT).retrieve("zzzz-no-authority-page-9f7e", max_results=2)

    assert result["status"] == "RETURN"
    assert result["context"] == ""
    assert result["selected_sources"] == []
    assert "no_current_authority_match" in result["blockers"]


def test_stale_recompile_fails_closed(monkeypatch):
    class StaleCompiler:
        def __init__(self, *args, **kwargs):
            pass

        def build(self):
            return ({"source_fingerprint": "stale"}, {"source_fingerprint": "stale"}, "")

    monkeypatch.setattr("scripts.ops.build_wiki_agent_index.WikiIndexCompiler", StaleCompiler)

    result = WikiKnowledgeAgent(REPO_ROOT).retrieve("CLI gate")

    assert result["status"] == "RETURN"
    assert result["context"] == ""
    assert "stale_wiki_artifact" in result["blockers"]


def test_legacy_only_match_is_downgraded_and_not_selected(monkeypatch):
    page = REPO_ROOT / "nexus_wiki_vault/00_Home/Agent Onboarding - Command Pack.md"
    agent = WikiKnowledgeAgent(REPO_ROOT)
    monkeypatch.setattr(
        agent,
        "_load_artifacts",
        lambda: {
            "index": {
                "pages": [{
                    "id": "legacy-onboarding",
                    "path": "00_Home/Agent Onboarding - Command Pack.md",
                    "title": "Agent Onboarding Command Pack",
                    "one_sentence_summary": "Legacy onboarding command pack",
                    "source_of_truth": "wiki",
                }],
            },
            "graph": {"edges": []},
            "freshness": {"pages": [{"path": page.relative_to(REPO_ROOT / "nexus_wiki_vault").as_posix(), "classification": "superseded"}]},
            "source_fingerprint": "fixture-fingerprint",
        },
    )

    result = agent.retrieve("legacy onboarding command pack")

    assert result["status"] == "RETURN"
    assert result["context"] == ""
    assert result["selected_sources"] == []
    assert result["retrieval_receipt"]["results"][0]["selected"] is False
    assert "legacy_only_result" in result["blockers"]


def test_runtime_gate_passes_on_real_repo():
    passed, blockers = verify_runtime_integration(REPO_ROOT)

    assert passed, blockers
