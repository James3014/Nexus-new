"""Issue #2795: macOS physical witnesses for the sandboxed EIA closure verifier.

``_run_verifier_specs`` runs each pytest verifier under real ``sandbox-exec`` with the
``nexus.engine.sandboxed_lane`` profile it builds.  These witnesses check, from inside
the verifier child, that network is denied and that writes outside the work tree and
the per-run child dir (the parent's evidence and trusted dirs, the tree's ``.git``, any
other path) are refused while normal pytest (tmp_path, TMPDIR, HOME) still works; that
the fake-pass routes stay not passed under the real sandbox; and that an honest
candidate, including the read-only base-run skip comparison, still passes.

Collection rule (same as the DSH, agy dispatch and sandbox runner witnesses, #1607):
where Seatbelt cannot run, the witnesses are bound to ``None`` so pytest collects
nothing, never a skip that could be mistaken for evidence.  Only the macOS job
``dsh-seatbelt-physical-witness`` collects them, and
``scripts/ci/verify_physical_witness_junit.py verify --suite eia-closure-verifier``
fails closed unless exactly these three nodes PASSED.
"""

from __future__ import annotations

import ast
import os
import shutil
import socket
import sys
from pathlib import Path

from nexus.services.external_intelligence_closure import (
    VERIFIER_FOREIGN_PLUGIN,
    VERIFIER_JUNIT_FAILURES,
    VERIFIER_JUNIT_SKIPPED,
    VERIFIER_PYTEST_INTERNALS_PATCHED,
)
from tests.services.test_external_intelligence_closure_out_of_process_2795 import (
    _FORGE_REPORT_FILE,
    _HONEST_SHAPES,
    _MAKEREPORT_PLUGIN,
    _PATCH_FROM_ITEM_AND_CALL,
    _SKIP_SOURCES,
    _TEST_KEEP,
    _TEST_NEEDS_TWO,
    _repo,
    _row,
    _spec,
)

SEATBELT_AVAILABLE = sys.platform == "darwin" and shutil.which("sandbox-exec") is not None
PHYSICAL_WITNESSES = (
    "test_sandboxed_verifier_denies_network_and_writes_outside_its_dirs",
    "test_fake_pass_routes_stay_not_passed_under_real_sandbox_exec",
    "test_honest_candidate_and_base_run_pass_under_real_sandbox_exec",
)

# Runs INSIDE the sandboxed verifier.  Every test passes only if the sandbox holds.
_PROBE_TEMPLATE = """\
import errno
import os
import socket
from pathlib import Path

PORT = {port}
OUTSIDE = Path({outside!r})


def _denied(action):
    try:
        action()
    except PermissionError:
        return True
    except OSError as exc:
        return exc.errno in (errno.EPERM, errno.EACCES)
    return False


def _append(path):
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("planted-2795")


def test_network_is_denied():
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(5)
    try:
        assert _denied(lambda: probe.connect(("127.0.0.1", PORT)))
    finally:
        probe.close()


def test_writes_outside_the_tree_and_child_dir_are_denied():
    run = Path(os.environ["TMPDIR"]).parents[1]
    for target in (
        run / "evidence" / "junit.xml",
        run / "trusted" / "_nexus_eia_verifier_witness.py",
        run / "trusted" / "pytest.ini",
        Path.cwd() / ".git" / "config",
        Path.cwd() / ".git" / "planted-2795",
        OUTSIDE,
    ):
        assert _denied(lambda t=target: _append(t)), target
    for source, dest in (
        (run / "evidence", run / "evidence-moved"),
        (run / "child", run / "child-moved"),
        (Path.cwd(), Path.cwd().with_name("tree-moved-2795")),
    ):
        assert _denied(lambda s=source, d=dest: os.rename(s, d)), source


def test_normal_pytest_writes_still_work(tmp_path):
    (tmp_path / "ok.txt").write_text("ok", encoding="utf-8")
    Path(os.environ["TMPDIR"], "ok.txt").write_text("ok", encoding="utf-8")
    Path(os.environ["HOME"], "ok.txt").write_text("ok", encoding="utf-8")
    in_tree = Path.cwd() / "probe-2795.txt"
    in_tree.write_text("ok", encoding="utf-8")
    in_tree.unlink()
"""


def physical_seatbelt_witness(func, *, available: bool = SEATBELT_AVAILABLE):
    """Expose a physical witness as a test node only where Seatbelt can run."""
    return func if available else None


def test_witness_nodes_are_declared_and_darwin_ci_must_collect_them():
    """Always collected (Linux included), so the impact gate sees a passing node."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    declared = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(d, ast.Name) and d.id == "physical_seatbelt_witness"
            for d in node.decorator_list
        )
    }
    assert declared == set(PHYSICAL_WITNESSES)
    for name in PHYSICAL_WITNESSES:
        assert (globals().get(name) is not None) is SEATBELT_AVAILABLE
    if os.environ.get("CI") and sys.platform == "darwin":
        assert SEATBELT_AVAILABLE, "macOS CI host has no sandbox-exec"


@physical_seatbelt_witness
def test_sandboxed_verifier_denies_network_and_writes_outside_its_dirs(tmp_path):
    outside = tmp_path / "outside-2795.txt"
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        probe = _PROBE_TEMPLATE.format(port=listener.getsockname()[1], outside=str(outside))
        root, base, cand = _repo(tmp_path, {"tests/test_probe.py": probe})
        row = _row(root, base, cand, _spec("tests/test_probe.py"), ["tests"])
    finally:
        listener.close()
    assert row["sandbox"]["sandboxed"] is True
    assert row["sandbox"]["barrier"] == "macos_sandbox_exec"
    assert row["sandbox"]["network"] == "denied"
    assert row["passed"] is True, row
    assert row["junit"]["tests"] == 3
    assert not outside.exists()
    assert "planted-2795" not in (root / ".git" / "config").read_text(encoding="utf-8")
    assert not (root / ".git" / "planted-2795").exists()


@physical_seatbelt_witness
def test_fake_pass_routes_stay_not_passed_under_real_sandbox_exec(tmp_path):
    cases = {
        "forge_report": ({"src_mod.py": _FORGE_REPORT_FILE}, ["src_mod.py"], "tests/test_mod.py"),
        "patch_reports": (
            {"src_mod.py": _PATCH_FROM_ITEM_AND_CALL},
            ["src_mod.py"],
            "tests/test_mod.py",
        ),
        "pytest_plugins": (
            {
                "evil_plugin_2795.py": _MAKEREPORT_PLUGIN,
                "tests/test_mod.py": "pytest_plugins = ['evil_plugin_2795']\n" + _TEST_NEEDS_TWO,
            },
            ["evil_plugin_2795.py", "tests/test_mod.py"],
            "tests/test_mod.py",
        ),
        "skip_item_location": (
            {
                "src_mod.py": _SKIP_SOURCES["skip_exception_item_location"],
                "tests/test_keep.py": _TEST_KEEP,
            },
            ["src_mod.py", "tests/test_keep.py"],
            "tests/test_keep.py",
        ),
    }
    expected = {
        "forge_report": VERIFIER_JUNIT_FAILURES,
        "patch_reports": VERIFIER_PYTEST_INTERNALS_PATCHED,
        "pytest_plugins": VERIFIER_FOREIGN_PLUGIN,
        "skip_item_location": VERIFIER_JUNIT_SKIPPED,
    }
    for name, (files, authorized, target) in cases.items():
        case_dir = tmp_path / name
        case_dir.mkdir()
        # test_keep.py is new at the candidate here, so the base run has no such node.
        root, base, cand = _repo(case_dir, files)
        row = _row(root, base, cand, _spec(target), authorized)
        assert row["sandbox"]["sandboxed"] is True, name
        assert row["passed"] is False, (name, row)
        assert row["error"] == expected[name], (name, row)


@physical_seatbelt_witness
def test_honest_candidate_and_base_run_pass_under_real_sandbox_exec(tmp_path):
    optional = (
        "import pytest\n\npytest.importorskip('nonexistent_mod_2795')\n\n\n"
        "def test_optional():\n    assert True\n"
    )
    root, base, cand = _repo(
        tmp_path,
        {"src_mod.py": "VALUE = 2\n", "tests/test_shapes.py": _HONEST_SHAPES},
        base={"pytest.ini": "[pytest]\nasyncio_mode = auto\n", "tests/test_optional.py": optional},
    )
    row = _row(root, base, cand, _spec("tests"), ["src_mod.py", "tests"])
    assert row["passed"] is True, row
    assert row["sandbox"]["sandboxed"] is True
    assert row["base_run"]["ran"] is True
    assert row["base_run"]["sandboxed"] is True
    assert row["junit"]["skipped_at_base"] == ["tests.test_optional"]
    assert row["junit"]["tests"] == 10
