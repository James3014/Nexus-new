"""#2259: policy manifest schema — enforcement_mode, verifiable commit refs, behavioural entrypoints.

The lane gate used to require only a non-empty ``test_entrypoints`` list, so a
policy could say "enforced" while its only test called the guard directly and
nothing in production did (#2199). These tests pin the new manifest fields and
the static behavioural check that closes that gap.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from scripts.ops import check_policy_lane_gate as gate
from scripts.ops.check_policy_lane_gate import (
    ENFORCEMENT_MODES,
    check_enforcement_wiring,
    check_lane_gate,
    load_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def _policy(manifest: dict, policy_id: str) -> dict:
    return next(p for p in manifest["policies"] if p["policy_id"] == policy_id)


# ─── enforcement_mode ───────────────────────────────────────────────


def test_every_policy_declares_a_valid_enforcement_mode() -> None:
    manifest = load_manifest()
    assert "enforcement_mode" in manifest["schema"]["fields"]
    for policy in manifest["policies"]:
        assert policy.get("enforcement_mode") in ENFORCEMENT_MODES, policy["policy_id"]
    distribution = manifest["summary"]["enforcement_mode_distribution"]
    assert set(distribution) == set(ENFORCEMENT_MODES)
    assert sorted(sum(distribution.values(), [])) == sorted(
        p["policy_id"] for p in manifest["policies"]
    )
    for mode, ids in distribution.items():
        assert ids == sorted(
            p["policy_id"] for p in manifest["policies"] if p["enforcement_mode"] == mode
        )


def test_p_contam_01_is_record_only_with_guard_modules() -> None:
    policy = _policy(load_manifest(), "P-CONTAM-01")
    assert policy["enforcement_mode"] == "record_only"
    sources = gate._source_paths(policy)
    guards = policy["guard_modules"]
    assert set(guards) <= set(sources)
    callers = sorted(set(sources) - set(guards))
    assert callers == [
        "nexus/app/research_flow_service.py",
        "nexus/core/capability_executor_registry.py",
    ]


def test_guard_modules_are_always_a_subset_of_source_file() -> None:
    for policy in load_manifest()["policies"]:
        guards = set(policy.get("guard_modules") or [])
        assert guards <= set(gate._source_paths(policy)), policy["policy_id"]


def test_invalid_enforcement_mode_fails_closed_in_every_lane(monkeypatch) -> None:
    original = load_manifest()
    for policy_id in ("P-GATE-03", "P-ROUTE-01", "P-AUTO-01"):
        for bad in (None, "", "advisory"):
            tampered = {
                **original,
                "policies": [
                    {**p, "enforcement_mode": bad} if p["policy_id"] == policy_id else p
                    for p in original["policies"]
                ],
            }
            monkeypatch.setattr(gate, "load_manifest", lambda t=tampered: t)
            result = check_lane_gate(policy_id, "observe")
            assert result["allowed"] is False
            assert result["errors"] == ["ENFORCEMENT_MODE_INVALID"]


# ─── commit refs ────────────────────────────────────────────────────


def _history_available() -> bool:
    try:
        shallow = subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return shallow.returncode == 0 and shallow.stdout.strip() == "false"


def test_commit_refs_are_verifiable_after_squash() -> None:
    manifest = load_manifest()
    assert "verified_in_pr" in manifest["schema"]["fields"]
    assert "commit_ref_policy" in manifest
    baseline = manifest["commit_sha"]
    history = _history_available()
    verified = 0
    for policy in manifest["policies"]:
        pr = policy.get("verified_in_pr")
        sha = policy["commit_sha"]
        if pr is None:
            # Baseline-freeze label (pre-split history), never a PR-branch commit.
            assert baseline.startswith(sha), policy["policy_id"]
            continue
        verified += 1
        assert isinstance(pr, int) and pr > 0, policy["policy_id"]
        assert FULL_SHA.match(sha), (policy["policy_id"], sha)
        if history:
            # The squash-merge commit must be reachable from the current checkout.
            ancestor = subprocess.run(
                ["git", "merge-base", "--is-ancestor", sha, "HEAD"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            assert ancestor.returncode == 0, (policy["policy_id"], sha, ancestor.stderr)
    assert verified >= 1  # P-CONTAM-01 (#2216)


def test_p_contam_01_no_longer_points_at_a_pr_branch_commit() -> None:
    policy = _policy(load_manifest(), "P-CONTAM-01")
    assert policy["verified_in_pr"] == 2216
    assert policy["commit_sha"] != "8e1da0e9b"
    assert FULL_SHA.match(policy["commit_sha"])


# ─── behavioural entrypoint check ───────────────────────────────────


def _fake_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "guard.py").write_text("def check(x):\n    return bool(x)\n", encoding="utf-8")
    (root / "pkg" / "caller.py").write_text(
        "from pkg.guard import check\n\ndef run(x):\n    return check(x)\n", encoding="utf-8"
    )
    (root / "pkg" / "shim.py").write_text("from pkg.caller import run\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_guard_only.py").write_text(
        "def test_guard():\n    from pkg.guard import check\n    assert check(1)\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_caller.py").write_text(
        "from pkg import caller\n\ndef test_run():\n    assert caller.run(1)\n", encoding="utf-8"
    )
    (root / "tests" / "test_via_shim.py").write_text(
        "import pkg.shim\n\ndef test_shim():\n    assert pkg.shim.run(1)\n", encoding="utf-8"
    )
    return root


def _fake_policy(**overrides) -> dict:
    policy = {
        "policy_id": "P-FAKE-01",
        "lane": "hard",
        "enforcement_mode": "record_only",
        "source_file": "pkg/guard.py; pkg/caller.py",
        "guard_modules": ["pkg/guard.py"],
        "test_entrypoints": ["tests/test_guard_only.py::test_guard"],
        "rollback_drill_status": "drilled-2026-10-15",
        "promotion_allowed": False,
    }
    policy.update(overrides)
    return policy


def test_entrypoint_that_only_calls_the_guard_is_rejected(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    assert check_enforcement_wiring(_fake_policy(), root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"]
    # Same verdict for a blocking policy.
    assert check_enforcement_wiring(_fake_policy(enforcement_mode="block"), root) == [
        "TEST_ENTRYPOINT_NOT_BEHAVIOURAL"
    ]


def test_entrypoint_through_a_production_caller_is_accepted(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    direct = _fake_policy(test_entrypoints=["tests/test_caller.py::test_run"])
    assert check_enforcement_wiring(direct, root) == []
    via_shim = _fake_policy(test_entrypoints=["tests/test_via_shim.py"])
    assert check_enforcement_wiring(via_shim, root) == []
    mixed = _fake_policy(
        test_entrypoints=["tests/test_guard_only.py::test_guard", "tests/test_caller.py::test_run"]
    )
    assert check_enforcement_wiring(mixed, root) == []


def test_wiring_check_edge_cases(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    assert check_enforcement_wiring(_fake_policy(enforcement_mode="not_wired"), root) == []
    assert check_enforcement_wiring(_fake_policy(enforcement_mode="maybe"), root) == [
        "ENFORCEMENT_MODE_INVALID"
    ]
    all_guard = _fake_policy(source_file="pkg/guard.py", guard_modules=["pkg/guard.py"])
    assert check_enforcement_wiring(all_guard, root) == ["ENFORCEMENT_CALLERS_MISSING"]
    foreign = _fake_policy(guard_modules=["pkg/other.py"])
    assert check_enforcement_wiring(foreign, root) == ["GUARD_MODULE_NOT_IN_SOURCE: pkg/other.py"]
    rust_only = _fake_policy(
        source_file="core/src/guard.rs",
        guard_modules=[],
        test_entrypoints=["core/src/guard.rs::tests"],
    )
    assert check_enforcement_wiring(rust_only, root) == []
    missing_file = _fake_policy(test_entrypoints=["tests/does_not_exist.py"])
    assert check_enforcement_wiring(missing_file, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"]


def test_lane_gate_rejects_guard_only_entrypoint_for_real_policy(
    monkeypatch, tmp_path: Path
) -> None:
    """Done-when of #2259: the gate rejects a policy whose only entrypoint calls the guard directly."""
    guard_only = tmp_path / "test_guard_direct.py"
    guard_only.write_text(
        "def test_direct():\n"
        "    from nexus.research.contamination_enforcement import check_research_output\n"
        "    assert check_research_output\n",
        encoding="utf-8",
    )
    original = load_manifest()
    rel = guard_only.relative_to(tmp_path).as_posix()
    tampered = {
        **original,
        "policies": [
            {**p, "test_entrypoints": [f"{rel}::test_direct"]}
            if p["policy_id"] == "P-CONTAM-01"
            else p
            for p in original["policies"]
        ],
    }
    monkeypatch.setattr(gate, "load_manifest", lambda: tampered)
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    result = check_lane_gate("P-CONTAM-01", "modify")
    assert result["allowed"] is False
    assert "TEST_ENTRYPOINT_NOT_BEHAVIOURAL" in result["errors"]


@pytest.mark.parametrize("action", ["modify", "promote", "cutover"])
def test_real_manifest_hard_lane_policies_are_behaviourally_tested(action: str) -> None:
    """Every hard-lane policy on main must pass the wiring check, or CI would block its files."""
    for policy in load_manifest()["policies"]:
        if policy["lane"] != "hard":
            continue
        assert check_enforcement_wiring(policy) == [], policy["policy_id"]
        result = check_lane_gate(policy["policy_id"], action)
        assert "TEST_ENTRYPOINT_NOT_BEHAVIOURAL" not in result["errors"], policy["policy_id"]
        assert "ENFORCEMENT_MODE_INVALID" not in result["errors"], policy["policy_id"]
