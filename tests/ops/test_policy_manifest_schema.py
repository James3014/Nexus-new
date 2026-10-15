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
        "import pytest\nfrom pkg import caller\n\n"
        "@pytest.mark.parametrize('x', [1, 2])\ndef test_run(x):\n    assert caller.run(x)\n"
        "\ndef test_plain():\n    assert caller.run(1)\n",
        encoding="utf-8",
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
    # Rust-only: no import walk, but every declared file must exist inside the repo.
    (root / "core" / "src").mkdir(parents=True)
    (root / "core" / "src" / "guard.rs").write_text("// guard\n", encoding="utf-8")
    rust_only = _fake_policy(
        source_file="core/src/guard.rs",
        guard_modules=[],
        test_entrypoints=["core/src/guard.rs::tests"],
    )
    assert check_enforcement_wiring(rust_only, root) == []
    rust_missing_test = _fake_policy(
        source_file="core/src/guard.rs",
        guard_modules=[],
        test_entrypoints=["core/src/nope.rs::tests"],
    )
    assert check_enforcement_wiring(rust_missing_test, root) == [
        "TEST_ENTRYPOINT_NOT_FOUND: core/src/nope.rs::tests"
    ]
    rust_missing_source = _fake_policy(
        source_file="core/src/nope.rs",
        guard_modules=[],
        test_entrypoints=["core/src/guard.rs::tests"],
    )
    assert check_enforcement_wiring(rust_missing_source, root) == [
        "SOURCE_FILE_NOT_FOUND: core/src/nope.rs"
    ]
    # A non-Python entry alongside a Python one must still exist.
    pyx_missing = _fake_policy(
        test_entrypoints=["tests/test_caller.py::test_plain", "tests/nope.pyx"]
    )
    assert check_enforcement_wiring(pyx_missing, root) == [
        "TEST_ENTRYPOINT_NOT_FOUND: tests/nope.pyx"
    ]
    # ``file.py::`` (empty selector) and helpers that pytest does not collect are not nodes.
    (root / "tests" / "test_names.py").write_text(
        "from pkg import caller\n\ndef _run():\n    return caller\n\ndef helper_test():\n"
        "    pass\n\nclass Helper:\n    def test_m(self):\n        pass\n\nclass TestOk:\n"
        "    def test_m(self):\n        pass\n",
        encoding="utf-8",
    )
    for selector in ("", "_run", "helper_test", "Helper::test_m", "TestOk::_run"):
        bad = _fake_policy(test_entrypoints=[f"tests/test_names.py::{selector}"])
        assert check_enforcement_wiring(bad, root) == [
            f"TEST_ENTRYPOINT_NOT_FOUND: tests/test_names.py::{selector}",
            "TEST_ENTRYPOINT_NOT_BEHAVIOURAL",
        ], selector
    assert (
        check_enforcement_wiring(
            _fake_policy(test_entrypoints=["tests/test_names.py::TestOk::test_m"]), root
        )
        == []
    )
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
    # Parametrized ids cannot be resolved statically, so any [param] selector is refused;
    # the manifest lists the function instead.
    for selector in (
        "test_run[1-2]",
        "test_run[a::b]",
        "test_plain[1]",
        "test_run[]",
        "test_run[a]junk]",
        "test_run[a]::zz]",
    ):
        bad = _fake_policy(test_entrypoints=[f"tests/test_caller.py::{selector}"])
        assert check_enforcement_wiring(bad, root) == [
            f"TEST_ENTRYPOINT_NOT_FOUND: tests/test_caller.py::{selector}",
            "TEST_ENTRYPOINT_NOT_BEHAVIOURAL",
        ], selector
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
    assert check_enforcement_wiring(ghost, root) == ["SOURCE_FILE_NOT_FOUND: pkg/ghost.py"]
    # A declared file must exist as that file: pkg.py does not become pkg/__init__.py.
    (root / "tests" / "test_pkg.py").write_text(
        "import pkg\n\ndef test_p():\n    assert pkg\n", encoding="utf-8"
    )
    package_alias = _fake_policy(
        source_file="pkg/guard.py; pkg.py", test_entrypoints=["tests/test_pkg.py::test_p"]
    )
    assert check_enforcement_wiring(package_alias, root) == ["SOURCE_FILE_NOT_FOUND: pkg.py"]
    # Fixtures and classes are not tests; [param] ids are never accepted.
    (root / "tests" / "test_fx.py").write_text(
        "import pytest\nfrom pytest import fixture as fx\nfrom pkg import caller\n"
        "alias = pytest.fixture\n\n@pytest.fixture\ndef test_fx():\n    return caller\n"
        "\n@pytest.fixture()\ndef test_fx2():\n    return 1\n\n@fx\ndef test_fx3():\n    return 1\n"
        "\n@alias()\ndef test_fx4():\n    return 1\n\nclass TestK:\n    pass\n"
        "import pytest as pt\npt2 = pt\n\n@pt.fixture\ndef test_fx5():\n    return 1\n"
        "\n@pt2.fixture()\ndef test_fx6():\n    return 1\n"
        "\nclass Marker:\n    fx = staticmethod(lambda f: f)\n    fixture = fx\n"
        "\ndef test_ok():\n    assert caller\n"
        "\n@Marker.fx\ndef test_marked():\n    assert caller\n"
        "\n@Marker.fixture\ndef test_other_fixture():\n    assert caller\n",
        encoding="utf-8",
    )
    for selector in (
        "test_fx",
        "test_fx2",
        "test_fx3",
        "test_fx4",
        "test_fx5",
        "test_fx6",
        "TestK",
        "test_ok[a]::zzz",
        "test_ok[a",
        "::test_ok",
    ):
        bad = _fake_policy(test_entrypoints=[f"tests/test_fx.py::{selector}"])
        assert check_enforcement_wiring(bad, root) == [
            f"TEST_ENTRYPOINT_NOT_FOUND: tests/test_fx.py::{selector}",
            "TEST_ENTRYPOINT_NOT_BEHAVIOURAL",
        ], selector
    # Structural, not name-based: an unrelated decorator that happens to end in an alias
    # name (@Marker.fx) or in "fixture" (@other.fixture) is still a test.
    for selector in ("test_ok", "test_marked", "test_other_fixture"):
        good = _fake_policy(test_entrypoints=[f"tests/test_fx.py::{selector}"])
        assert check_enforcement_wiring(good, root) == [], selector
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
    # Every declared source file must exist under the tmp root (SOURCE_FILE_NOT_FOUND
    # otherwise), so the verdict below is about the entrypoint, not the sources.
    for source in (
        "nexus/app/research_flow_service.py",
        "nexus/core/capability_executor_registry.py",
        "nexus/research/contamination_guard.py",
        "nexus/research/contamination_enforcement.py",
        "nexus/research/research_facts.py",
    ):
        (tmp_path / source).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / source).write_text("", encoding="utf-8")
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


# The only hard-lane entry allowed to be undrilled / not_wired: the drill fixture that
# scripts/ops/update_manifest_drills.py maintains so the "blocked without drill" tests
# have a subject. Every other hard-lane policy must be drilled, wired and modifiable.
HARD_LANE_FIXTURE_IDS = frozenset({"P-TEST-NODRILL-01"})


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
        if policy["policy_id"] in HARD_LANE_FIXTURE_IDS:
            assert policy["enforcement_mode"] == "not_wired"
            continue
        # Not drilled, not wired, or blocked on modify: a real hard-lane policy must not be
        # any of these, so a manifest-only relabel (with or without a drill-status edit)
        # turns this red in the required gate and in the policy-lane workflow.
        assert gate._is_drilled(policy["rollback_drill_status"]), policy["policy_id"]
        assert policy["enforcement_mode"] in ("block", "record_only"), policy["policy_id"]
        if action == "modify":
            assert result["allowed"] is True, (policy["policy_id"], result["errors"])


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


@pytest.mark.parametrize(
    "status",
    [
        "no-drill",
        "",
        None,
        "not-drilled",
        "drilled",
        "drilled-2026-1-5",
        "drilled-2026-99-99",
        "drilled-2026-10-15\n",
        "drilled-\u0662\u0660\u0662\u0666-10-15",
        7,
    ],
)
def test_only_an_explicit_drill_date_counts_as_drilled(monkeypatch, status) -> None:
    original = load_manifest()
    tampered = {
        **original,
        "policies": [
            {**p, "rollback_drill_status": status} if p["policy_id"] == "P-GATE-03" else p
            for p in original["policies"]
        ],
    }
    monkeypatch.setattr(gate, "load_manifest", lambda: tampered)
    result = check_lane_gate("P-GATE-03", "modify")
    assert result["allowed"] is False
    assert "ROLLBACK_DRILL_MISSING" in result["errors"]


def test_wiring_check_scopes_imports_to_the_selected_test(tmp_path: Path) -> None:
    """Imports inside *other* functions of the file do not count for the selected test."""
    root = _fake_repo(tmp_path)
    (root / "tests" / "test_scoped.py").write_text(
        "def test_guard_only():\n    from pkg.guard import check\n    assert check(1)\n"
        "\ndef test_uses_caller():\n    from pkg import caller\n    assert caller.run(1)\n",
        encoding="utf-8",
    )
    guard_only = _fake_policy(test_entrypoints=["tests/test_scoped.py::test_guard_only"])
    assert check_enforcement_wiring(guard_only, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"]
    uses_caller = _fake_policy(test_entrypoints=["tests/test_scoped.py::test_uses_caller"])
    assert check_enforcement_wiring(uses_caller, root) == []
    whole_file = _fake_policy(test_entrypoints=["tests/test_scoped.py"])
    assert check_enforcement_wiring(whole_file, root) == []
    # A module-level import is visible to every test in the file (documented limit).
    (root / "tests" / "test_module_import.py").write_text(
        "from pkg import caller\n\ndef test_guard_only():\n    from pkg.guard import check\n"
        "    assert check(1)\n",
        encoding="utf-8",
    )
    module_level = _fake_policy(test_entrypoints=["tests/test_module_import.py::test_guard_only"])
    assert check_enforcement_wiring(module_level, root) == []


def test_fixture_bindings_cover_assignment_shapes_and_scope(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    (root / "tests" / "test_bind.py").write_text(
        "import pytest\nimport pytest_asyncio\nfrom pytest import *\nfrom pkg import caller\n"
        "fx, other = pytest.fixture, None\n"
        "fy: object = pytest.fixture\n"
        "\n@fx\ndef test_tuple():\n    return 1\n"
        "\n@fy()\ndef test_annotated():\n    return 1\n"
        "\n@pytest_asyncio.fixture\nasync def test_async_fixture():\n    return 1\n"
        "\n@fixture\ndef test_star():\n    return 1\n"
        "\ndef _helper():\n    from pytest import fixture as local_fx\n    return local_fx\n"
        "\nlocal_fx = lambda f: f\n"
        "\n@local_fx\ndef test_local_alias_is_still_a_test():\n    assert caller\n",
        encoding="utf-8",
    )
    for selector in ("test_tuple", "test_annotated", "test_async_fixture", "test_star"):
        bad = _fake_policy(test_entrypoints=[f"tests/test_bind.py::{selector}"])
        assert check_enforcement_wiring(bad, root) == [
            f"TEST_ENTRYPOINT_NOT_FOUND: tests/test_bind.py::{selector}",
            "TEST_ENTRYPOINT_NOT_BEHAVIOURAL",
        ], selector
    good = _fake_policy(test_entrypoints=["tests/test_bind.py::test_local_alias_is_still_a_test"])
    assert check_enforcement_wiring(good, root) == []


def test_wiring_check_round7_cases(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    # A caller import under a dead branch at module level does not count.
    for guard_text in ("from typing import TYPE_CHECKING\nif TYPE_CHECKING:", "if False:", "if 0:"):
        (root / "tests" / "test_dead.py").write_text(
            f"{guard_text}\n    from pkg import caller\n\n"
            "def test_guard_only():\n    from pkg.guard import check\n    assert check(1)\n",
            encoding="utf-8",
        )
        dead = _fake_policy(test_entrypoints=["tests/test_dead.py::test_guard_only"])
        assert check_enforcement_wiring(dead, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"], (
            guard_text
        )
        whole = _fake_policy(test_entrypoints=["tests/test_dead.py"])
        assert check_enforcement_wiring(whole, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"], (
            guard_text
        )
    # An empty source_file is not "no Python sources, nothing to check".
    assert check_enforcement_wiring(_fake_policy(source_file="", guard_modules=[]), root) == [
        "SOURCE_FILE_MISSING"
    ]
    assert check_enforcement_wiring(_fake_policy(source_file=" ; ", guard_modules=[]), root) == [
        "SOURCE_FILE_MISSING"
    ]
    # A whole-file entry must be a test_*.py file with at least one collectable test.
    (root / "tests" / "test_empty.py").write_text(
        "from pkg import caller\n\ndef helper():\n    return caller\n", encoding="utf-8"
    )
    (root / "tests" / "test_only_fixture.py").write_text(
        "import pytest\nfrom pkg import caller\n\n@pytest.fixture\ndef test_fx():\n    return caller\n",
        encoding="utf-8",
    )
    for entry in (
        "pkg/shim.py",
        "tests/helper.py",
        "tests/test_empty.py",
        "tests/test_only_fixture.py",
    ):
        not_a_test_file = _fake_policy(test_entrypoints=[entry])
        assert check_enforcement_wiring(not_a_test_file, root) == [
            f"TEST_ENTRYPOINT_NOT_FOUND: {entry}",
            "TEST_ENTRYPOINT_NOT_BEHAVIOURAL",
        ], entry
    (root / "tests" / "test_in_class.py").write_text(
        "class TestK:\n    def test_m(self):\n        pass\n", encoding="utf-8"
    )
    assert check_enforcement_wiring(
        _fake_policy(test_entrypoints=["tests/test_in_class.py"]), root
    ) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"]
    # Class-level imports are visible to the class's tests.
    (root / "tests" / "test_class_import.py").write_text(
        "class TestWiring:\n    from pkg import caller\n\n    def test_caller(self):\n"
        "        assert self.caller\n\n    def helper(self):\n        from pkg.guard import check\n"
        "        return check\n",
        encoding="utf-8",
    )
    in_class = _fake_policy(
        test_entrypoints=["tests/test_class_import.py::TestWiring::test_caller"]
    )
    assert check_enforcement_wiring(in_class, root) == []


def test_wiring_check_round8_cases(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    # A whole-file entry is the union of its collectable tests: an unused helper that
    # imports the caller does not count.
    (root / "tests" / "test_helper_only.py").write_text(
        "def helper():\n    from pkg import caller\n    return caller\n\n"
        "def test_guard():\n    from pkg.guard import check\n    assert check(1)\n",
        encoding="utf-8",
    )
    helper_only = _fake_policy(test_entrypoints=["tests/test_helper_only.py"])
    assert check_enforcement_wiring(helper_only, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"]
    (root / "tests" / "test_one_reaches.py").write_text(
        "def test_guard():\n    from pkg.guard import check\n    assert check(1)\n\n"
        "class TestK:\n    def test_c(self):\n        from pkg import caller\n        assert caller\n",
        encoding="utf-8",
    )
    one_reaches = _fake_policy(test_entrypoints=["tests/test_one_reaches.py"])
    assert check_enforcement_wiring(one_reaches, root) == []
    # The else of "if not TYPE_CHECKING:" and of "if True:" never runs; the else of
    # "if TYPE_CHECKING:" always does.
    cases = {
        "from typing import TYPE_CHECKING\nif not TYPE_CHECKING:\n    pass\nelse:\n"
        "    from pkg import caller\n": ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"],
        "if True:\n    pass\nelse:\n    from pkg import caller\n": [
            "TEST_ENTRYPOINT_NOT_BEHAVIOURAL"
        ],
        "if 1:\n    pass\nelse:\n    from pkg import caller\n": ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"],
        "import typing\nif typing.TYPE_CHECKING:\n    pass\nelse:\n    from pkg import caller\n": [],
        "from typing import TYPE_CHECKING\nif not TYPE_CHECKING:\n    from pkg import caller\n": [],
        "import os\nif os.environ.get('X'):\n    from pkg import caller\n": [],
    }
    for prefix, expected in cases.items():
        (root / "tests" / "test_branch.py").write_text(
            prefix + "\ndef test_guard():\n    from pkg.guard import check\n    assert check(1)\n",
            encoding="utf-8",
        )
        policy = _fake_policy(test_entrypoints=["tests/test_branch.py::test_guard"])
        assert check_enforcement_wiring(policy, root) == expected, prefix


def test_wiring_check_round9_cases(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    # A live branch must not smuggle def bodies past the scoping filter.
    (root / "tests" / "test_live_def.py").write_text(
        "if True:\n    def unused_helper():\n        from pkg import caller\n        return caller\n"
        "\ndef test_guard():\n    from pkg.guard import check\n    assert check(1)\n",
        encoding="utf-8",
    )
    for entry in ("tests/test_live_def.py::test_guard", "tests/test_live_def.py"):
        policy = _fake_policy(test_entrypoints=[entry])
        assert check_enforcement_wiring(policy, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"], entry
    (root / "tests" / "test_live_import.py").write_text(
        "if True:\n    from pkg import caller\n"
        "\ndef test_guard():\n    from pkg.guard import check\n    assert check(1) and caller\n",
        encoding="utf-8",
    )
    live_import = _fake_policy(test_entrypoints=["tests/test_live_import.py::test_guard"])
    assert check_enforcement_wiring(live_import, root) == []
    # A helper module reached by the walk is scanned whole even if its name starts with
    # test_ (the union rule applies to the entrypoint file only).
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests" / "test_helpers_mod.py").write_text(
        "from pkg import caller\n\ndef make():\n    return caller\n", encoding="utf-8"
    )
    (root / "tests" / "test_uses_helper_mod.py").write_text(
        "from tests import test_helpers_mod\n\ndef test_x():\n    assert test_helpers_mod.make()\n",
        encoding="utf-8",
    )
    via_helper_mod = _fake_policy(test_entrypoints=["tests/test_uses_helper_mod.py::test_x"])
    assert check_enforcement_wiring(via_helper_mod, root) == []


def test_wiring_check_round10_cases(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    # A helper nested inside the selected test does not count.
    (root / "tests" / "test_nested.py").write_text(
        "def test_guard():\n    def unused():\n        from pkg import caller\n"
        "        return caller\n    from pkg.guard import check\n    assert check(1)\n",
        encoding="utf-8",
    )
    for entry in ("tests/test_nested.py::test_guard", "tests/test_nested.py"):
        policy = _fake_policy(test_entrypoints=[entry])
        assert check_enforcement_wiring(policy, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"], entry
    # Imports inside a with/try/for block of the test body still count.
    (root / "tests" / "test_block.py").write_text(
        "def test_guard():\n    try:\n        from pkg import caller\n    except ImportError:\n"
        "        caller = None\n    assert caller\n",
        encoding="utf-8",
    )
    assert (
        check_enforcement_wiring(
            _fake_policy(test_entrypoints=["tests/test_block.py::test_guard"]), root
        )
        == []
    )
    # An import cycle back into the entrypoint file must not rescan it whole.
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests" / "loop_helper.py").write_text("import tests.test_loop\n", encoding="utf-8")
    (root / "tests" / "test_loop.py").write_text(
        "import tests.loop_helper\n\ndef _unused():\n    from pkg import caller\n    return caller\n"
        "\ndef test_loop():\n    from pkg.guard import check\n    assert check(1)\n",
        encoding="utf-8",
    )
    for entry in ("tests/test_loop.py::test_loop", "tests/test_loop.py"):
        policy = _fake_policy(test_entrypoints=[entry])
        assert check_enforcement_wiring(policy, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"], entry


def test_wiring_check_guard_alias_via_symlink_is_still_a_guard(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    # The guard imports the caller (circular helper); an alias to the guard file must
    # not let the walk pass through the guard.
    (root / "pkg" / "guard.py").write_text(
        "from pkg import caller\n\ndef check(x):\n    return bool(x) and caller\n", encoding="utf-8"
    )
    (root / "pkg" / "alias.py").symlink_to(root / "pkg" / "guard.py")
    (root / "tests" / "test_alias.py").write_text(
        "def test_a():\n    from pkg.alias import check\n    assert check(1)\n", encoding="utf-8"
    )
    via_alias = _fake_policy(test_entrypoints=["tests/test_alias.py::test_a"])
    assert check_enforcement_wiring(via_alias, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"]
    direct = _fake_policy(test_entrypoints=["tests/test_guard_only.py::test_guard"])
    assert check_enforcement_wiring(direct, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"]
    # A second declared path that is a copy (not the guard) is still a caller.
    assert (
        check_enforcement_wiring(
            _fake_policy(test_entrypoints=["tests/test_caller.py::test_plain"]), root
        )
        == []
    )


def test_wiring_check_guard_identity_round12(tmp_path: Path) -> None:
    import os

    root = _fake_repo(tmp_path)
    (root / "pkg" / "guard.py").write_text(
        "from pkg import caller\n\ndef check(x):\n    return bool(x) and caller\n", encoding="utf-8"
    )
    (root / "pkg" / "alias.py").symlink_to(root / "pkg" / "guard.py")
    # The symlink is declared as the guard and the real path as a "caller": the real
    # path is physically the guard, so it is not a caller and the test is guard-only.
    swapped = _fake_policy(
        source_file="pkg/alias.py; pkg/guard.py",
        guard_modules=["pkg/alias.py"],
        test_entrypoints=["tests/test_guard_only.py::test_guard"],
    )
    assert check_enforcement_wiring(swapped, root) == ["ENFORCEMENT_CALLERS_MISSING"]
    # A hard link to the guard is the guard too.
    os.link(root / "pkg" / "guard.py", root / "pkg" / "hard.py")
    (root / "tests" / "test_hard.py").write_text(
        "def test_h():\n    from pkg.hard import check\n    assert check(1)\n", encoding="utf-8"
    )
    via_hardlink = _fake_policy(test_entrypoints=["tests/test_hard.py::test_h"])
    assert check_enforcement_wiring(via_hardlink, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"]
    # A caller import whose file is physically a guard does not count as reaching a caller.
    os.link(root / "pkg" / "guard.py", root / "pkg" / "caller2.py")
    (root / "tests" / "test_c2.py").write_text(
        "def test_c():\n    from pkg import caller2\n    assert caller2\n", encoding="utf-8"
    )
    fake_caller = _fake_policy(
        source_file="pkg/guard.py; pkg/caller2.py; pkg/caller.py",
        test_entrypoints=["tests/test_c2.py::test_c"],
    )
    assert check_enforcement_wiring(fake_caller, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"]
    # The genuine caller still passes.
    assert (
        check_enforcement_wiring(
            _fake_policy(test_entrypoints=["tests/test_caller.py::test_plain"]), root
        )
        == []
    )


def test_wiring_check_package_guard_and_stat_failure(tmp_path: Path, monkeypatch) -> None:
    root = _fake_repo(tmp_path)
    # A guard declared as a package __init__ guards every module beneath it: importing
    # pkg.caller loads pkg/__init__.py first, so the route is not guard-free.
    (root / "pkg" / "__init__.py").write_text("from pkg import caller\n", encoding="utf-8")
    package_guard = _fake_policy(
        source_file="pkg/__init__.py; pkg/caller.py",
        guard_modules=["pkg/__init__.py"],
        test_entrypoints=["tests/test_caller.py::test_plain"],
    )
    assert check_enforcement_wiring(package_guard, root) == [
        "CALLER_UNDER_GUARD_PACKAGE: pkg/caller.py"
    ]
    # An unreadable guard fails closed rather than losing its identity. The fault is
    # injected at _file_id (the identity lookup) rather than Path.stat, because other
    # pathlib calls use stat differently per platform (Linux CI raised through resolve()).
    real_file_id = gate._file_id

    def unreadable_guard(path):
        if path.name == "guard.py":
            return None
        return real_file_id(path)

    monkeypatch.setattr(gate, "_file_id", unreadable_guard)
    result = check_enforcement_wiring(
        _fake_policy(test_entrypoints=["tests/test_caller.py::test_plain"]), root
    )
    assert result == ["SOURCE_FILE_NOT_FOUND: pkg/guard.py"]


def test_wiring_check_round14_cases(tmp_path: Path, monkeypatch) -> None:
    root = _fake_repo(tmp_path)
    # A package __init__ declared as the caller is credited when a child is imported.
    (root / "app").mkdir()
    (root / "app" / "__init__.py").write_text("from pkg.guard import check\n", encoding="utf-8")
    (root / "app" / "svc.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    (root / "tests" / "test_app_child.py").write_text(
        "def test_c():\n    from app import svc\n    assert svc.run()\n", encoding="utf-8"
    )
    pkg_caller = _fake_policy(
        source_file="pkg/guard.py; app/__init__.py",
        test_entrypoints=["tests/test_app_child.py::test_c"],
    )
    assert check_enforcement_wiring(pkg_caller, root) == []
    # A caller beneath a guard package is reported as such, not as a silent failure.
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    under_guard = _fake_policy(
        source_file="pkg/__init__.py; pkg/caller.py",
        guard_modules=["pkg/__init__.py"],
        test_entrypoints=["tests/test_caller.py::test_plain"],
    )
    assert check_enforcement_wiring(under_guard, root) == [
        "CALLER_UNDER_GUARD_PACKAGE: pkg/caller.py"
    ]
    # A guard package whose __init__ exists but cannot be resolved is still a guard.
    (root / "gp").mkdir()
    (root / "gp" / "__init__.py").symlink_to(root / "pkg" / "guard.py")  # alias of the guard
    (root / "gp" / "child.py").write_text("from pkg import caller\n", encoding="utf-8")
    (root / "tests" / "test_gp.py").write_text(
        "def test_g():\n    from gp import child\n    assert child\n", encoding="utf-8"
    )
    via_alias_pkg = _fake_policy(test_entrypoints=["tests/test_gp.py::test_g"])
    assert check_enforcement_wiring(via_alias_pkg, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"]
    real_resolve = Path.resolve

    def flaky_resolve(self, *args, **kwargs):
        if self.name == "__init__.py" and self.parent.name == "gp":
            raise OSError("transient")
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", flaky_resolve)
    assert check_enforcement_wiring(via_alias_pkg, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"]


def test_wiring_check_round15_cases(tmp_path: Path, monkeypatch) -> None:
    import os

    root = _fake_repo(tmp_path)
    # A caller package whose child is the guard: importing the guard child executes
    # the caller package first, so the route reaches the caller.
    (root / "app").mkdir()
    (root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "g.py").write_text("def check(x):\n    return bool(x)\n", encoding="utf-8")
    (root / "tests" / "test_child_guard.py").write_text(
        "def test_x():\n    from app.g import check\n    assert check(1)\n", encoding="utf-8"
    )
    caller_pkg = _fake_policy(
        source_file="app/g.py; app/__init__.py",
        guard_modules=["app/g.py"],
        test_entrypoints=["tests/test_child_guard.py::test_x"],
    )
    # Refused up front: a caller package containing the guard would let a guard-only
    # test pass. The manifest must name a concrete caller module.
    assert check_enforcement_wiring(caller_pkg, root) == [
        "GUARD_UNDER_CALLER_PACKAGE: app/__init__.py"
    ]
    # A guard package above a caller still wins (route goes through the guard).
    (root / "gp").mkdir()
    (root / "gp" / "__init__.py").symlink_to(root / "pkg" / "guard.py")
    (root / "gp" / "child.py").write_text("from pkg import caller\n", encoding="utf-8")
    (root / "tests" / "test_gp2.py").write_text(
        "def test_g():\n    from gp import child\n    assert child\n", encoding="utf-8"
    )
    via_guard_pkg = _fake_policy(test_entrypoints=["tests/test_gp2.py::test_g"])
    assert check_enforcement_wiring(via_guard_pkg, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"]
    # An lstat error on the prefix's __init__ counts as present (fail closed).
    real_lstat = os.lstat

    def flaky_lstat(path, *args, **kwargs):
        if str(path).endswith("gp/__init__.py"):
            raise PermissionError("transient")
        return real_lstat(path, *args, **kwargs)

    real_resolve = Path.resolve

    def flaky_resolve(self, *args, **kwargs):
        if self.name == "__init__.py" and self.parent.name == "gp":
            raise OSError("transient")
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", flaky_lstat)
    monkeypatch.setattr(Path, "resolve", flaky_resolve)
    assert check_enforcement_wiring(via_guard_pkg, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"]


def test_wiring_check_round16_cases(tmp_path: Path, monkeypatch) -> None:
    root = _fake_repo(tmp_path)
    policy = _fake_policy(test_entrypoints=["tests/test_caller.py::test_plain"])
    assert check_enforcement_wiring(policy, root) == []
    # A declared caller that stops resolving during the walk is not credited by name.
    real_module_file = gate._module_file

    def flaky_module_file(module, repo_root):
        if module == "pkg.caller":
            return None
        return real_module_file(module, repo_root)

    monkeypatch.setattr(gate, "_module_file", flaky_module_file)
    assert check_enforcement_wiring(policy, root) == ["TEST_ENTRYPOINT_NOT_BEHAVIOURAL"]
    monkeypatch.setattr(gate, "_module_file", real_module_file)
    # A declared caller whose resolved file turns out to be the guard is a guard.
    real_file_id = gate._file_id
    guard_id = real_file_id(root / "pkg" / "guard.py")

    def swapped_file_id(path):
        if path.name == "caller.py":
            return guard_id
        return real_file_id(path)

    monkeypatch.setattr(gate, "_file_id", swapped_file_id)
    assert check_enforcement_wiring(policy, root) == ["ENFORCEMENT_CALLERS_MISSING"]
