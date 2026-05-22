from __future__ import annotations

import json

from scripts.ops.build_antigravity_nonruntime_gates import (
    build_contexthub_split_pregate,
    build_rlm_recursive_dispatch_gate,
    main,
)


def _write(path, text="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_rlm_recursive_dispatch_gate_stays_deferred_without_runtime_unlock(tmp_path):
    repo = tmp_path / "repo"
    _write(repo / "nexus/engine/rlm_controller.py")
    _write(repo / "tests/contracts/test_routing_spec_v2_backlog.py")
    _write(repo / "tests/engine/test_rlm_outcome_integration.py")

    gate = build_rlm_recursive_dispatch_gate(repo_root=repo)

    assert gate["status"] == "DEFERRED"
    assert gate["recursive_dispatch_allowed"] is False
    assert gate["runtime_update_allowed"] is False
    assert gate["max_recursion_depth"] == 0
    assert gate["blockers"] == ["recursive_runtime_dispatch_requires_separate_authorization"]


def test_rlm_recursive_dispatch_gate_approves_bounded_authorized_implementation(tmp_path):
    repo = tmp_path / "repo"
    _write(repo / "nexus/engine/rlm_controller.py")
    _write(repo / "tests/contracts/test_routing_spec_v2_backlog.py")
    _write(repo / "tests/engine/test_rlm_outcome_integration.py")
    _write(
        repo / "docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_RUNTIME_AUTHORIZATION_2026-05-22.json",
        json.dumps(
            {
                "status": "APPROVED",
                "runtime_update_allowed": True,
                "budget_ceiling": {"max_recursion_depth": 1, "max_handoff_count": 1},
            }
        ),
    )

    gate = build_rlm_recursive_dispatch_gate(repo_root=repo)

    assert gate["status"] == "APPROVED"
    assert gate["recursive_dispatch_allowed"] is True
    assert gate["runtime_update_allowed"] is True
    assert gate["runtime_default_change_allowed"] is False
    assert gate["public_benchmark_allowed"] is False
    assert gate["max_recursion_depth"] == 1
    assert gate["blockers"] == []


def test_contexthub_split_pregate_requires_caller_map_before_split(tmp_path):
    repo = tmp_path / "repo"
    _write(repo / "nexus/core/context_hub.py")
    _write(repo / "tests/core/test_context_hub_strict_deps.py")
    _write(repo / "tests/core/test_belief_engine.py")

    gate = build_contexthub_split_pregate(repo_root=repo)

    assert gate["status"] == "DEFERRED"
    assert gate["physical_split_allowed"] is False
    assert gate["compatibility_facade_required"] is True
    assert gate["blockers"] == [
        "physical_split_requires_caller_map_and_deletion_tests",
        "missing_context_view",
    ]


def test_contexthub_split_pregate_approves_leaf_extraction_with_deletion_test(tmp_path):
    repo = tmp_path / "repo"
    _write(
        repo / "nexus/core/context_hub.py",
        "from nexus.core.context_view import ContextDependencies, StateView\n",
    )
    _write(repo / "nexus/core/context_view.py", "class StateView: pass\n")
    _write(
        repo / "tests/core/test_context_hub_strict_deps.py",
        "def test_context_hub_reexports_split_context_view_contracts(): pass\n",
    )
    _write(repo / "tests/core/test_belief_engine.py")

    gate = build_contexthub_split_pregate(repo_root=repo)

    assert gate["status"] == "APPROVED"
    assert gate["physical_split_allowed"] is True
    assert gate["leaf_extraction_candidate"] == "nexus.core.context_view.StateView"
    assert gate["blockers"] == []


def test_main_writes_both_gate_reports(tmp_path, capsys):
    repo = tmp_path / "repo"
    _write(repo / "nexus/engine/rlm_controller.py")
    _write(repo / "tests/contracts/test_routing_spec_v2_backlog.py")
    _write(repo / "tests/engine/test_rlm_outcome_integration.py")
    _write(repo / "nexus/core/context_hub.py")
    _write(repo / "tests/core/test_context_hub_strict_deps.py")
    _write(repo / "tests/core/test_belief_engine.py")
    rlm_output = tmp_path / "rlm.json"
    context_output = tmp_path / "context.json"

    assert main(["--repo-root", str(repo), "--rlm-output", str(rlm_output), "--context-output", str(context_output)]) == 0

    assert json.loads(rlm_output.read_text(encoding="utf-8"))["decision"] == "DEFERRED"
    assert json.loads(context_output.read_text(encoding="utf-8"))["decision"] == "DEFERRED"
    assert '"rlm_status": "DEFERRED"' in capsys.readouterr().out
