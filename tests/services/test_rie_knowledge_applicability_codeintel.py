"""#1579 G1/G2: RIE knowledge applicability as bounded codeintel evidence."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.services import rie_knowledge_applicability as ka
from nexus.services.capability_evidence_bundle import (
    MAX_CONSUMER_PAYLOAD_CHARS,
    extract_bounded_consumer_payload,
)

A, B = "a" * 64, "b" * 64
SNAP = {
    "repository": "owner/repo",
    "pr_number": 7,
    "head_sha": "head7",
    "base_sha": "main7",
    "current_main_sha": "main7",
}
PIN = ka.PINNED_RIE_ENGINE_REVISION
ENV = {ka.ENV_ENGINE_ROOT: "/engine", ka.ENV_PYTHON_BIN: "py"}


def _identity(**over):
    ident = dict(
        SNAP,
        declared_base_sha=None,
        declared_head_sha=None,
        declared_main_sha=None,
        stale_evidence=False,
        is_valid=True,
    )
    ident.update(over)
    return ident


def _report(relations=None, **over):
    rep = {
        "schema": ka.RIE_KNOWLEDGE_REPORT_SCHEMA,
        "identity": _identity(),
        "knowledge_artifacts": [],
        "changes": [],
        "observed_source_sha256": {},
        "in_scope": ["src/*"],
        "collection_complete": True,
        "collection_errors": [],
        "relations": relations or [],
        "uncovered_changes": [],
        "evidence_gaps": [],
        "is_complete": True,
        "claim_ceiling": ka.RIE_KNOWLEDGE_CLAIM_CEILING,
    }
    rep.update(over)
    rep["content_sha256"] = ka.canonical_hash(rep)
    return rep


def _rel(status, path="docs/a.md", **kw):
    return {
        "artifact_id": path,
        "artifact_path": path,
        "status": status,
        "reason_codes": ["SECRET_REASON_TEXT"],
        "affected_paths": [],
        **kw,
    }


class FakeRunner:
    def __init__(self, head=PIN, report=None, returncode=0, envelope_ceiling=None):
        self.head, self.report, self.returncode = head, report, returncode
        self.envelope_ceiling = envelope_ceiling or ka.RIE_KNOWLEDGE_CLAIM_CEILING
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        if cmd[0] == "git":
            return SimpleNamespace(returncode=0, stdout=self.head + "\n", stderr="")
        env = {
            "operation": "knowledge",
            "claim_ceiling": self.envelope_ceiling,
            "result": self.report,
        }
        return SimpleNamespace(returncode=self.returncode, stdout=json.dumps(env), stderr="")


ARTIFACTS = [
    {
        "artifact_id": "a",
        "path": "docs/a.md",
        "source_refs": [{"source_path": "src/a.py", "expected_content_sha256": A}],
        "covers": [],
    }
]


def _build(runner, **kw):
    args = dict(
        snapshot=SNAP,
        knowledge_artifacts=ARTIFACTS,
        changes=[],
        observed_source_sha256={"src/a.py": A},
        in_scope=["src/*"],
        collection_complete=True,
        env=ENV,
        runner=runner,
    )
    args.update(kw)
    return ka.build_codeintel_knowledge_evidence(**args)


def test_positive_projection_counts_and_ceiling():
    rep = _report(
        [
            _rel("CURRENT", "docs/c.md"),
            _rel("STALE_EXACT_SOURCE", "docs/s.md"),
            _rel("AFFECTED_BY_COVERAGE", "docs/x.md"),
            _rel("UNKNOWN", "docs/u.md"),
        ],
        uncovered_changes=["src/new.py"],
        evidence_gaps=["SOME_GAP"],
    )
    runner = FakeRunner(report=rep)
    out = _build(runner)["knowledge_applicability"]
    assert out["relation_counts"] == {
        "CURRENT": 1,
        "STALE_EXACT_SOURCE": 1,
        "AFFECTED_BY_COVERAGE": 1,
        "UNKNOWN": 1,
    }
    assert out["claim_ceiling"] == ka.PLANNER_SELECTED_CODEINTEL_CLAIM_CEILING
    assert out["rie_claim_ceiling"] == ka.RIE_KNOWLEDGE_CLAIM_CEILING
    assert out["report_hash"] == rep["content_sha256"]
    assert out["uncovered_change_refs"] == ["src/new.py"]
    assert out["evidence_gaps"] == ["SOME_GAP"]
    assert out["affected_artifact_refs"][0].startswith("STALE_EXACT_SOURCE:")
    assert "SECRET_REASON_TEXT" not in json.dumps(out)
    # engine invoked as subprocess with pinned root, cwd and PYTHONPATH
    cmd, kw = runner.calls[-1]
    assert cmd == [
        "py",
        "-m",
        "repository_intelligence.cli",
        "--operation",
        "knowledge",
        "--input",
        "-",
    ]
    assert kw["cwd"] == "/engine" and kw["env"]["PYTHONPATH"] == "/engine"


def test_no_claims_never_fabricates_current():
    runner = FakeRunner(report=_report())
    for kwargs in (
        {"knowledge_artifacts": None},
        {"knowledge_artifacts": []},
        {"snapshot": None},
        {"snapshot": {"repository": "o/r"}},
    ):
        out = _build(runner, **kwargs)["knowledge_applicability"]
        assert out["status"] == "NOT_APPLICABLE"
        assert out["relation_counts"]["CURRENT"] == 0
        assert out["evidence_gaps"]
    assert runner.calls == []  # engine not even invoked


def test_empty_relation_report_is_not_applicable():
    out = ka.project_knowledge_report(_report())
    assert out["status"] == "NOT_APPLICABLE" and out["relation_counts"]["CURRENT"] == 0


def test_incomplete_report_marked_incomplete():
    out = ka.project_knowledge_report(
        _report([_rel("UNKNOWN")], is_complete=False, evidence_gaps=["COLLECTION_INCOMPLETE"])
    )
    assert out["status"] == "INCOMPLETE"


@pytest.mark.parametrize("head", ["0" * 40, "not-a-sha"])
def test_engine_revision_mismatch_rejected(head):
    runner = FakeRunner(head=head, report=_report([_rel("CURRENT")]))
    with pytest.raises(ka.RieKnowledgeApplicabilityError) as exc:
        _build(runner)
    assert exc.value.code in {"RIE_ENGINE_REVISION_MISMATCH", "RIE_ENGINE_REVISION_UNREADABLE"}
    assert all(c[0][0] == "git" for c in runner.calls)  # never ran the engine


def test_engine_root_unconfigured_fails_closed():
    with pytest.raises(ka.RieKnowledgeApplicabilityError) as exc:
        _build(FakeRunner(report=_report()), env={})
    assert exc.value.code == "RIE_ENGINE_ROOT_NOT_CONFIGURED"


def _expect(code, report=None, **runner_kw):
    with pytest.raises(ka.RieKnowledgeApplicabilityError) as exc:
        _build(FakeRunner(report=report, **runner_kw))
    assert exc.value.code == code


def test_tampered_report_rejected():
    rep = _report([_rel("STALE_EXACT_SOURCE")])
    rep["relations"][0]["status"] = "CURRENT"  # tamper without rehash
    _expect("RIE_REPORT_CONTENT_SHA256_MISMATCH", rep)


def test_wrong_schema_and_claim_ceiling_rejected():
    _expect("RIE_REPORT_SCHEMA_MISMATCH", _report(schema="other.v1"))
    _expect("RIE_CLAIM_CEILING_MISMATCH", _report(claim_ceiling="PROOF"))
    _expect("RIE_CLAIM_CEILING_MISMATCH", _report(), envelope_ceiling="PROOF")


def test_wrong_revision_and_stale_identity_rejected():
    _expect("RIE_REPORT_IDENTITY_MISMATCH", _report(identity=_identity(head_sha="other")))
    _expect(
        "RIE_REPORT_IDENTITY_STALE_OR_INVALID", _report(identity=_identity(stale_evidence=True))
    )


def test_engine_failure_modes_fail_closed():
    _expect("RIE_ENGINE_NONZERO_EXIT", _report(), returncode=1)

    def boom(cmd, **kw):
        if cmd[0] == "git":
            return SimpleNamespace(returncode=0, stdout=PIN, stderr="")
        raise subprocess.TimeoutExpired(cmd, 1)

    with pytest.raises(ka.RieKnowledgeApplicabilityError) as exc:
        _build(boom)
    assert exc.value.code == "RIE_ENGINE_INVOCATION_FAILED"


def test_projection_bounded_and_survives_consumer_payload():
    rels = [_rel("STALE_EXACT_SOURCE", "docs/" + "x" * 300 + f"{i}.md") for i in range(40)]
    rep = _report(
        rels,
        uncovered_changes=[f"src/{'y' * 200}{i}.py" for i in range(40)],
        evidence_gaps=[f"GAP_{'z' * 200}_{i}" for i in range(40)],
    )
    proj = ka.project_knowledge_report(rep)
    assert len(proj["affected_artifact_refs"]) == ka.MAX_REFS
    assert len(proj["uncovered_change_refs"]) == ka.MAX_REFS
    assert len(proj["evidence_gaps"]) == ka.MAX_GAPS
    assert all(len(r) <= ka.MAX_REF_CHARS for r in proj["affected_artifact_refs"])
    assert proj["relation_counts"]["STALE_EXACT_SOURCE"] == 40

    payload = extract_bounded_consumer_payload(
        capability="codeintel",
        success=True,
        stage={
            "response": {
                "evidence": {
                    "action": "lookup_implementation",
                    "result": "found",
                    "knowledge_applicability": proj,
                }
            }
        },
    )
    fields = payload["fields"]
    assert not fields.get("truncated")
    assert payload["payload_chars"] <= MAX_CONSUMER_PAYLOAD_CHARS
    got = fields["knowledge_applicability"]
    assert got["relation_counts"] == proj["relation_counts"]
    assert got["claim_ceiling"] == ka.PLANNER_SELECTED_CODEINTEL_CLAIM_CEILING
    assert got["report_hash"] == rep["content_sha256"]
    assert got["affected_artifact_refs"] == proj["affected_artifact_refs"]
    assert "SECRET_REASON_TEXT" not in json.dumps(payload)


def test_not_applicable_survives_consumer_payload_without_current():
    na = ka.not_applicable_projection(["KNOWLEDGE_CLAIM_SOURCE_NOT_AVAILABLE"])
    payload = extract_bounded_consumer_payload(
        capability="codeintel",
        success=True,
        stage={"response": {"evidence": {"knowledge_applicability": na}}},
    )
    got = payload["fields"]["knowledge_applicability"]
    assert got["status"] == "NOT_APPLICABLE" and got["relation_counts"]["CURRENT"] == 0


def test_non_codeintel_capability_unaffected_by_key():
    # context-only knowledge key on a non-context capability yields nothing usable
    assert (
        extract_bounded_consumer_payload(
            capability="verifier", success=True, stage={"response": {"evidence": {}}}
        )
        == {}
    )


@pytest.mark.skipif(
    not (
        os.environ.get(ka.ENV_ENGINE_ROOT) and Path(os.environ.get(ka.ENV_ENGINE_ROOT, "")).is_dir()
    ),
    reason="NEXUS_RIE_ENGINE_ROOT not configured",
)
def test_real_engine_subprocess_roundtrip():
    try:
        ka.verify_engine_revision(Path(os.environ[ka.ENV_ENGINE_ROOT]))
    except ka.RieKnowledgeApplicabilityError:
        pytest.skip("engine root not at pinned revision")
    changes = [{"kind": "MODIFY", "path": "src/a.py"}]
    out = ka.build_codeintel_knowledge_evidence(
        snapshot=SNAP,
        knowledge_artifacts=ARTIFACTS,
        changes=changes,
        observed_source_sha256={"src/a.py": B},
        in_scope=["src/*"],
        collection_complete=True,
    )["knowledge_applicability"]
    assert out["relation_counts"]["STALE_EXACT_SOURCE"] == 1
    assert out["relation_counts"]["CURRENT"] == 0
    assert out["status"] == "COMPLETE"
    # affected != semantic incorrectness: projection carries no verdict on truth
    assert "incorrect" not in json.dumps(out).lower()
