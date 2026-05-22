#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_RLM_OUTPUT = Path("docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_GATE_2026-05-22.json")
DEFAULT_CONTEXT_OUTPUT = Path("docs/reports/NEXUS_CONTEXTHUB_SPLIT_PREGATE_2026-05-22.json")
RLM_AUTHORIZATION = Path("docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_RUNTIME_AUTHORIZATION_2026-05-22.json")


def _exists(repo_root: Path, path: str) -> bool:
    return (repo_root / path).exists()


def _read_json(repo_root: Path, path: Path) -> dict[str, Any]:
    target = repo_root / path
    if not target.exists():
        return {}
    loaded = json.loads(target.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def build_rlm_recursive_dispatch_gate(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    required = {
        "rlm_controller": "nexus/engine/rlm_controller.py",
        "routing_backlog_test": "tests/contracts/test_routing_spec_v2_backlog.py",
        "outcome_integration_test": "tests/engine/test_rlm_outcome_integration.py",
    }
    missing = [name for name, path in required.items() if not _exists(repo_root, path)]
    authorization = _read_json(repo_root, RLM_AUTHORIZATION)
    authorized = (
        authorization.get("status") == "APPROVED"
        and authorization.get("runtime_update_allowed") is True
        and int(authorization.get("budget_ceiling", {}).get("max_recursion_depth", 0) or 0) > 0
    )
    blockers = [] if authorized else ["recursive_runtime_dispatch_requires_separate_authorization"]
    blockers.extend(f"missing_{name}" for name in missing)
    decision = "APPROVED" if not blockers else "DEFERRED"
    budget_ceiling = authorization.get("budget_ceiling", {}) if isinstance(authorization.get("budget_ceiling"), dict) else {}
    return {
        "schema": "nexus.rlm_recursive_dispatch_gate.v1",
        "status": decision,
        "decision": decision,
        "runtime_update_allowed": bool(authorized),
        "public_benchmark_allowed": False,
        "recursive_dispatch_allowed": bool(authorized),
        "runtime_default_change_allowed": False,
        "max_recursion_depth": int(budget_ceiling.get("max_recursion_depth", 0) or 0),
        "max_handoff_count": int(budget_ceiling.get("max_handoff_count", 0) or 0),
        "baseline": "bounded_rlm_receipt_only",
        "authorization": RLM_AUTHORIZATION.as_posix() if authorized else "",
        "required_evidence": [
            "budget ceiling and stop reason receipt",
            "handoff and repair-loop composition receipt",
            "focused regression for recursive dispatch authorization",
        ],
        "checked_paths": required,
        "blockers": blockers,
    }


def build_contexthub_split_pregate(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    candidates = {
        "context_hub": "nexus/core/context_hub.py",
        "strict_deps_test": "tests/core/test_context_hub_strict_deps.py",
        "belief_engine_test": "tests/core/test_belief_engine.py",
        "context_view": "nexus/core/context_view.py",
    }
    missing = [name for name, path in candidates.items() if not _exists(repo_root, path)]
    strict_deps_test = (repo_root / candidates["strict_deps_test"]).read_text(encoding="utf-8", errors="ignore") if _exists(repo_root, candidates["strict_deps_test"]) else ""
    context_hub = (repo_root / candidates["context_hub"]).read_text(encoding="utf-8", errors="ignore") if _exists(repo_root, candidates["context_hub"]) else ""
    deletion_test_present = "test_context_hub_reexports_split_context_view_contracts" in strict_deps_test
    leaf_extraction_present = (
        _exists(repo_root, candidates["context_view"])
        and "from nexus.core.context_view import ContextDependencies, StateView" in context_hub
    )
    blockers = []
    if not deletion_test_present or not leaf_extraction_present:
        blockers.append("physical_split_requires_caller_map_and_deletion_tests")
    blockers.extend(f"missing_{name}" for name in missing)
    decision = "APPROVED" if not blockers else "DEFERRED"
    return {
        "schema": "nexus.contexthub_split_pregate.v1",
        "status": decision,
        "decision": decision,
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "physical_split_allowed": decision == "APPROVED",
        "compatibility_facade_required": True,
        "leaf_extraction_candidate": "nexus.core.context_view.StateView",
        "deletion_test": "tests/core/test_context_hub_strict_deps.py::test_context_hub_reexports_split_context_view_contracts",
        "caller_map": {
            "known_facade": candidates["context_hub"],
            "monkeypatch_sensitive_tests": [
                candidates["strict_deps_test"],
                candidates["belief_engine_test"],
            ],
        },
        "required_evidence": [
            "caller/import map for ContextHub construction",
            "responsibility map with one leaf extraction candidate",
            "deletion test proving duplicated logic removal",
        ],
        "checked_paths": candidates,
        "blockers": blockers,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Antigravity non-runtime gate reports.")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--rlm-output", type=Path, default=DEFAULT_RLM_OUTPUT)
    parser.add_argument("--context-output", type=Path, default=DEFAULT_CONTEXT_OUTPUT)
    args = parser.parse_args(argv)

    rlm = build_rlm_recursive_dispatch_gate(repo_root=args.repo_root)
    context = build_contexthub_split_pregate(repo_root=args.repo_root)
    _write_json(args.rlm_output, rlm)
    _write_json(args.context_output, context)
    print(
        json.dumps(
            {
                "rlm_status": rlm["status"],
                "context_status": context["status"],
                "rlm_output": args.rlm_output.as_posix(),
                "context_output": args.context_output.as_posix(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
