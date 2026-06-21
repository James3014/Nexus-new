from __future__ import annotations

from types import SimpleNamespace

from nexus.research.findings_vector_sync import MemoryRepositoryFindingsVectorSync
from nexus.services.local_heal.context import GovernanceContext, HealContext, OperationalContext
from nexus.services.local_heal.learning_closure_bridge import LearningClosureBridge, write_learning_closure
from nexus.services.local_heal.latency_ledger import LatencyLedger
from nexus.services.local_heal.memory_retrieval_adapter import (
    FindingsMemoryLessonStore,
    LocalJsonlLessonStore,
    MemoryRepositoryLessonStore,
    MemoryRetrievalAdapter,
    NexusCompositeLessonStore,
    RetrievedLesson,
)
from nexus.services.local_heal.memory_trace import MemoryTrace, build_memory_trace_from_adapter
from nexus.services.local_heal.native_evidence_packet import NativeEvidencePacketBuilder
from nexus.services.local_heal.orchestrator import HealOrchestrator
from nexus.services.local_heal.receipt import _extract_memory_trace


class FakeStore:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *, query_text: str, limit: int):
        return self.rows[:limit]


def test_receipt_uses_ctx_or_op_trace_without_adapter_class_fallback():
    assert not hasattr(MemoryRetrievalAdapter, "_last_trace")

    first = SimpleNamespace(
        _memory_influence_trace=MemoryTrace(
            available=True,
            trace_status="TRACE_AVAILABLE",
            memory_evidence_ids=["lesson-1"],
        )
    )
    assert _extract_memory_trace(first)["memory_evidence_ids"] == ["lesson-1"]

    nested = SimpleNamespace(
        op=SimpleNamespace(
            _memory_influence_trace={
                "available": True,
                "trace_status": "TRACE_AVAILABLE",
                "memory_evidence_ids": ["lesson-2"],
            }
        )
    )
    assert _extract_memory_trace(nested)["memory_evidence_ids"] == ["lesson-2"]

    second = SimpleNamespace()
    assert _extract_memory_trace(second)["trace_status"] == "TRACE_MISSING"
    assert _extract_memory_trace(second)["memory_evidence_ids"] == []


def test_composite_memory_retrieval_records_sources_and_hashes_query():
    composite = NexusCompositeLessonStore(
        [
            FakeStore([{"lesson_id": "jsonl-1", "summary": "format write path", "provenance": "receipt:jsonl"}]),
            FakeStore([{"lesson_id": "findings-1", "body": "format owner", "provenance": "receipt:findings"}]),
            FakeStore([{"lesson_id": "bad-1", "summary": "missing provenance"}]),
        ]
    )
    adapter = MemoryRetrievalAdapter(store=composite)

    lessons = adapter.retrieve(query_text="format output", limit=5)

    assert [lesson.finding_id for lesson in lessons] == ["jsonl-1", "findings-1"]
    assert adapter.last_metadata["rejected_without_provenance"] == 1
    assert adapter.last_metadata["query_text_hash"]
    assert "query_text" not in adapter.last_metadata
    assert adapter.last_metadata["retrieval_sources"] == ["FakeStore", "FakeStore", "FakeStore"]

    trace = build_memory_trace_from_adapter(adapter.last_metadata).to_dict()
    assert trace["retrieval_sources"] == ["FakeStore", "FakeStore", "FakeStore"]
    assert trace["memory_evidence_ids"] == ["jsonl-1", "findings-1"]
    assert trace["provenance_count"] == 2


def test_local_jsonl_store_reads_existing_learning_closure_rows(tmp_path):
    path = tmp_path / "learning_closure.jsonl"
    path.write_text(
        '{"lesson_id":"lh-jsonl","task_id":"C_1","classification":"verifier_pass",'
        '"summary":"format output owner","provenance":"receipt:jsonl"}\n',
        encoding="utf-8",
    )
    store = LocalJsonlLessonStore(path)

    rows = store.query(query_text="format output", limit=3)

    assert rows[0]["lesson_id"] == "lh-jsonl"
    assert rows[0]["provenance"] == "receipt:jsonl"


def test_memory_adapter_deduplicates_across_sources():
    adapter = MemoryRetrievalAdapter(
        NexusCompositeLessonStore(
            [
                FakeStore([{"lesson_id": "dup-1", "summary": "same", "provenance": "receipt:dup"}]),
                FakeStore([{"lesson_id": "dup-1", "summary": "same again", "provenance": "receipt:dup"}]),
            ]
        )
    )

    lessons = adapter.retrieve(query_text="same", limit=5)

    assert [lesson.finding_id for lesson in lessons] == ["dup-1"]


def test_memory_repository_lesson_store_is_fail_open():
    class BrokenRepository:
        def search_fts(self, *args, **kwargs):
            raise RuntimeError("offline")

    store = MemoryRepositoryLessonStore(repository=BrokenRepository())

    assert store.query(query_text="anything", limit=3) == []
    assert store.last_error == "RuntimeError"


def test_findings_memory_store_uses_token_fallback_for_multiword_queries():
    class FakeFindingsStore:
        def search(self, query, kind=None, scope="both"):
            if query == "output":
                return [
                    SimpleNamespace(
                        id="card-1",
                        title="Output lesson",
                        task_id="C_1",
                        body="Fix output writer",
                        tags=["local_heal"],
                        evidence_paths=["receipt:card"],
                        extra={"classification": "verifier_pass", "lesson_id": "lesson-card"},
                    )
                ]
            return []

    store = FindingsMemoryLessonStore(findings_store=FakeFindingsStore())

    rows = store.query(query_text="format output target.py", limit=3)

    assert rows[0]["lesson_id"] == "lesson-card"
    assert rows[0]["source"] == "FindingsMemoryStore"


def test_native_evidence_packet_uses_real_memory_adapter_not_heuristics(tmp_path):
    class FakeMemoryAdapter:
        def __init__(self):
            self.calls = []

        def retrieve_reranked(self, **kwargs):
            self.calls.append(kwargs)
            return [
                RetrievedLesson(
                    finding_id="lesson-real",
                    summary="Prior repair selected the write path.",
                    relevance_score=2.0,
                    provenance="receipt:real",
                    source="FindingsMemoryStore",
                    pattern_type="success",
                )
            ]

    repo_file = tmp_path / "target.py"
    repo_file.write_text("def write_output():\n    return True\n", encoding="utf-8")
    adapter = FakeMemoryAdapter()

    packet = NativeEvidencePacketBuilder(memory_adapter=adapter).build(
        task_id="C_1",
        route_id="local_heal",
        issue_intent="output_formatting",
        base_commit="abc",
        repo_path=str(tmp_path),
        target_file="target.py",
        anchor_symbol="write_output",
        anchor_span=(1, 2),
        anchor_source_text=repo_file.read_text(encoding="utf-8"),
    )

    assert [item.finding_id for item in packet.memory_evidence] == ["lesson-real"]
    assert packet.memory_evidence[0].provenance == "receipt:real"
    assert packet.memory_evidence[0].provenance != "local_memory_heuristic"
    assert adapter.calls[0]["anchor_symbol"] == "write_output"


def test_native_evidence_packet_records_missing_memory_risk(tmp_path):
    class EmptyMemoryAdapter:
        def retrieve_reranked(self, **kwargs):
            return []

    repo_file = tmp_path / "target.py"
    repo_file.write_text("def write_output():\n    return True\n", encoding="utf-8")

    packet = NativeEvidencePacketBuilder(memory_adapter=EmptyMemoryAdapter()).build(
        task_id="C_1",
        route_id="local_heal",
        issue_intent="output_formatting",
        base_commit="abc",
        repo_path=str(tmp_path),
        target_file="target.py",
        anchor_symbol="write_output",
        anchor_span=(1, 2),
        anchor_source_text=repo_file.read_text(encoding="utf-8"),
    )

    assert packet.memory_evidence == []
    assert "no_memory_evidence_available" in packet.missing_context_risks


def test_learning_closure_writes_jsonl_and_findings_card_fail_open(tmp_path):
    class FakeFindingsStore:
        def __init__(self):
            self.cards = []

        def write(self, card):
            self.cards.append(card)
            return f"memory://{card.id}"

    findings = FakeFindingsStore()
    trace = MemoryTrace(
        available=True,
        trace_status="TRACE_AVAILABLE",
        memory_evidence_ids=["lesson-real"],
        retrieval_sources=["FindingsMemoryStore"],
    )
    ctx = SimpleNamespace(
        instance_id="C_13453",
        solve_eligible=False,
        failure_reason="owner_gated",
        receipt_path="receipt:1",
        _memory_influence_trace=trace,
    )
    bridge = LearningClosureBridge(tmp_path / "learning.jsonl", findings_store=findings)

    result = write_learning_closure(ctx, bridge=bridge)

    assert result["writeback_status"] == "ok"
    lesson = result["lesson"]
    assert (tmp_path / "learning.jsonl").read_text(encoding="utf-8")
    assert lesson["findings_writeback_status"] == "ok"
    assert lesson["findings_card_id"] == findings.cards[0].id
    assert lesson["retrieved_memory_ids"] == ["lesson-real"]
    assert findings.cards[0].extra["training_export_allowed"] is False
    assert findings.cards[0].extra["internal_only"] is True

    class BrokenFindingsStore:
        def write(self, card):
            raise OSError("disk")

    failed = LearningClosureBridge(tmp_path / "failed.jsonl", findings_store=BrokenFindingsStore()).write_lesson(ctx)
    assert failed["findings_writeback_status"] == "failed_non_blocking"
    assert failed["training_export_allowed"] is False


def test_learning_closure_live_findings_memory_store_round_trip(tmp_path):
    trace = MemoryTrace(
        available=True,
        trace_status="TRACE_AVAILABLE",
        memory_evidence_ids=["seed-memory"],
        retrieval_sources=["LOCAL_LEARNING_CLOSURE_JSONL"],
    )
    ctx = SimpleNamespace(
        instance_id="C_live",
        solve_eligible=False,
        failure_reason="owner_gated",
        receipt_path="receipt:live",
        _memory_influence_trace=trace,
    )
    bridge = LearningClosureBridge(
        tmp_path / ".nexus" / "reports" / "learn" / "learning_closure.jsonl",
        project_root=tmp_path,
    )

    lesson = bridge.write_lesson(ctx)
    rows = FindingsMemoryLessonStore(project_root=tmp_path).query(query_text="owner_gated", limit=5)

    assert lesson["findings_writeback_status"] == "ok"
    assert rows
    assert rows[0]["lesson_id"] == lesson["lesson_id"]
    assert rows[0]["provenance"] == "receipt:live"


def test_orchestrator_finalize_attaches_ctx_memory_trace_before_receipt(tmp_path, monkeypatch):
    class FakeMemoryAdapter:
        def __init__(self):
            self.last_metadata = {}

        def retrieve_reranked(self, **kwargs):
            self.last_metadata = {
                "enabled": True,
                "query_text_hash": "abc123",
                "accepted": 1,
                "rejected_without_provenance": 0,
                "source": "NexusCompositeLessonStore",
                "retrieval_sources": ["LOCAL_LEARNING_CLOSURE_JSONL"],
                "selected_ids": ["lh-finalize"],
                "memory_evidence_ids": ["lh-finalize"],
                "no_memory_match": False,
            }
            return []

    monkeypatch.setattr("nexus.services.local_heal.memory_retrieval_adapter.MemoryRetrievalAdapter", FakeMemoryAdapter)
    monkeypatch.setattr(
        "nexus.services.local_heal.learning_closure_bridge.write_learning_closure",
        lambda ctx: setattr(ctx.op, "_learning_closure", {"writeback_status": "ok"}),
    )
    target = tmp_path / "target.py"
    target.write_text("def target_symbol():\n    return True\n", encoding="utf-8")
    ctx = HealContext(
        op=OperationalContext(
            instance_id="C_1",
            repo_dir=tmp_path,
            problem_statement="repair target_symbol with memory",
            plan=SimpleNamespace(search_symbols=["target_symbol"]),
            localized_files=[SimpleNamespace(path="target.py")],
            solve_eligible=False,
        ),
        gov=GovernanceContext(),
    )
    receipts = []

    class FakeGate:
        def audit(self, ctx):
            ctx.gov.gate_exit = "verification"

    def receipt_writer(ctx, run_group=""):
        receipts.append(ctx.op._memory_influence_trace.to_dict())
        return tmp_path / "receipt.json"

    ledger = LatencyLedger(task_id="", instance_id="C_1")
    orchestrator = HealOrchestrator([], FakeGate(), receipt_writer=receipt_writer)

    orchestrator._finalize_run(ctx, ledger, start_wall=0.0)

    assert receipts[0]["trace_status"] == "TRACE_AVAILABLE"
    assert receipts[0]["memory_evidence_ids"] == ["lh-finalize"]
    assert ctx.op._learning_closure["writeback_status"] == "ok"


def test_findings_vector_sync_maps_body_to_memory_repository_content(tmp_path):
    class FakeRepository:
        def __init__(self):
            self.payload = None

        def semantic_dedup_ingest(self, table_name, payload):
            self.payload = payload

    class FakeRegistry:
        def __init__(self, repo):
            self.repo = repo

        def repository_for(self, **kwargs):
            return self.repo

    repo = FakeRepository()
    sync = MemoryRepositoryFindingsVectorSync(tmp_path, registry=FakeRegistry(repo))

    assert sync.sync({"id": "card-1", "body": "indexed lesson body"}) is True
    assert repo.payload["content"] == "indexed lesson body"
