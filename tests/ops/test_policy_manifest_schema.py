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
BASELINE_LABEL = "1c9dce65"
# The entries frozen on 2026-06-15 before this repository's history begins; any
# policy added later must carry verified_in_pr and a real squash-merge commit.
BASELINE_FREEZE_IDS = frozenset({
    "P-ROUTE-01",
    "P-ROUTE-02",
    "P-ROUTE-03",
    "P-ROUTE-04",
    "P-BUDGET-01",
    "P-PLAN-01",
    "P-PLAN-02",
    "P-COST-01",
    "P-S2T-01",
    "P-S2T-02",
    "P-S2T-03",
    "P-GATE-01",
    "P-GATE-02",
    "P-GATE-03",
    "P-CLAIM-01",
    "P-CLAIM-02",
    "P-CLAIM-03",
    "P-DELIVERY-01",
    "P-DELIVERY-02",
    "P-LEARN-01",
    "P-LEARN-02",
    "P-AUTO-01",
    "P-BELIEF-01",
    "P-CTX-01",
    "P-SETTLE-01",
    "P-FLOW-01",
    "P-TEST-NODRILL-01",
})


def _policy(manifest: dict, policy_id: str) -> dict:
    return next(p for p in manifest["policies"] if p["policy_id"] == policy_id)


# ─── enforcement_mode ───────────────────────────────────────────────


def test_every_policy_declares_a_valid_enforcement_mode() -> None:
    manifest = load_manifest()
    assert "enforcement_mode" in manifest["schema"]["fields"]
    assert "enforcement_mode_policy" in manifest
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


def test_guard_modules_are_a_subset_of_source_file_and_present_for_multi_source() -> None:
    for policy in load_manifest()["policies"]:
        sources = gate._source_paths(policy)
        guards = set(policy.get("guard_modules") or [])
        assert guards <= set(sources), policy["policy_id"]
        if len(sources) > 1 and policy["enforcement_mode"] != "not_wired":
            assert guards, policy["policy_id"]


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


def _git(*args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _history_available() -> bool:
    shallow = _git("rev-parse", "--is-shallow-repository")
    return shallow is not None and shallow.returncode == 0 and shallow.stdout.strip() == "false"


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
            # Only the 2026-06-15 baseline-freeze label (pre-split history) may be unverified.
            assert policy["policy_id"] in BASELINE_FREEZE_IDS, policy["policy_id"]
            assert sha == BASELINE_LABEL and baseline.startswith(sha), policy["policy_id"]
            continue
        verified += 1
        assert isinstance(pr, int) and pr > 0, policy["policy_id"]
        assert FULL_SHA.match(sha), (policy["policy_id"], sha)
        if history:
            # The commit must be reachable from the checkout and be that PR's squash merge.
            ancestor = _git("merge-base", "--is-ancestor", sha, "HEAD")
            assert ancestor is not None and ancestor.returncode == 0, (policy["policy_id"], sha)
            subject = _git("log", "-1", "--format=%s", sha)
            assert subject is not None and f"(#{pr})" in subject.stdout, (policy["policy_id"], sha)
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
    assert check_enforcement_wiring(missing_file, root) == [
        "TEST_ENTRYPOINT_NOT_FOUND: tests/does_not_exist.py",
        "TEST_ENTRYPOINT_NOT_BEHAVIOURAL",
    ]
    # The named test must exist in the file; a file that merely imports the caller is
    # not an entrypoint.
    wrong_name = _fake_policy(test_entrypoints=["tests/test_caller.py::test_nope"])
    assert check_enforcement_wiring(wrong_name, root) == [
        "TEST_ENTRYPOINT_NOT_FOUND: tests/test_caller.py::test_nope",
        "TEST_ENTRYPOINT_NOT_BEHAVIOURAL",
    ]
    parametrized = _fake_policy(test_entrypoints=["tests/test_caller.py::test_run[1-2]"])
    assert check_enforcement_wiring(parametrized, root) == []
    colon_param = _fake_policy(test_entrypoints=["tests/test_caller.py::test_run[a::b]"])
    assert check_enforcement_wiring(colon_param, root) == []
    # Two unrelated top-level functions do not form a pytest node.
    (root / "tests" / "test_two.py").write_text(
        "from pkg import caller\n\ndef test_a():\n    assert caller\n\ndef test_b():\n    pass\n"
        "\nclass TestC:\n    def test_m(self):\n        pass\n",
        encoding="utf-8",
    )
    chained = _fake_policy(test_entrypoints=["tests/test_two.py::test_a::test_b"])
    assert check_enforcement_wiring(chained, root) == [
        "TEST_ENTRYPOINT_NOT_FOUND: tests/test_two.py::test_a::test_b",
        "TEST_ENTRYPOINT_NOT_BEHAVIOURAL",
    ]
    in_class = _fake_policy(test_entrypoints=["tests/test_two.py::TestC::test_m"])
    assert check_enforcement_wiring(in_class, root) == []
    wrong_class = _fake_policy(test_entrypoints=["tests/test_two.py::TestC::test_a"])
    assert check_enforcement_wiring(wrong_class, root) == [
        "TEST_ENTRYPOINT_NOT_FOUND: tests/test_two.py::TestC::test_a",
        "TEST_ENTRYPOINT_NOT_BEHAVIOURAL",
    ]
    # A caller named in source_file must exist inside the repo, even if a test imports it.
    (root / "tests" / "test_ghost.py").write_text(
        "from pkg import ghost\n\ndef test_g():\n    assert ghost\n", encoding="utf-8"
    )
    ghost = _fake_policy(
        source_file="pkg/guard.py; pkg/ghost.py", test_entrypoints=["tests/test_ghost.py::test_g"]
    )
    assert check_enforcement_wiring(ghost, root) == ["ENFORCEMENT_CALLER_NOT_FOUND: pkg.ghost"]
    # A stale entry is reported even when another entry reaches a caller.
    stale_plus_good = _fake_policy(
        test_entrypoints=["tests/test_caller.py::test_run", "tests/gone.py::test_x"]
    )
    assert check_enforcement_wiring(stale_plus_good, root) == [
        "TEST_ENTRYPOINT_NOT_FOUND: tests/gone.py::test_x"
    ]
    # Multi-source entries must say which files are the guard, otherwise the guard
    # itself would count as a production caller.
    no_guards = _fake_policy(guard_modules=[], test_entrypoints=["tests/test_guard_only.py"])
    assert check_enforcement_wiring(no_guards, root) == ["GUARD_MODULES_REQUIRED"]
    single = _fake_policy(
        source_file="pkg/caller.py", guard_modules=[], test_entrypoints=["tests/test_caller.py"]
    )
    assert check_enforcement_wiring(single, root) == []


def test_wiring_check_ignores_type_checking_and_relative_imports(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    (root / "tests" / "test_type_checking.py").write_text(
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from pkg.caller import run\n"
        "else:\n"
        "    from pkg.guard import check\n"
        "def test_x():\n    assert check(1)\n",
        encoding="utf-8",
    )
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests" / "helper.py").write_text("from pkg.caller import run\n", encoding="utf-8")
    (root / "tests" / "test_relative.py").write_text(
        "from .helper import run\n\ndef test_x():\n    assert run(1)\n", encoding="utf-8"
    )
    typed = _fake_policy(test_entrypoints=["tests/test_type_checking.py"])
    assert check_enforcement_wiring(typed, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"]
    # Relative imports are resolved against the file's package.
    relative = _fake_policy(test_entrypoints=["tests/test_relative.py"])
    assert check_enforcement_wiring(relative, root) == []
    (root / "tests" / "test_relative_guard.py").write_text(
        "from . import helper_guard\n\ndef test_x():\n    assert helper_guard\n", encoding="utf-8"
    )
    (root / "tests" / "helper_guard.py").write_text(
        "from pkg.guard import check\n", encoding="utf-8"
    )
    relative_guard = _fake_policy(test_entrypoints=["tests/test_relative_guard.py"])
    assert check_enforcement_wiring(relative_guard, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"]
    # Beyond the top-level package: Python would refuse it, so the walk ignores it.
    (root / "tests" / "test_beyond.py").write_text(
        "from ..pkg import caller\n\ndef test_x():\n    assert caller\n", encoding="utf-8"
    )
    beyond = _fake_policy(test_entrypoints=["tests/test_beyond.py"])
    assert check_enforcement_wiring(beyond, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"]


def test_wiring_check_keeps_paths_inside_the_repo(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    outside = tmp_path / "outside_test.py"
    outside.write_text(
        "from pkg import caller\n\ndef test_run():\n    assert caller\n", encoding="utf-8"
    )
    for entry in (str(outside), "../outside_test.py::test_run"):
        policy = _fake_policy(test_entrypoints=[entry])
        assert check_enforcement_wiring(policy, root) == [
            f"TEST_ENTRYPOINT_NOT_FOUND: {entry}",
            "TEST_ENTRYPOINT_NOT_BEHAVIOURAL",
        ]
    link = root / "tests" / "test_link.py"
    link.symlink_to(outside)
    linked = _fake_policy(test_entrypoints=["tests/test_link.py::test_run"])
    assert check_enforcement_wiring(linked, root) == [
        "TEST_ENTRYPOINT_NOT_FOUND: tests/test_link.py::test_run",
        "TEST_ENTRYPOINT_NOT_BEHAVIOURAL",
    ]


def test_hard_lane_not_wired_is_not_an_escape_hatch(monkeypatch) -> None:
    original = load_manifest()
    tampered = {
        **original,
        "policies": [
            {**p, "enforcement_mode": "not_wired"} if p["policy_id"] == "P-CONTAM-01" else p
            for p in original["policies"]
        ],
    }
    monkeypatch.setattr(gate, "load_manifest", lambda: tampered)
    for action in ("modify", "promote", "cutover"):
        result = check_lane_gate("P-CONTAM-01", action)
        assert result["allowed"] is False
        assert "HARD_LANE_NOT_WIRED" in result["errors"]
    assert check_lane_gate("P-CONTAM-01", "observe")["allowed"] is True


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
    # The production callers must exist under the tmp root (ENFORCEMENT_CALLER_NOT_FOUND
    # otherwise), so the verdict below is about the entrypoint, not the callers.
    for caller in (
        "nexus/app/research_flow_service.py",
        "nexus/core/capability_executor_registry.py",
    ):
        (tmp_path / caller).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / caller).write_text("", encoding="utf-8")
    original = load_manifest()
    tampered = {
        **original,
        "policies": [
            {**p, "test_entrypoints": ["test_guard_direct.py::test_direct"]}
            if p["policy_id"] == "P-CONTAM-01"
            else p
            for p in original["policies"]
        ],
    }
    monkeypatch.setattr(gate, "load_manifest", lambda: tampered)
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    assert gate.check_enforcement_wiring(_policy(tampered, "P-CONTAM-01")) == [
        "TEST_ENTRYPOINT_NOT_BEHAVIOURAL"
    ]
    result = check_lane_gate("P-CONTAM-01", "modify")
    assert result["allowed"] is False
    assert "TEST_ENTRYPOINT_NOT_BEHAVIOURAL" in result["errors"]

    # Positive control under the same tmp root: an entrypoint that reaches a production
    # caller is accepted, so the rejection above is about the guard-only import, not a
    # missing file.
    via_caller = tmp_path / "test_via_caller.py"
    via_caller.write_text(
        "def test_flow():\n"
        "    from nexus.app import research_flow_service\n"
        "    assert research_flow_service\n",
        encoding="utf-8",
    )
    accepted = {
        **tampered,
        "policies": [
            {**p, "test_entrypoints": ["test_via_caller.py::test_flow"]}
            if p["policy_id"] == "P-CONTAM-01"
            else p
            for p in tampered["policies"]
        ],
    }
    monkeypatch.setattr(gate, "load_manifest", lambda: accepted)
    assert gate.check_enforcement_wiring(_policy(accepted, "P-CONTAM-01")) == []
    assert check_lane_gate("P-CONTAM-01", "modify")["allowed"] is True


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
        if action == "modify" and policy["rollback_drill_status"] != "no-drill":
            # A drilled hard-lane policy must stay modifiable; relabelling it not_wired
            # or breaking its wiring would turn this red (and the lane workflow with it).
            assert result["allowed"] is True, (policy["policy_id"], result["errors"])
            assert policy["enforcement_mode"] in ("block", "record_only"), policy["policy_id"]


def test_drill_updater_keeps_schema_fields_and_distribution() -> None:
    from scripts.ops.update_manifest_drills import update_manifest

    manifest = load_manifest()
    updated = update_manifest(manifest)
    fixture = _policy(updated, "P-TEST-NODRILL-01")
    assert list(fixture) == list(_policy(manifest, "P-TEST-NODRILL-01"))
    assert fixture["enforcement_mode"] == "not_wired" and fixture["verified_in_pr"] is None
    assert (
        updated["summary"]["enforcement_mode_distribution"]
        == manifest["summary"]["enforcement_mode_distribution"]
    )
