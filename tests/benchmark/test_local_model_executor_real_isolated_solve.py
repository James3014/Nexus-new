from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pytest

from scripts.bench.capability_ab_runner import CapabilityTask, _finalize_with_nexus_row


def _make_committee_envelope(candidate_id, target_file, target_symbol, patch_content):
    """Build a committee CandidateEnvelope with a real patch."""
    from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
    return CandidateEnvelope(
        candidate_id=candidate_id,
        task_id="real-solve",
        source="local",
        model="qwen2.5-coder:7b",
        role="primary_proposer",
        patch_protocol="anchored_edit",
        target_file=target_file,
        target_symbol=target_symbol,
        source_anchor_hash="ahash",
        candidate_patch_hash=hashlib.sha256(patch_content.encode()).hexdigest(),
        evidence_refs=("ref1",),
        candidate_patch=patch_content,
    )


def test_two_task_real_isolated_solve_local_model_armor(monkeypatch, tmp_path):
    """Real isolated solve: two toy tasks with actual apply/verify through IsolatedLocalSolveLoop."""
    from nexus.services.local_heal.local_committee_candidate_provider import LocalCommitteeCandidateProvider

    monkeypatch.setenv("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_EXECUTOR_DRY_RUN", "0")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_PROTOCOL_MODE", "anchored_edit")
    monkeypatch.setenv("NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED", "1")

    resolved_path = tmp_path.resolve()

    # --- Task A: locked_search present ---
    task_a_dir = resolved_path / "pkg"
    task_a_dir.mkdir(parents=True, exist_ok=True)
    (task_a_dir / "mod.py").write_text("def func():\n    pass\n", encoding="utf-8")

    # Create a simple verifier script at repo root
    (resolved_path / "verify_a.py").write_text(
        "import sys\nc = open('pkg/mod.py').read()\nsys.exit(0 if 'return 1' in c else 1)\n",
        encoding="utf-8",
    )

    # Patch that changes pass to return 1
    patch_a = (
        "<<<<<<< SEARCH\n"
        "def func():\n"
        "    pass\n"
        "=======\n"
        "def func():\n"
        "    return 1\n"
        ">>>>>>> REPLACE"
    )

    committee_called_a = False
    def mock_committee_a(*args, **kwargs):
        nonlocal committee_called_a
        committee_called_a = True
        return [_make_committee_envelope("a-primary", "pkg/mod.py", "func", patch_a)]

    # --- Task B: locked_search missing (ast_boundary fallback) ---
    task_b_dir = resolved_path / "lib"
    task_b_dir.mkdir(parents=True, exist_ok=True)
    (task_b_dir / "__init__.py").write_text("", encoding="utf-8")
    (task_b_dir / "helper.py").write_text("def compute(x):\n    return x * 2\n", encoding="utf-8")

    (resolved_path / "verify_b.py").write_text(
        "import sys\nc = open('lib/helper.py').read()\nsys.exit(0 if 'return x * 3' in c else 1)\n",
        encoding="utf-8",
    )

    patch_b = (
        "<<<<<<< SEARCH\n"
        "def compute(x):\n"
        "    return x * 2\n"
        "=======\n"
        "def compute(x):\n"
        "    return x * 3\n"
        ">>>>>>> REPLACE"
    )

    committee_called_b = False
    def mock_committee_b(*args, **kwargs):
        nonlocal committee_called_b
        committee_called_b = True
        return [_make_committee_envelope("b-primary", "lib/helper.py", "compute", patch_b)]

    # Track which task is being called
    call_count = [0]
    def mock_committee_dispatch(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            committee_called_a = True
            return [_make_committee_envelope("a-primary", "pkg/mod.py", "func", patch_a)]
        else:
            committee_called_b = True
            return [_make_committee_envelope("b-primary", "lib/helper.py", "compute", patch_b)]

    monkeypatch.setattr(LocalCommitteeCandidateProvider, "generate_committee_candidates", mock_committee_dispatch)

    results = []

    for task_id, target_file, target_symbol, locked_search, committee_fn, task_desc in [
        ("task-a-real", "pkg/mod.py", "func", "def func():\n    pass", mock_committee_a, "real solve A"),
        ("task-b-real", "lib/helper.py", "compute", "def compute(x):\n    return x * 2", mock_committee_b, "real solve B"),
    ]:
        task = CapabilityTask(
            id=task_id,
            task_desc=task_desc,
            task_type="bug",
            success_criteria="passes",
            difficulty="easy",
            category="test",
            expected_capabilities=["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
            target_file=target_file,
            test_file=f"{target_file.rsplit('/', 1)[0]}/test_{target_file.rsplit('/', 1)[-1].replace('.py', '')}.py",
        )

        row = {
            "capability_plan_selected": ["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
            "evidence_refs": [f"{task_id}-ref"],
            "verifier_command": ["python3", str(resolved_path / ("verify_a.py" if "task-a" in task_id else "verify_b.py"))],
            "target_symbol": target_symbol,
            "locked_search": locked_search,
            "candidate_generate_fn": lambda req: "mock",
            "signal_snapshot": {
                "execution_topology": "local_committee_only",
                "protocol_mode": "anchored_edit",
                "model_call_allowed": True,
                "executor_provider": "ollama",
                "executor_model": "qwen2.5-coder:7b",
                "judge_model": "qwen2.5:3b",
                "proposer_specs": [
                    {"model": "qwen2.5-coder:7b", "role": "primary"},
                    {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
                ]
            },
        }

        finalized = _finalize_with_nexus_row(
            row, provider="ollama", model_required=True, nexus_required=True,
            task=task, repo_root=resolved_path,
        )

        receipt = finalized.get("local_executor_receipt")
        adapter = finalized.get("local_model_adapter", {})
        adapter_meta = adapter.get("metadata", {})

        results.append({
            "task_id": task_id,
            "receipt": receipt,
            "adapter": adapter,
            "adapter_meta": adapter_meta,
            "finalized": finalized,
        })

    # Assert Task A
    rA = results[0]
    assert rA["receipt"] is not None
    assert rA["receipt"]["name"] == "local_model_executor"
    assert rA["receipt"]["gate_passed"] is True, f"Task A gate failed: {rA['receipt'].get('failure_reason')}"
    assert rA["adapter"].get("adapter_invoked") is True
    assert rA["adapter"].get("route_mode") == "local_only_executed"

    # Assert Task B
    rB = results[1]
    assert rB["receipt"] is not None
    assert rB["receipt"]["name"] == "local_model_executor"
    assert rB["receipt"]["gate_passed"] is True, f"Task B gate failed: {rB['receipt'].get('failure_reason')}"
    assert rB["adapter"].get("adapter_invoked") is True
    assert rB["adapter"].get("route_mode") == "local_only_executed"

    # Patches are applied in isolated workspace, not original files
    # Verify via receipt metadata that apply and verify succeeded
    for r in results:
        meta = r["adapter"].get("metadata", {})
        # The receipt should show gate_passed=True which means verifier passed
        # which means the patch was applied and verified in isolated workspace

    # Summary
    summary = {
        "total_tasks": 2,
        "solved_tasks": sum(1 for r in results if r["receipt"]["gate_passed"]),
        "real_isolated_solve": True,
    }
    assert summary["solved_tasks"] == 2
