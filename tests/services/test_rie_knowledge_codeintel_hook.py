"""#1579 G3 seam: codeintel hook + invoker carry RIE knowledge applicability."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.services import rie_knowledge_applicability as ka
from nexus.services import rie_knowledge_codeintel_hook as hook

ENV = {ka.ENV_ENGINE_ROOT: "/engine", ka.ENV_PYTHON_BIN: "py"}
DOC = "docs/knowledge/doc.md"
SRC = "src/a.py"


def _git(root: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def make_repo(root: Path) -> tuple[str, str]:
    """Temp repo with a manifest; returns (base_sha, head_sha) where head edits SRC."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / "src").mkdir()
    (root / "docs/knowledge").mkdir(parents=True)
    (root / SRC).write_text("print('v1')\n")
    (root / DOC).write_text("# doc about src/a.py\n")
    sha = hashlib.sha256((root / SRC).read_bytes()).hexdigest()
    manifest = {
        "schema": "nexus.rie_knowledge_manifest.v1",
        "revision": "1" * 40,
        "claim_ceiling": "REPOSITORY_KNOWLEDGE_MANIFEST_DECLARATION_ONLY",
        "notes": "test",
        "entries": [
            {
                "id": "doc",
                "path": DOC,
                "source_refs": [{"path": SRC, "expected_content_sha256": sha}],
                "covers": [],
                "in_scope": True,
            }
        ],
    }
    (root / "docs/knowledge/rie_knowledge_manifest.v1.json").write_text(json.dumps(manifest))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")
    (root / SRC).write_text("print('v2')\n")
    _git(root, "commit", "-q", "-am", "head")
    return base, _git(root, "rev-parse", "HEAD")


def identity(base: str) -> dict:
    return {
        "repository": "owner/repo",
        "pr_number": 7,
        "base_sha": base,
        "current_main_sha": base,
    }


def stub_report(head: str, base: str, status: str = "STALE_EXACT_SOURCE", **over) -> dict:
    rep = {
        "schema": ka.RIE_KNOWLEDGE_REPORT_SCHEMA,
        "identity": {
            "repository": "owner/repo",
            "pr_number": 7,
            "head_sha": head,
            "base_sha": base,
            "current_main_sha": base,
            "declared_base_sha": None,
            "declared_head_sha": None,
            "declared_main_sha": None,
            "stale_evidence": False,
            "is_valid": True,
        },
        "relations": [
            {
                "artifact_id": "doc",
                "artifact_path": DOC,
                "status": status,
                "reason_codes": ["X"],
                "affected_paths": [SRC],
            }
        ],
        "uncovered_changes": [],
        "evidence_gaps": [],
        "is_complete": True,
        "claim_ceiling": ka.RIE_KNOWLEDGE_CLAIM_CEILING,
    }
    rep.update(over)
    rep["content_sha256"] = ka.canonical_hash(rep)
    return rep


class StubRunner:
    def __init__(self, report=None, head=ka.PINNED_RIE_ENGINE_REVISION):
        self.report, self.head, self.engine_calls = report, head, 0

    def __call__(self, cmd, **kw):
        if cmd[0] == "git":
            return SimpleNamespace(returncode=0, stdout=self.head + "\n", stderr="")
        self.engine_calls += 1
        env = {
            "operation": "knowledge",
            "claim_ceiling": ka.RIE_KNOWLEDGE_CLAIM_CEILING,
            "result": self.report,
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(env), stderr="")


def _ctx(root: Path, head: str, base: str | None, **over) -> dict:
    ctx = {"workspace_root": str(root), "target_revision": head}
    if base:
        ctx["rie_knowledge_identity"] = identity(base)
    ctx.update(over)
    return ctx


def _status(out: dict) -> str:
    return out["knowledge_applicability"]["status"]


def test_no_identity_is_not_applicable_and_engine_untouched(tmp_path):
    base, head = make_repo(tmp_path / "r")
    runner = StubRunner(stub_report(head, base))
    out = hook.knowledge_applicability_evidence(
        _ctx(tmp_path / "r", head, None), env=ENV, runner=runner
    )
    assert _status(out) == "NOT_APPLICABLE"
    assert out["knowledge_applicability"]["evidence_gaps"] == ["REVISION_IDENTITY_UNAVAILABLE"]
    assert runner.engine_calls == 0


@pytest.mark.parametrize(
    "bad",
    [
        {"repository": "no-slash", "pr_number": 1},
        {"repository": "o/r", "pr_number": 0},
        {"repository": "o/r", "pr_number": True},
        {"repository": "o/r", "pr_number": 1, "base_sha": "xyz"},
        "not-a-mapping",
    ],
)
def test_invalid_identity_hint_is_not_applicable(tmp_path, bad):
    base, head = make_repo(tmp_path / "r")
    runner = StubRunner(stub_report(head, base))
    hint = bad if isinstance(bad, str) else {"base_sha": base, **bad}
    ctx = _ctx(tmp_path / "r", head, None, rie_knowledge_identity=hint)
    out = hook.knowledge_applicability_evidence(ctx, env=ENV, runner=runner)
    assert _status(out) == "NOT_APPLICABLE"
    assert runner.engine_calls == 0


def test_engine_unconfigured_is_not_applicable(tmp_path):
    base, head = make_repo(tmp_path / "r")
    runner = StubRunner(stub_report(head, base))
    out = hook.knowledge_applicability_evidence(
        _ctx(tmp_path / "r", head, base), env={}, runner=runner
    )
    assert _status(out) == "NOT_APPLICABLE"
    assert out["knowledge_applicability"]["evidence_gaps"] == ["RIE_ENGINE_ROOT_NOT_CONFIGURED"]
    assert runner.engine_calls == 0


def test_head_mismatch_is_not_applicable(tmp_path):
    base, head = make_repo(tmp_path / "r")
    runner = StubRunner(stub_report(head, base))
    ctx = _ctx(tmp_path / "r", base, base)  # target_revision != checked-out HEAD
    out = hook.knowledge_applicability_evidence(ctx, env=ENV, runner=runner)
    assert _status(out) == "NOT_APPLICABLE"
    assert out["knowledge_applicability"]["evidence_gaps"] == ["HEAD_REVISION_MISMATCH"]
    assert runner.engine_calls == 0


def test_applicable_projection_with_stub_engine(tmp_path):
    base, head = make_repo(tmp_path / "r")
    rep = stub_report(head, base)
    runner = StubRunner(rep)
    out = hook.knowledge_applicability_evidence(
        _ctx(tmp_path / "r", head, base), env=ENV, runner=runner
    )
    proj = out["knowledge_applicability"]
    assert runner.engine_calls == 1
    assert proj["status"] != "CURRENT"
    assert proj["relation_counts"]["STALE_EXACT_SOURCE"] == 1
    assert proj["report_hash"] == rep["content_sha256"]
    assert proj["claim_ceiling"] == ka.PLANNER_SELECTED_CODEINTEL_CLAIM_CEILING


def test_tampered_report_is_non_current_and_does_not_raise(tmp_path):
    base, head = make_repo(tmp_path / "r")
    rep = stub_report(head, base, "CURRENT")
    rep["relations"][0]["status"] = "STALE_EXACT_SOURCE"  # hash no longer matches
    out = hook.knowledge_applicability_evidence(
        _ctx(tmp_path / "r", head, base), env=ENV, runner=StubRunner(rep)
    )
    proj = out["knowledge_applicability"]
    assert proj["status"] == "INCOMPLETE"
    assert proj["evidence_gaps"] == ["RIE_KNOWLEDGE_REJECTED:RIE_REPORT_CONTENT_SHA256_MISMATCH"]
    assert proj["relation_counts"]["CURRENT"] == 0


def test_wrong_revision_report_is_non_current(tmp_path):
    base, head = make_repo(tmp_path / "r")
    rep = stub_report("f" * 40, base, "CURRENT")
    out = hook.knowledge_applicability_evidence(
        _ctx(tmp_path / "r", head, base), env=ENV, runner=StubRunner(rep)
    )
    proj = out["knowledge_applicability"]
    assert proj["status"] == "INCOMPLETE"
    assert proj["evidence_gaps"][0].startswith("RIE_KNOWLEDGE_REJECTED:RIE_REPORT_IDENTITY")


def test_wrong_engine_revision_is_non_current(tmp_path):
    base, head = make_repo(tmp_path / "r")
    out = hook.knowledge_applicability_evidence(
        _ctx(tmp_path / "r", head, base),
        env=ENV,
        runner=StubRunner(stub_report(head, base), head="0" * 40),
    )
    assert _status(out) == "INCOMPLETE"


def test_missing_manifest_is_non_current(tmp_path):
    base, head = make_repo(tmp_path / "r")
    (tmp_path / "r/docs/knowledge/rie_knowledge_manifest.v1.json").unlink()
    out = hook.knowledge_applicability_evidence(
        _ctx(tmp_path / "r", head, base), env=ENV, runner=StubRunner(stub_report(head, base))
    )
    assert _status(out) == "INCOMPLETE"


def test_runner_exception_never_raises(tmp_path):
    base, head = make_repo(tmp_path / "r")

    def boom(*a, **k):
        raise RuntimeError("boom")

    out = hook.knowledge_applicability_evidence(
        _ctx(tmp_path / "r", head, base), env=ENV, runner=boom
    )
    assert _status(out) == "INCOMPLETE"
    assert hook.knowledge_applicability_evidence(None) is not None  # type: ignore[arg-type]


def test_invoker_output_carries_knowledge_applicability(monkeypatch):
    from nexus.services import capability_registry as cr

    seen = {}

    def fake_hook(context):
        seen["context"] = dict(context)
        return {
            "knowledge_applicability": ka.not_applicable_projection([
                "REVISION_IDENTITY_UNAVAILABLE"
            ])
        }

    monkeypatch.setattr(
        "nexus.services.rie_knowledge_codeintel_hook.knowledge_applicability_evidence", fake_hook
    )
    monkeypatch.setattr(
        cr,
        "build_real_executor_invoker",
        lambda name: (
            (lambda ctx: {"task_id": "t", "invoked": True, "evidence": {"risk_score": 3}})
            if name == "codeintel"
            else None
        ),
    )
    out = cr.build_default_mainchain_invokers()["codeintel"]({"task_id": "t"})
    assert out["evidence"]["risk_score"] == 3
    assert out["evidence"]["knowledge_applicability"]["status"] == "NOT_APPLICABLE"
    assert seen["context"]["task_id"] == "t"


def test_invoker_preflight_fallback_and_hook_failure_does_not_break_stage(monkeypatch):
    from nexus.services import capability_registry as cr

    monkeypatch.setattr(cr, "build_real_executor_invoker", lambda name: None)
    out = cr.build_default_mainchain_invokers(codeintel={"risk_score": 2})["codeintel"]({
        "task_id": "t"
    })
    assert out["invoked"] is True
    assert out["evidence"]["knowledge_applicability"]["status"] == "NOT_APPLICABLE"

    def explode(context):
        raise RuntimeError("hook bug")

    monkeypatch.setattr(
        "nexus.services.rie_knowledge_codeintel_hook.knowledge_applicability_evidence", explode
    )
    out = cr.build_default_mainchain_invokers(codeintel={"risk_score": 2})["codeintel"]({
        "task_id": "t"
    })
    assert out["invoked"] is True
    assert "knowledge_applicability" not in out["evidence"]


# Opt-in real-engine proof: only collected when NEXUS_RIE_ENGINE_ROOT is set (no skips in CI).
if os.environ.get(ka.ENV_ENGINE_ROOT):

    def test_real_engine_marks_modified_declared_source_stale(tmp_path):
        base, head = make_repo(tmp_path / "r")
        env = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", ka.ENV_ENGINE_ROOT}}
        env[ka.ENV_PYTHON_BIN] = os.environ.get(ka.ENV_PYTHON_BIN, "python3")
        out = hook.knowledge_applicability_evidence(_ctx(tmp_path / "r", head, base), env=env)
        proj = out["knowledge_applicability"]
        assert proj["relation_counts"]["STALE_EXACT_SOURCE"] >= 1, proj
        assert re.fullmatch(r"[0-9a-f]{64}", proj["report_hash"])
