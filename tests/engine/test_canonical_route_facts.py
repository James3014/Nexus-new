"""Canonical planner task facts (#2688): restore the inputs cut by 5665fa00f."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from nexus.engine import canonical_route_facts as facts_mod
from nexus.engine.canonical_route_facts import (
    TIER_FACT_KEYS,
    allowed_files_cross_module,
    derive_canonical_route_facts,
)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "core.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    for name in ("a", "b", "c"):
        (root / "pkg" / f"user_{name}.py").write_text("from pkg.core import f\n", encoding="utf-8")
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    _commit(root)
    return root


def _commit(root: Path) -> None:
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "commit",
            "-q",
            "-m",
            "c",
        ],
        check=True,
    )


def test_cross_module_rule_matches_the_old_mcp_ingress() -> None:
    assert allowed_files_cross_module(["nexus/a.py", "nexus/b.py"])
    assert allowed_files_cross_module(["docs/a.md", "scripts/b.py"])
    assert not allowed_files_cross_module(["docs/a.md", "docs/b.md"])
    assert not allowed_files_cross_module(["nexus/a.py"])
    assert not allowed_files_cross_module(["nexus/a.py", "nexus/a.py"])
    assert not allowed_files_cross_module(["nexus/a.py", "nexus/./a.py"])


def test_facts_report_impact_risk_and_reverse_importers(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    facts = derive_canonical_route_facts(
        repo_root=root, task_text="fix f", task_type="repair", allowed_files=["pkg/core.py"]
    )

    assert facts["errors"] == []
    features, codeintel = facts["route_features"], facts["codeintel"]
    assert codeintel["risk_score"] > 0 and "risk_score" not in features
    assert codeintel["impact_report_present"] is True
    assert codeintel["impacted_files_count"] == 4  # core.py + three importers
    assert features["memory_hits"] == 0 and features["findings_hits"] == 0
    assert codeintel["cross_module"] is False
    assert not set(features) & set(TIER_FACT_KEYS)
    assert 0.0 <= features["adjusted_root_cause_confidence"] <= 1.0


def test_facts_never_carry_route_or_selection_keys(tmp_path: Path) -> None:
    """The Planner stays the route authority: no flow, lane, worker or model key."""
    from nexus_runtime.support.contracts.canonical_execution import _forbidden_context_key

    root = _repo(tmp_path)
    facts = derive_canonical_route_facts(
        repo_root=root,
        task_text="Fix the cross-module SDK race in pkg",
        task_type="repair",
        allowed_files=["pkg/core.py", "README.md"],
    )
    keys = [*facts["route_features"], *facts["codeintel"]]
    assert keys and not [key for key in keys if _forbidden_context_key(key)]
    assert facts["codeintel"]["cross_module"] is True
    assert facts["route_features"]["has_hard_signal"] is True


def test_a_failing_source_drops_only_its_own_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)

    def boom(*_args, **_kwargs):
        raise OSError("scan failed")

    monkeypatch.setattr(facts_mod, "_graph_index", boom)
    facts = derive_canonical_route_facts(
        repo_root=root, task_text="fix f", task_type="repair", allowed_files=["pkg/core.py"]
    )

    assert facts["errors"] == ["impact:OSError"]
    assert facts["codeintel"] == {}
    assert "memory_hits" in facts["route_features"]


def test_graph_is_scanned_once_per_root_and_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    calls: list[Path] = []
    real_scan = __import__(
        "nexus.services.codeintel.graph_builder", fromlist=["scan_codebase"]
    ).scan_codebase

    def counting_scan(path, *, index_path=None):
        calls.append(Path(path))
        return real_scan(path, index_path=index_path)

    monkeypatch.setattr("nexus.services.codeintel.graph_builder.scan_codebase", counting_scan)
    for _ in range(3):
        derive_canonical_route_facts(
            repo_root=root, task_text="fix f", task_type="repair", allowed_files=["pkg/core.py"]
        )

    assert calls == [root]


def test_seam_kill_switch_restores_the_old_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus.engine import canonical_task_seam as seam

    monkeypatch.setenv("NEXUS_CANONICAL_ROUTE_FACTS", "0")
    assert seam._canonical_route_facts(
        repo_root=Path("."), task_text="x", task_type="repair", allowed_files=("a.py",)
    ) == {"route_features": {}, "codeintel": {}}


def test_planner_tiers_a_cross_module_code_task_above_l1_with_the_facts() -> None:
    """Id kept for the impact gate. #2688 live witness: the facts must select codeintel
    without moving the routing tier (L3 -> main_engineering Workforce demand)."""
    from nexus.contracts.canonical_execution import CanonicalTaskContext
    from nexus.engine.canonical_execution import plan_canonical_task_bundle
    from nexus.engine.canonical_task_seam import REPO_ROOT

    allowed = ("nexus/engine/canonical_task_seam.py", "nexus/services/gateway.py")
    facts = derive_canonical_route_facts(
        repo_root=REPO_ROOT,
        task_text="Repair the gateway admission path",
        task_type="repair",
        allowed_files=allowed,
    )

    def plan(route_features, codeintel):
        context = CanonicalTaskContext(
            task_id="t-2688",
            task_type="repair",
            task_desc="Repair the gateway admission path",
            execution_world="product_runtime",
            transport_ingress="mcp",
            execution_channels=("online",),
            task_facts={"mutation_requested": True, "candidate_required": True},
            authority_inputs={
                "direct_canonical_eligible": False,
                "isolation_required": True,
                "owner_authorized": False,
                "assisted_execution_required": False,
            },
            route_features={
                "bounded_allowed_file_count": 2,
                "deterministic_verifier_available": True,
                **route_features,
            },
            codeintel={"allowed_files": list(allowed), **codeintel},
        )
        payload = plan_canonical_task_bundle(context, shared_playbook_root=REPO_ROOT).to_dict()[
            "plan_payload"
        ]
        snapshot = payload["signal_snapshot"]
        return (
            snapshot["routing_tier"],
            set(payload["selected_capabilities"]),
            snapshot["workforce_demands"],
        )

    before_tier, before, before_demands = plan({}, {})
    after_tier, after, after_demands = plan(facts["route_features"], facts["codeintel"])

    assert facts["codeintel"]["cross_module"] is True and facts["codeintel"]["risk_score"] >= 60
    assert after_tier == before_tier == "L1_green_lane"
    assert after_demands == before_demands
    assert "codeintel" not in before and "codeintel" in after


def test_paths_outside_the_root_are_never_read(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (tmp_path / "outside.py").write_text("x = 1\n", encoding="utf-8")

    facts = derive_canonical_route_facts(
        repo_root=root,
        task_text="fix",
        task_type="repair",
        allowed_files=["../outside.py", str(tmp_path / "outside.py"), "pkg/../../outside.py"],
    )

    assert facts["codeintel"] == {}


def test_uncommitted_python_changes_invalidate_the_cached_graph(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    first = derive_canonical_route_facts(
        repo_root=root, task_text="fix f", task_type="repair", allowed_files=["pkg/core.py"]
    )
    (root / "pkg" / "user_d.py").write_text("from pkg.core import f\n", encoding="utf-8")

    second = derive_canonical_route_facts(
        repo_root=root, task_text="fix f", task_type="repair", allowed_files=["pkg/core.py"]
    )

    assert (
        second["codeintel"]["impacted_files_count"]
        == first["codeintel"]["impacted_files_count"] + 1
    )


def test_a_root_without_a_revision_is_not_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "plain"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "core.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr(
        "nexus.services.codeintel.graph_builder.scan_codebase",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("cached a revisionless root")),
    )

    facts = derive_canonical_route_facts(
        repo_root=root, task_text="fix f", task_type="repair", allowed_files=["pkg/core.py"]
    )

    assert facts["errors"] == [] and facts["codeintel"]["impact_report_present"] is True


def test_a_second_edit_of_a_modified_file_rebuilds_the_graph(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    user = root / "pkg" / "user_a.py"
    user.write_text("import os\n", encoding="utf-8")  # first edit: drops the importer
    first = derive_canonical_route_facts(
        repo_root=root, task_text="fix f", task_type="repair", allowed_files=["pkg/core.py"]
    )
    user.write_text("from pkg.core import f\nimport os\n", encoding="utf-8")  # second edit

    second = derive_canonical_route_facts(
        repo_root=root, task_text="fix f", task_type="repair", allowed_files=["pkg/core.py"]
    )

    assert (
        second["codeintel"]["impacted_files_count"]
        == first["codeintel"]["impacted_files_count"] + 1
    )


def test_path_aliases_collapse_to_one_file(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    facts = derive_canonical_route_facts(
        repo_root=root,
        task_text="fix f",
        task_type="repair",
        allowed_files=["pkg/core.py", "pkg/./core.py"],
    )

    assert facts["codeintel"]["cross_module"] is False


def test_moving_an_import_between_dirty_files_changes_the_graph_key(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    a, b = root / "pkg" / "user_a.py", root / "pkg" / "user_b.py"
    a.write_text("from pkg.core import f\nx = 1\n", encoding="utf-8")
    b.write_text("x = 1\n", encoding="utf-8")
    first = facts_mod._graph_key(root)
    a.write_text("x = 1\n", encoding="utf-8")
    b.write_text("from pkg.core import f\nx = 1\n", encoding="utf-8")

    assert facts_mod._graph_key(root) != first


def test_cached_and_live_impact_give_the_same_risk(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    cached = derive_canonical_route_facts(
        repo_root=root, task_text="fix f", task_type="repair", allowed_files=["pkg/core.py"]
    )
    plain = tmp_path / "plain"
    subprocess.run(["cp", "-R", str(root), str(plain)], check=True)
    subprocess.run(["rm", "-rf", str(plain / ".git")], check=True)

    live = derive_canonical_route_facts(
        repo_root=plain, task_text="fix f", task_type="repair", allowed_files=["pkg/core.py"]
    )

    assert cached["codeintel"]["risk_score"] == live["codeintel"]["risk_score"]


def test_no_hits_keep_the_planners_default_confidence(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    facts = derive_canonical_route_facts(
        repo_root=root, task_text="fix f", task_type="repair", allowed_files=["pkg/core.py"]
    )

    assert facts["route_features"]["adjusted_root_cause_confidence"] == 1.0


def test_cached_and_live_impact_agree_at_the_cap(tmp_path: Path) -> None:
    """Many importers: the live score caps at 100 and so must the cached one."""
    root = _repo(tmp_path)
    for i in range(12):
        (root / "pkg" / f"many_{i}.py").write_text("from pkg.core import f\n", encoding="utf-8")
    _commit(root)
    plain = tmp_path / "plain"
    subprocess.run(["cp", "-R", str(root), str(plain)], check=True)
    subprocess.run(["rm", "-rf", str(plain / ".git")], check=True)

    cached = derive_canonical_route_facts(
        repo_root=root, task_text="fix f", task_type="repair", allowed_files=["pkg/core.py"]
    )
    live = derive_canonical_route_facts(
        repo_root=plain, task_text="fix f", task_type="repair", allowed_files=["pkg/core.py"]
    )

    assert cached["codeintel"]["risk_score"] == live["codeintel"]["risk_score"] == 100


def test_route_fact_probes_never_run_repository_config_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2742: an external measurement repo's fsmonitor (or one injected through GIT_CONFIG_*)
    must not run while the planner reads route facts."""
    root = _repo(tmp_path)
    marker = tmp_path / "fsmonitor-ran"
    hook = tmp_path / "fsmonitor.sh"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    hook.chmod(0o755)
    subprocess.run(["git", "-C", str(root), "config", "core.fsmonitor", str(hook)], check=True)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(hook))
    (root / "pkg" / "user_d.py").write_text("from pkg.core import f\n", encoding="utf-8")

    facts = derive_canonical_route_facts(
        repo_root=root, task_text="fix f", task_type="repair", allowed_files=["pkg/core.py"]
    )

    assert facts["codeintel"]["impacted_files_count"] >= 1
    assert not marker.exists()
