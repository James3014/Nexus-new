"""Fixture tests and self-checks for the #1216 real-outcome scorer (spec §11)."""

from __future__ import annotations

import base64
import contextlib
import dataclasses
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from nexus.engine import sandboxed_lane
from nexus.research import real_outcome_scorer as ros

ADD_TEST = "from pkg.calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
MUL_TEST = (
    "from pkg.calc import mul\n\n\ndef test_mul():\n    assert mul(2, 3) == 6\n\n\n"
    "def test_mul_zero():\n    assert mul(0, 3) == 0\n\n\n"
    "def test_mul_neg():\n    assert mul(-2, 3) == -6\n"
)
BUGGY = "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a + b\n"
FIXED = "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"


def _git(cwd: Path, *args: str, input: bytes | None = None) -> str:
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": "/usr/bin:/bin",
        "HOME": str(cwd),
    }
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, input=input, env=env
    ).stdout.decode()


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)


class Fixture:
    """Upstream repo: BASE, then main moves (README), then the human fix commit."""

    def __init__(
        self,
        tmp: Path,
        repo_name: str = "fixture-repo",
        gate: str | None = None,
        mul_test: str = MUL_TEST,
        extra_base: dict[str, str] | None = None,
    ):
        self.tmp = tmp
        self.repo_name = repo_name
        self.upstream = tmp / "upstream"
        self.upstream.mkdir()
        _git(self.upstream, "init", "-q")
        files = {
            "pkg/__init__.py": "",
            "pkg/calc.py": BUGGY,
            "tests/test_add.py": ADD_TEST,
            "README.md": "base\n",
            **(extra_base or {}),
        }
        if gate:
            files["scripts/ops/pr_impact_gate.py"] = gate
        _write(self.upstream, files)
        _git(self.upstream, "add", "-A")
        _git(self.upstream, "commit", "-qm", "base")
        self.base = _git(self.upstream, "rev-parse", "HEAD").strip()
        _write(self.upstream, {"README.md": "main moved\n"})
        _git(self.upstream, "commit", "-qam", "drift")
        _write(self.upstream, {"pkg/calc.py": FIXED, "tests/test_mul.py": mul_test})
        _git(self.upstream, "add", "-A")
        _git(self.upstream, "commit", "-qm", "human fix")
        self.fix = _git(self.upstream, "rev-parse", "HEAD").strip()
        self.gold_diff = _git(self.upstream, "diff", "--binary", f"{self.fix}^1", self.fix).encode()
        _write(self.upstream, {"docs/x.md": "doc\n"})
        _git(self.upstream, "add", "-A")
        _git(self.upstream, "commit", "-qm", "docs only")
        self.docs_commit = _git(self.upstream, "rev-parse", "HEAD").strip()
        self.store = tmp / "store"
        self.n = 0

    def diff_from_base(self, files: dict[str, str]) -> bytes:
        wt = self.tmp / f"scratch{self.n}"
        self.n += 1
        _git(self.upstream, "worktree", "add", "-q", "--detach", str(wt), self.base)
        _write(wt, files)
        return _git(wt, "diff", "--binary", "HEAD").encode()

    def task(
        self,
        diff: bytes = b"",
        untracked: dict[str, str] | None = None,
        status: str = "VALID",
        terminal: str | None = "CLOSED_WITH_MERGED_PR",
        merge: str | None = None,
        number: int | None = None,
    ) -> Path:
        self.n += 1
        key = f"James3014__{self.repo_name}--{number or self.n}"
        d = self.store / "tasks" / key
        d.mkdir(parents=True)
        so = {
            "status": status,
            "scope_valid": True,
            "failure_kind": None,
            "diff_gzip_base64": base64.b64encode(gzip.compress(diff, mtime=0)).decode(),
            "diff_sha256": hashlib.sha256(diff).hexdigest(),
            "untracked_files": [],
        }
        for path, text in (untracked or {}).items():
            data = text.encode()
            so["untracked_files"].append({
                "path": path,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "gzip_base64": base64.b64encode(gzip.compress(data, mtime=0)).decode(),
            })
        raw = {
            "route": "B",
            "wall_time_seconds": 120.0,
            "raw_response": {
                "candidate_packet": {"source_revision": self.base},
                "strong_online_timeout_seconds": 1800,
                "strong_online_raw_response": so,
            },
        }
        raw_bytes = json.dumps(raw).encode()
        (d / "raw.json").write_bytes(raw_bytes)
        seal = {
            "path": "raw.json",
            "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "schema": "nexus.hybrid_replication.raw_seal.v1",
        }
        (d / "raw_seal.json").write_text(json.dumps(seal))
        state = {"raw_seal": seal, "phase": "RAW_SEALED", "ground_truth": None}
        if terminal:
            prs = (
                []
                if terminal != "CLOSED_WITH_MERGED_PR"
                else [
                    {
                        "number": 7,
                        "merge_commit_sha": merge or self.fix,
                        "head_sha": merge or self.fix,
                        "merged_at": "2026-10-12T00:00:00Z",
                    }
                ]
            )
            gt = {"details": {"merged_prs": prs}, "terminal_state": terminal}
            gt_bytes = json.dumps(gt).encode()
            (d / "ground_truth.json").write_bytes(gt_bytes)
            state["ground_truth"] = {"sha256": hashlib.sha256(gt_bytes).hexdigest(), **gt}
            state["phase"] = "SCORED"
        (d / "state.json").write_text(json.dumps(state))
        return d


class LocalEnv:
    """Runs fixture trees with this interpreter and its import roots.

    Some CI executors run a system Python with packages supplied via PYTHONPATH, which the
    scorer's hermetic env would otherwise drop.
    """

    def get(self, repo: str, base_wt: Path) -> ros.TestEnv:
        repo_root = Path(__file__).resolve().parents[2]
        roots = tuple(
            p for p in sys.path if p and Path(p).is_dir() and Path(p).resolve() != repo_root
        )
        return ros.TestEnv("fixture-env", sys.executable, "fixture", extra_pythonpath=roots)


def _ctx(tmp: Path, fx: Fixture, work: str = "work") -> ros.ScoreContext:
    w = tmp / work
    return ros.ScoreContext(
        work=w,
        env_provider=LocalEnv(),
        runner=ros.PytestRunner(w / "scratch", timeout=300, log=lambda m: None),
        repo_sources={fx.repo_name: [str(fx.upstream)]},
        spec_sha256="0" * 64,
        spec_v2_sha256="2" * 64,
        log=lambda m: None,
    )


@pytest.fixture()
def fx(tmp_path: Path) -> Fixture:
    return Fixture(tmp_path)


def _score(tmp: Path, fx: Fixture, task: Path, **kw):
    return ros.score_task(task, _ctx(tmp, fx), **kw)["receipt"]


def test_oracle_file_classification():
    assert ros.is_oracle_test_file("tests/a/b.py")
    assert ros.is_oracle_test_file("pkg/tests/data.json")
    assert ros.is_oracle_test_file("pkg/test_x.py")
    assert ros.is_oracle_test_file("pkg/x_test.py")
    assert ros.is_oracle_test_file("conftest.py")
    assert not ros.is_oracle_test_file("pkg/testing.py")
    assert not ros.is_oracle_test_file("docs/tests.md")
    assert ros.is_oracle_module_name("tests/test_x.py")
    assert not ros.is_oracle_module_name("tests/conftest.py")


def test_human_fix_scores_resolved(tmp_path, fx):
    r = _score(tmp_path, fx, fx.task(fx.gold_diff))
    assert r["label"] == ros.RESOLVED
    assert r["f2p_total"] == 3
    assert r["f2p_pass"] == r["f2p_total"]
    assert r["p2p_new_failures"] == []
    assert r["oracle_test_files"] == ["tests/test_mul.py"]
    assert r["trees"]["CAND+T"] == r["trees"]["GOLD"]


def test_empty_patch_scores_no_candidate(tmp_path, fx):
    r = _score(tmp_path, fx, fx.task(b""))
    assert r["label"] == ros.NO_CANDIDATE
    assert r["f2p_total"] >= 1


def test_broken_patch_scores_broke_existing(tmp_path, fx):
    diff = fx.diff_from_base({"pkg/calc.py": FIXED + "\ndef broken(:\n"})
    r = _score(tmp_path, fx, fx.task(diff))
    assert r["label"] == ros.BROKE_EXISTING
    assert any("test_add" in n for n in r["p2p_new_failures"])


def test_unresolved_and_partial(tmp_path, fx):
    still_buggy = fx.diff_from_base({"pkg/calc.py": BUGGY.replace("a + b\n", "a + b  # x\n")})
    assert _score(tmp_path, fx, fx.task(still_buggy))["label"] == ros.UNRESOLVED
    partial = fx.diff_from_base({
        "pkg/calc.py": BUGGY.replace(
            "def mul(a, b):\n    return a + b",
            "def mul(a, b):\n    return 6 if (a, b) == (2, 3) else a + b",
        )
    })
    r = _score(tmp_path, fx, fx.task(partial))
    assert r["label"] == ros.PARTIAL
    assert 0 < r["f2p_pass"] < r["f2p_total"]


def test_candidate_test_edits_are_overwritten(tmp_path, fx):
    # Candidate "fixes" by writing a trivially passing test_mul.py; the oracle copy wins.
    weak = {"tests/test_mul.py": "def test_mul():\n    assert True\n"}
    assert _score(tmp_path, fx, fx.task(b"", untracked=weak))["label"] == ros.UNRESOLVED
    honest = fx.diff_from_base({"pkg/calc.py": FIXED})
    assert _score(tmp_path, fx, fx.task(honest, untracked=weak))["label"] == ros.RESOLVED


def test_untracked_files_are_applied(tmp_path, fx):
    diff = fx.diff_from_base({
        "pkg/calc.py": BUGGY.replace(
            "def mul(a, b):\n    return a + b", "from pkg.fast import mul  # noqa: F811"
        )
    })
    task = fx.task(diff, untracked={"pkg/fast.py": "def mul(a, b):\n    return a * b\n"})
    assert _score(tmp_path, fx, task)["label"] == ros.RESOLVED


def test_untracked_sha_mismatch_refused(tmp_path, fx):
    task = fx.task(b"", untracked={"pkg/fast.py": "x = 1\n"})
    raw = json.loads((task / "raw.json").read_text())
    raw["raw_response"]["strong_online_raw_response"]["untracked_files"][0]["sha256"] = "0" * 64
    raw_bytes = json.dumps(raw).encode()
    (task / "raw.json").write_bytes(raw_bytes)
    seal = {
        "path": "raw.json",
        "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "schema": "nexus.hybrid_replication.raw_seal.v1",
    }
    (task / "raw_seal.json").write_text(json.dumps(seal))
    state = json.loads((task / "state.json").read_text())
    state["raw_seal"] = seal
    (task / "state.json").write_text(json.dumps(state))
    with pytest.raises(ros.SealRefused, match="untracked_sha256"):
        _score(tmp_path, fx, task)


def test_tampered_raw_seal_is_refused(tmp_path, fx):
    task = fx.task(fx.gold_diff)
    data = bytearray((task / "raw.json").read_bytes())
    data[-2] = ord(" ") if data[-2] != ord(" ") else ord("\n")
    (task / "raw.json").write_bytes(bytes(data))
    with pytest.raises(ros.SealRefused, match="raw_sha256_mismatch"):
        _score(tmp_path, fx, task)


def test_tampered_ground_truth_is_refused(tmp_path, fx):
    task = fx.task(fx.gold_diff)
    (task / "ground_truth.json").write_text((task / "ground_truth.json").read_text() + " ")
    with pytest.raises(ros.SealRefused, match="ground_truth_sha256_mismatch"):
        _score(tmp_path, fx, task)


def test_cli_refuses_tampered_seal_and_writes_nothing(tmp_path, fx):
    task = fx.task(fx.gold_diff)
    (task / "raw.json").write_bytes((task / "raw.json").read_bytes() + b" ")
    script = Path(__file__).resolve().parents[2] / "nexus/research/score_real_outcome_cli.py"
    out = tmp_path / "out"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--store",
            str(fx.store),
            "--out",
            str(out),
            "--work",
            str(tmp_path / "w"),
            "--task",
            task.name,
            "--min-free-percent",
            "0",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 3
    assert "REFUSED_SEAL" in proc.stdout
    assert not list(out.glob("tasks/*/real_outcome.json"))


def test_two_runs_are_byte_identical(tmp_path, fx):
    task = fx.task(fx.diff_from_base({"pkg/calc.py": FIXED}))
    bodies = []
    for i in range(2):
        result = ros.score_task(task, _ctx(tmp_path, fx, work=f"work{i}"))
        path = ros.write_receipt(tmp_path / f"out{i}", result)
        bodies.append(path.read_bytes())
    assert bodies[0] == bodies[1]
    seal = json.loads((path.parent / "real_outcome_seal.json").read_text())
    assert seal["sha256"] == hashlib.sha256(bodies[1]).hexdigest()
    with pytest.raises(ros.ReceiptExists):
        ros.write_receipt(tmp_path / "out1", result)


def test_non_terminal_labels(tmp_path, fx):
    assert _score(tmp_path, fx, fx.task(terminal=None))["label"] == ros.PENDING_GROUND_TRUTH
    r = _score(tmp_path, fx, fx.task(terminal="CLOSED_WITHOUT_MERGED_PR"))
    assert r["label"] == ros.NOT_SCORABLE_NO_MERGED_PR
    r = _score(tmp_path, fx, fx.task(fx.gold_diff, merge=fx.docs_commit))
    assert r["label"] == ros.NOT_SCORABLE_NO_ORACLE
    r = _score(tmp_path, fx, fx.task(fx.gold_diff, merge="f" * 40))
    assert (r["label"], r["sub_reason"]) == (ros.NOT_SCORABLE_ORACLE_INVALID, "GOLD_PORT_FAILED")


def test_timeout_is_not_runnable_with_shadow_label(tmp_path, fx):
    r = _score(tmp_path, fx, fx.task(fx.gold_diff, status="TIMEOUT"))
    assert (r["label"], r["sub_reason"]) == (ros.NOT_RUNNABLE, "SEALED_WHILE_PROVIDER_RUNNING")
    assert r["shadow_label"] == ros.RESOLVED
    # An empty timeout is still NO_CANDIDATE (rule order).
    assert _score(tmp_path, fx, fx.task(b"", status="TIMEOUT"))["label"] == ros.NO_CANDIDATE


def test_apply_failure_is_not_runnable(tmp_path, fx):
    bad = b"diff --git a/nope.py b/nope.py\n--- a/nope.py\n+++ b/nope.py\n@@ -1 +1 @@\n-x\n+y\n"
    r = _score(tmp_path, fx, fx.task(bad))
    assert (r["label"], r["sub_reason"]) == (ros.NOT_RUNNABLE, "APPLY_FAILED")


def test_self_check_overrides(tmp_path, fx):
    task = fx.task(b"", status="TIMEOUT")
    ctx = _ctx(tmp_path, fx)
    assert ros.score_task(task, ctx, candidate_override="gold")["receipt"]["label"] == ros.RESOLVED
    assert (
        ros.score_task(task, ctx, candidate_override="empty")["receipt"]["label"]
        == ros.NO_CANDIDATE
    )
    r = ros.score_task(task, ctx, candidate_override="broken")["receipt"]
    assert r["label"] == ros.BROKE_EXISTING
    assert r["candidate_override"] == "broken:pkg/calc.py"


GATE_SOURCE = """
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ImpactPlan:
    pytest_targets: list = field(default_factory=list)
    changed_paths: list = field(default_factory=list)


def build_impact_plan(changed_paths, *, base_sha="", head_sha="", root=None):
    return ImpactPlan(pytest_targets=["tests/test_add.py", "tests/test_mul.py"],
                      changed_paths=list(changed_paths))
"""


def test_impact_gate_targets_come_from_trusted_base(tmp_path):
    fx = Fixture(tmp_path, repo_name="Nexus-new", gate=GATE_SOURCE)
    # Candidate breaks add() and also neuters the gate so it would select nothing.
    evil_gate = GATE_SOURCE.replace('["tests/test_add.py", "tests/test_mul.py"]', "[]")
    diff = fx.diff_from_base({
        "pkg/calc.py": FIXED.replace("a + b", "a - b"),
        "scripts/ops/pr_impact_gate.py": evil_gate,
    })
    r = _score(tmp_path, fx, fx.task(diff))
    assert r["p2p_targets"] == ["tests/test_add.py"]  # oracle file removed from targets
    assert r["impact_plan_sha256"]
    assert r["label"] == ros.BROKE_EXISTING


def test_clopper_pearson():
    lo, hi = ros.clopper_pearson(5, 10)
    assert abs(lo - 0.1871) < 1e-3 and abs(hi - 0.8129) < 1e-3
    lo, hi = ros.clopper_pearson(0, 10)
    assert lo == 0.0 and abs(hi - 0.3085) < 1e-3
    assert ros.clopper_pearson(0, 0) == (0.0, 1.0)


def test_summary_denominator_counts_no_candidate_as_failure():
    rows = [
        {
            "label": lab,
            "route": "B",
            "candidate_raw_status": "VALID",
            "capped": False,
            "candidate_empty": lab == ros.NO_CANDIDATE,
            "failure_kind": None,
            "task_key": str(i),
        }
        for i, lab in enumerate([
            ros.RESOLVED,
            ros.NO_CANDIDATE,
            ros.NOT_RUNNABLE,
            ros.NOT_SCORABLE_NO_ORACLE,
            ros.PENDING_GROUND_TRUTH,
        ])
    ]
    s = ros.summarize(rows)
    assert s["valid_oracle_n"] == 3 and s["resolved"] == 1
    assert s["counts"][ros.PENDING_GROUND_TRUTH] == 1


# ----------------------------------------------------------------------------
# Post-merge review follow-ups (#1951 review). See the PR for the mutation table.


def _reseal(task: Path, mutate) -> None:
    """Rewrite raw.json through ``mutate(so)`` and re-seal it consistently."""
    raw = json.loads((task / "raw.json").read_text())
    mutate(raw["raw_response"]["strong_online_raw_response"])
    raw_bytes = json.dumps(raw).encode()
    (task / "raw.json").write_bytes(raw_bytes)
    seal = {
        "path": "raw.json",
        "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "schema": "nexus.hybrid_replication.raw_seal.v1",
    }
    (task / "raw_seal.json").write_text(json.dumps(seal))
    state = json.loads((task / "state.json").read_text())
    state["raw_seal"] = seal
    (task / "state.json").write_text(json.dumps(state))


def _diff_with_symlink(fx: Fixture, link: str, target: str) -> bytes:
    """A candidate diff (vs BASE) that adds symlink ``link`` -> ``target``."""
    wt = fx.tmp / f"scratch{fx.n}"
    fx.n += 1
    _git(fx.upstream, "worktree", "add", "-q", "--detach", str(wt), fx.base)
    (wt / link).symlink_to(target)
    _git(wt, "add", "-A")
    return _git(wt, "diff", "--cached", "--binary", "HEAD").encode()


# Item 1: SHAs from ground truth / receipts never reach git unvalidated.


def test_injected_merge_sha_is_refused_and_not_executed(tmp_path, fx):
    marker = tmp_path / "PWNED"
    evil = f"--upload-pack=touch {marker};git-upload-pack"
    task = fx.task(fx.gold_diff, merge=evil)
    with pytest.raises(ros.SealRefused, match="merge_commit_sha_invalid"):
        _score(tmp_path, fx, task)
    assert not marker.exists()


def test_git_repo_refuses_non_sha_revisions(tmp_path, fx):
    marker = tmp_path / "PWNED2"
    repo = ros.GitRepo(tmp_path / "scorer-repo", [str(fx.upstream)])
    for bad in (f"--upload-pack=touch {marker};git-upload-pack", "main", "HEAD", fx.fix.upper()):
        with pytest.raises(ValueError, match="non-SHA"):
            repo.ensure_commit(bad)
        with pytest.raises(ValueError, match="non-SHA"):
            repo.worktree(tmp_path / "wt-bad", bad)
    assert not marker.exists()
    assert repo.ensure_commit(fx.fix)
    assert ros.is_full_sha(fx.fix) and not ros.is_full_sha("f" * 39)


# Item 2: nothing is written outside the candidate worktree.


def test_symlink_escape_with_untracked_write_is_apply_failed(tmp_path, fx):
    outside = tmp_path / "outside"
    outside.mkdir()
    # CAND+T lives at <tmp>/work/trees/<task>/candt, so this resolves to <tmp>/outside.
    diff = _diff_with_symlink(fx, "link", "../../../../outside")
    task = fx.task(diff, untracked={"link/evil.py": "print('escaped')\n"})
    r = _score(tmp_path, fx, task)
    assert (r["label"], r["sub_reason"]) == (ros.NOT_RUNNABLE, "APPLY_FAILED")
    assert r["detail"].startswith("symlink_escapes_tree:link")
    assert list(outside.iterdir()) == []


def test_escaping_symlink_alone_is_apply_failed(tmp_path, fx):
    outside = tmp_path / "outside"
    outside.mkdir()
    diff = _diff_with_symlink(fx, "pkg/escape", str(outside))
    r = _score(tmp_path, fx, fx.task(diff))
    assert (r["label"], r["sub_reason"]) == (ros.NOT_RUNNABLE, "APPLY_FAILED")


def test_apply_candidate_untracked_write_never_follows_links(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    wt = tmp_path / "wt"
    repo = ros.GitRepo(wt, [])
    (wt / "pkg").mkdir()
    (wt / "link").symlink_to(outside)
    (wt / "dangling").symlink_to(outside / "new.py")
    (wt / "alias").symlink_to("pkg")

    def cand(path: str) -> ros.Candidate:
        data = b"x = 1\n"
        return ros.Candidate(
            b"", [{"path": path, "sha256": hashlib.sha256(data).hexdigest(), "data": data}]
        )

    assert ros.apply_candidate(repo, wt, cand("link/evil.py")).startswith("untracked_path_escapes:")
    assert ros.apply_candidate(repo, wt, cand("dangling")).startswith("untracked_path_exists:")
    assert ros.apply_candidate(repo, wt, cand("../evil.py")).startswith("untracked_path_unsafe:")
    assert list(outside.iterdir()) == []
    # A link that stays inside the tree is still allowed.
    assert ros.apply_candidate(repo, wt, cand("alias/new.py")) is None
    assert (wt / "pkg" / "new.py").read_bytes() == b"x = 1\n"


def test_oracle_overwrite_replaces_candidate_symlink(tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("keep\n")
    gold, wt = tmp_path / "gold", tmp_path / "wt"
    (gold / "tests").mkdir(parents=True)
    (wt / "tests").mkdir(parents=True)
    (gold / "tests" / "test_x.py").write_text("gold\n")
    (wt / "tests" / "test_x.py").symlink_to(outside)
    ros.overwrite_oracle_files(wt, gold, ["tests/test_x.py"])
    assert outside.read_text() == "keep\n"
    assert not (wt / "tests" / "test_x.py").is_symlink()
    assert (wt / "tests" / "test_x.py").read_text() == "gold\n"


# Item 3: summary by raw status keys and filters on the same string.


def test_summary_by_raw_status_counts_none_status():
    rows = [
        {
            "label": lab,
            "route": "B",
            "candidate_raw_status": status,
            "capped": False,
            "candidate_empty": False,
            "failure_kind": None,
            "task_key": str(i),
        }
        for i, (lab, status) in enumerate([
            (ros.RESOLVED, None),
            (ros.UNRESOLVED, None),
            (ros.RESOLVED, "VALID"),
        ])
    ]
    s = ros.summarize(rows)
    assert s["by_raw_status"]["None"]["n"] == 2
    assert s["by_raw_status"]["None"]["resolved"] == 1
    assert s["by_raw_status"]["VALID"]["n"] == 1


# Item 4: spec §6.2 / §6.4 behaviours (each kills a recorded mutation).

FLAKY_ORACLE_TEST = (
    MUL_TEST + "\n\nimport os\nfrom pathlib import Path\n\n\n"
    "def test_flaky_counter():\n"
    "    # Fails on the 2nd invocation per tree (cwd is the scorer tree: gold/baset/candt).\n"
    '    p = Path(os.environ["TMPDIR"]) / ("flaky-" + Path.cwd().name)\n'
    "    n = int(p.read_text()) if p.exists() else 0\n"
    "    p.write_text(str(n + 1))\n"
    "    assert n != 1\n"
)
FLAKY_NODE = "tests.test_mul::test_flaky_counter"


def _counting_calc(mul_body: str, add_body: str = "return a + b") -> str:
    """Candidate calc.py that counts its imports on the CAND+T tree (one per pytest run)."""
    return (
        "import os\nfrom pathlib import Path\n\n"
        '_p = Path(os.environ["TMPDIR"]) / "cand-imports"\n'
        "_n = int(_p.read_text()) if _p.exists() else 0\n"
        "_p.write_text(str(_n + 1))\n\n\n"
        f"def add(a, b):\n    {add_body}\n\n\n"
        f"def mul(a, b):\n    {mul_body}\n"
    )


def test_oracle_flaky_node_is_dropped_not_p2p(tmp_path):
    fx = Fixture(tmp_path, mul_test=FLAKY_ORACLE_TEST)
    r = _score(tmp_path, fx, fx.task(fx.diff_from_base({"pkg/calc.py": FIXED})))
    assert r["oracle_flaky"] == [FLAKY_NODE]
    assert FLAKY_NODE not in r["p2p_a"] and FLAKY_NODE not in r["f2p"]
    assert r["flaky_dropped"] == 1
    assert r["f2p_total"] == 3
    assert len(r["outcome_digests"]["GOLD"]) == 3
    assert r["label"] == ros.RESOLVED


def test_candidate_f2p_uses_majority_of_three_runs(tmp_path, fx):
    # First CAND+T oracle run: mul is still buggy; reruns 2 and 3: fixed. Majority = pass.
    calc = _counting_calc("return a + b if _n == 0 else a * b")
    r = _score(tmp_path, fx, fx.task(fx.diff_from_base({"pkg/calc.py": calc})))
    assert r["label"] == ros.RESOLVED
    assert r["f2p_pass"] == 3
    assert len(r["outcome_digests_cand"]) == 3


def test_p2p_suspect_flaky_on_candidate_is_dropped(tmp_path, fx):
    # Import 0 = oracle run (all pass, no rerun); import 1 = P2P run 0 where add() is
    # broken; P2P reruns pass. Not 3/3 failing on CAND+T -> flaky, not a regression.
    calc = _counting_calc("return a * b", add_body="return a - b if _n == 1 else a + b")
    r = _score(tmp_path, fx, fx.task(fx.diff_from_base({"pkg/calc.py": calc})))
    assert r["p2p_new_failures"] == []
    assert r["flaky_dropped"] == 1
    assert r["label"] == ros.RESOLVED


def test_clean_candidate_has_no_p2p_suspects(tmp_path, fx):
    r = _score(tmp_path, fx, fx.task(fx.diff_from_base({"pkg/calc.py": FIXED})))
    assert r["label"] == ros.RESOLVED
    assert r["flaky_dropped"] == 0
    assert r["gold_also_fails"] == []
    assert r["p2p_bc_total"] == 1


LEGACY_TEST = "from pkg.calc import mul\n\n\ndef test_legacy_mul():\n    assert mul(2, 3) == 5\n"


def test_p2p_node_broken_by_gold_is_gold_also_fails(tmp_path):
    # tests/test_legacy.py is not touched by the human PR (so it is P2P(c), not oracle),
    # passes on BASE+T and fails on GOLD: the intended change breaks it.
    fx = Fixture(tmp_path, extra_base={"tests/test_legacy.py": LEGACY_TEST})
    r = _score(tmp_path, fx, fx.task(fx.diff_from_base({"pkg/calc.py": FIXED})))
    assert r["gold_also_fails"] == ["tests.test_legacy::test_legacy_mul"]
    assert r["p2p_new_failures"] == []
    assert r["label"] == ros.RESOLVED


P2P_A_TEST = MUL_TEST + "\n\ndef test_mul_two_two():\n    assert mul(2, 2) == 4\n"


def test_p2p_a_regression_is_broke_existing(tmp_path):
    fx = Fixture(tmp_path, mul_test=P2P_A_TEST)
    calc = FIXED.replace("return a * b", "return 5 if (a, b) == (2, 2) else a * b")
    r = _score(tmp_path, fx, fx.task(fx.diff_from_base({"pkg/calc.py": calc})))
    assert r["p2p_a"] == ["tests.test_mul::test_mul_two_two"]
    assert r["f2p_pass"] == r["f2p_total"] == 3
    assert r["p2p_new_failures"] == ["tests.test_mul::test_mul_two_two"]
    assert r["label"] == ros.BROKE_EXISTING


# Item 5: self-check (a) executes CAND+T instead of replaying GOLD's cached run.


def test_self_check_gold_executes_candidate_runs(tmp_path, fx):
    lines: list[str] = []
    ctx = _ctx(tmp_path, fx)
    ctx.runner.log = lines.append
    r = ros.score_task(fx.task(b""), ctx, candidate_override="gold")["receipt"]
    assert r["label"] == ros.RESOLVED
    assert r["trees"]["CAND+T"] == r["trees"]["GOLD"]
    assert any("tests/test_mul.py" in m and "role=CAND+T" in m for m in lines)


# Item 6: P2P runs that time out or fail to collect are recorded as a diagnostic only;
# scoring follows v1 (§6.2, §8: their expected nodes count as fail).


class _FaultyRunner(ros.PytestRunner):
    """Times out the P2P(b/c) run on one tree (BASE+T or GOLD)."""

    def __init__(self, *a, fail_tree: str, **kw):
        super().__init__(*a, **kw)
        self.fail_tree = fail_tree

    def run(self, env, tree, tree_id, target, ignores, run_idx, role=""):
        if target == "tests" and tree.name == self.fail_tree and not role:
            return ros.RunResult({}, -1, True)
        return super().run(env, tree, tree_id, target, ignores, run_idx, role)


def _faulty_ctx(tmp: Path, fx: Fixture, fail_tree: str) -> ros.ScoreContext:
    ctx = _ctx(tmp, fx)
    ctx.runner = _FaultyRunner(
        tmp / "work" / "scratch", timeout=300, log=lambda m: None, fail_tree=fail_tree
    )
    return ctx


def test_p2p_baseline_timeout_is_recorded_without_label_effect(tmp_path, fx):
    task = fx.task(fx.diff_from_base({"pkg/calc.py": FIXED}))
    r = ros.score_task(task, _faulty_ctx(tmp_path, fx, "baset"))["receipt"]
    # v1: a timed-out BASE+T run has no passing nodes, so the P2P(c) base set is empty.
    assert r["label"] == ros.RESOLVED and r["sub_reason"] is None
    assert r["p2p_bc_total"] == 0
    assert r["p2p_baseline_failures"] == [
        {"exit_code": -1, "run": 0, "target": "tests", "timed_out": True, "tree": "BASE+T"}
    ]


class _OracleFaultRunner(ros.PytestRunner):
    """Kills (timeout, or a signal exit code) oracle-module runs on one tree."""

    def __init__(self, *a, fail_tree: str, exit_code: int = -1, timed_out: bool = True, **kw):
        super().__init__(*a, **kw)
        self.fail_tree, self.fault = fail_tree, (exit_code, timed_out)

    def run(self, env, tree, tree_id, target, ignores, run_idx, role=""):
        if target != "tests" and tree.name == self.fail_tree:
            return ros.RunResult({}, self.fault[0], self.fault[1])
        return super().run(env, tree, tree_id, target, ignores, run_idx, role)


def _oracle_fault_receipt(tmp, tree, **kw):
    tmp.mkdir(parents=True)
    fx = Fixture(tmp)
    ctx = _ctx(tmp, fx)
    ctx.runner = _OracleFaultRunner(
        tmp / "work" / "scratch", timeout=300, log=lambda m: None, fail_tree=tree, **kw
    )
    task = fx.task(fx.diff_from_base({"pkg/calc.py": FIXED}))
    return ros.score_task(task, ctx)["receipt"]


def test_a7_oracle_timeouts_are_diagnostic_only(tmp_path, monkeypatch):
    (tmp_path / "clean").mkdir()
    fx = Fixture(tmp_path / "clean")
    clean = _score(tmp_path / "clean", fx, fx.task(fx.diff_from_base({"pkg/calc.py": FIXED})))
    assert clean["run_failure_diagnostics"] == []
    for tree, name in (("baset", "BASE+T"), ("candt", "CAND+T")):
        r = _oracle_fault_receipt(tmp_path / tree, tree)
        diag = r["run_failure_diagnostics"]
        assert diag and all(d["tree"] == name and d["timed_out"] for d in diag)
        assert all(d["exit_code"] == -1 and d["target"] != "tests" for d in diag)
        # Labels are what they would be without the recording (A7 never changes a label).
        monkeypatch.setattr(ros, "_run_failures", lambda *a, **k: [])
        off = _oracle_fault_receipt(tmp_path / (tree + "-off"), tree)
        monkeypatch.undo()
        assert off["run_failure_diagnostics"] == []
        assert (r["label"], r["sub_reason"], r.get("shadow_label")) == (
            off["label"],
            off["sub_reason"],
            off.get("shadow_label"),
        )


def test_a7_signal_kill_is_listed_and_exit_2_is_not(tmp_path):
    r = _oracle_fault_receipt(tmp_path / "sig", "candt", exit_code=-9, timed_out=False)
    assert r["run_failure_diagnostics"]
    assert all(d["exit_code"] == -9 and not d["timed_out"] for d in r["run_failure_diagnostics"])
    # Exit 2 (collection error) is how F2P fails on BASE+T: never listed.
    for tree in ("baset", "candt"):
        r = _oracle_fault_receipt(tmp_path / f"e2{tree}", tree, exit_code=2, timed_out=False)
        assert r["run_failure_diagnostics"] == []


def test_p2p_gold_timeout_makes_suspects_gold_also_fails(tmp_path, fx):
    # The candidate breaks add(); GOLD's P2P run times out, so under v1 every node of it
    # counts as fail on GOLD and the suspect is `gold_also_fails`. The diagnostic shows why.
    calc = FIXED.replace("return a + b", "return a - b")
    task = fx.task(fx.diff_from_base({"pkg/calc.py": calc}))
    r = ros.score_task(task, _faulty_ctx(tmp_path, fx, "gold"))["receipt"]
    assert r["label"] == ros.RESOLVED
    assert r["gold_also_fails"] == ["tests.test_add::test_add"]
    assert [d["tree"] for d in r["p2p_baseline_failures"]] == ["GOLD"]


def test_p2p_baseline_collection_error_is_recorded(tmp_path):
    fx = Fixture(tmp_path, extra_base={"tests/test_import_error.py": "import no_such_mod_xyz\n"})
    r = _score(tmp_path, fx, fx.task(fx.diff_from_base({"pkg/calc.py": FIXED})))
    assert r["label"] == ros.RESOLVED
    assert r["p2p_baseline_failures"][0]["tree"] == "BASE+T"
    assert r["p2p_baseline_failures"][0]["exit_code"] == 2


def test_p2p_baseline_failure_on_timeout_candidate_keeps_shadow_label(tmp_path, fx):
    task = fx.task(fx.diff_from_base({"pkg/calc.py": FIXED}), status="TIMEOUT")
    r = ros.score_task(task, _faulty_ctx(tmp_path, fx, "baset"))["receipt"]
    assert (r["label"], r["sub_reason"]) == (ros.NOT_RUNNABLE, "SEALED_WHILE_PROVIDER_RUNNING")
    assert r["shadow_label"] == ros.RESOLVED
    assert r["p2p_baseline_failures"]


def test_gold_deleting_imported_module_is_gold_also_fails(tmp_path):
    # Review repro: the human fix deletes pkg/old.py, which an unchanged P2P test imports.
    # GOLD's P2P run fails to collect (exit 2); under v1 those nodes fail on GOLD, so
    # candidate := GOLD is RESOLVED with them in gold_also_fails.
    fx = Fixture(
        tmp_path,
        extra_base={
            "pkg/old.py": "X = 1\n",
            "tests/test_old_user.py": "import pkg.old\n\n\ndef test_old():\n    assert pkg.old.X == 1\n",
        },
    )
    up = fx.upstream
    _git(up, "checkout", "-q", "--detach", fx.base)
    _write(up, {"pkg/calc.py": FIXED, "tests/test_mul.py": MUL_TEST})
    _git(up, "rm", "-q", "pkg/old.py")
    _git(up, "add", "-A")
    _git(up, "commit", "-qm", "human fix removing old")
    merge = _git(up, "rev-parse", "HEAD").strip()
    task = fx.task(b"", merge=merge)
    r = ros.score_task(task, _ctx(tmp_path, fx), candidate_override="gold")["receipt"]
    assert r["label"] == ros.RESOLVED
    assert "tests.test_old_user::test_old" in r["gold_also_fails"]
    assert r["p2p_new_failures"] == []
    assert any(d["tree"] == "GOLD" and d["exit_code"] == 2 for d in r["p2p_baseline_failures"])


# Review round 2 (F3-F5): symlinks at ignored paths, .git components, shape checks.


def _apply_lab(tmp_path: Path):
    """A BASE repo with `*.log` git-ignored, its scorer repo, and an outside dir."""
    outside = tmp_path / "outside"
    outside.mkdir()
    up = tmp_path / "lab-up"
    up.mkdir()
    _git(up, "init", "-q")
    _write(
        up,
        {
            ".gitignore": "*.log\n",
            "pkg/a.py": "x = 1\n",
            "tests/test_a.py": "def test_a():\n    pass\n",
        },
    )
    _git(up, "add", "-A")
    _git(up, "commit", "-qm", "base")
    base = _git(up, "rev-parse", "HEAD").strip()
    repo = ros.GitRepo(tmp_path / "lab-repo", [str(up)])
    assert repo.ensure_commit(base)
    return up, base, repo, outside


def _forced_diff(up: Path, base: str, make) -> bytes:
    """Diff vs BASE that also includes git-ignored paths (``add -f``)."""
    w = up.parent / f"mk-{abs(hash(make)) % 10**8}"
    _git(up, "worktree", "add", "-q", "--detach", str(w), base)
    make(w)
    _git(w, "add", "-A", "-f")
    return _git(w, "diff", "--cached", "--binary", "--no-renames").encode()


@pytest.mark.parametrize(
    "make",
    [
        pytest.param(lambda w, out: (w / "evil.log").symlink_to(out), id="ignored-absolute"),
        pytest.param(lambda w, out: (w / "rel.log").symlink_to("../../outside"), id="relative"),
        pytest.param(
            lambda w, out: (
                (w / "a.log").symlink_to("evil2.log"),
                (w / "evil2.log").symlink_to(out),
            ),
            id="chain",
        ),
    ],
)
def test_escaping_symlink_at_ignored_path_is_apply_failed(tmp_path, make):
    up, base, repo, outside = _apply_lab(tmp_path)
    diff = _forced_diff(up, base, lambda w: make(w, outside))
    # The candidate worktree sits at <tmp>/wts/cand, so ../../outside is <tmp>/outside.
    wt = repo.worktree(tmp_path / "wts" / "cand", base)
    err = ros.apply_candidate(repo, wt, ros.Candidate(diff, []))
    assert err and err.startswith("symlink_escapes_tree:")
    assert list(outside.iterdir()) == []


def test_base_tracked_escaping_symlink_is_not_blamed_on_candidate(tmp_path):
    up, _, _, outside = _apply_lab(tmp_path)
    (up / "docs").mkdir()
    (up / "docs" / "LATEST.md").symlink_to(outside / "rca.md")
    _git(up, "add", "-A")
    _git(up, "commit", "-qm", "tracked absolute link, as in Nexus-new")
    base = _git(up, "rev-parse", "HEAD").strip()
    repo = ros.GitRepo(tmp_path / "lab-repo2", [str(up)])
    assert repo.ensure_commit(base)
    diff = _forced_diff(up, base, lambda w: (w / "pkg" / "a.py").write_text("x = 2\n"))
    wt = repo.worktree(tmp_path / "wts" / "cand2", base)
    assert ros.apply_candidate(repo, wt, ros.Candidate(diff, [])) is None


@pytest.mark.parametrize("path", [".git/config", ".GIT/config", "pkg/.git/hooks/x", "a/.Git"])
def test_untracked_git_component_is_unsafe(tmp_path, path):
    wt = tmp_path / "wt"
    repo = ros.GitRepo(wt, [])
    data = b"x\n"
    cand = ros.Candidate(
        b"", [{"path": path, "sha256": hashlib.sha256(data).hexdigest(), "data": data}]
    )
    assert ros.apply_candidate(repo, wt, cand) == f"untracked_path_unsafe:{path}"


def test_oracle_parent_symlink_escape_is_apply_failed(tmp_path, monkeypatch, fx):
    # If an escaping parent link ever reaches the oracle overwrite, the task is
    # NOT_RUNNABLE/APPLY_FAILED rather than a scorer error.
    def boom(wt, gold_wt, files):
        if wt.name == "candt":
            raise ros.UnsafeTreePath("oracle_path_escapes:tests/test_mul.py")
        return real(wt, gold_wt, files)

    real = ros.overwrite_oracle_files
    monkeypatch.setattr(ros, "overwrite_oracle_files", boom)
    r = _score(tmp_path, fx, fx.task(fx.diff_from_base({"pkg/calc.py": FIXED})))
    assert (r["label"], r["sub_reason"]) == (ros.NOT_RUNNABLE, "APPLY_FAILED")
    assert r["detail"] == "oracle_path_escapes:tests/test_mul.py"


def test_overwrite_oracle_files_refuses_escaping_parent(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    gold, wt = tmp_path / "gold", tmp_path / "wt"
    (gold / "tests" / "sub").mkdir(parents=True)
    (gold / "tests" / "sub" / "test_o.py").write_text("gold\n")
    (wt / "tests").mkdir(parents=True)
    (wt / "tests" / "sub").symlink_to(outside)
    with pytest.raises(ros.UnsafeTreePath):
        ros.overwrite_oracle_files(wt, gold, ["tests/sub/test_o.py"])
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("size", ["abc", 1.5, True, [6]])
def test_malformed_untracked_size_is_seal_refused(tmp_path, fx, size):
    task = fx.task(b"", untracked={"pkg/fast.py": "x = 1\n"})
    _reseal(task, lambda so: so["untracked_files"][0].update({"size": size}))
    with pytest.raises(ros.SealRefused, match="untracked_size_invalid"):
        ros.load_sealed_task(task)


@pytest.mark.parametrize(
    "gt", [{"details": "x", "terminal_state": "CLOSED_WITH_MERGED_PR"}, ["not", "an", "object"]]
)
def test_malformed_ground_truth_shape_is_seal_refused(tmp_path, fx, gt):
    task = fx.task(fx.gold_diff)
    gt_bytes = json.dumps(gt).encode()
    (task / "ground_truth.json").write_bytes(gt_bytes)
    state = json.loads((task / "state.json").read_text())
    state["ground_truth"]["sha256"] = hashlib.sha256(gt_bytes).hexdigest()
    (task / "state.json").write_text(json.dumps(state))
    with pytest.raises(ros.SealRefused, match="ground_truth_shape_invalid"):
        _score(tmp_path, fx, task)


def test_ensure_commit_option_like_source_is_not_an_option(tmp_path, fx):
    marker = tmp_path / "PWNED3"
    repo = ros.GitRepo(tmp_path / "scorer-repo3", [f"--upload-pack=touch {marker};git-upload-pack"])
    assert repo.ensure_commit(fx.fix) is False
    assert not marker.exists()
    repo.sources.append(str(fx.upstream))
    assert repo.ensure_commit(fx.fix) is True


# Item 7: malformed payloads, memory wait, env cache key, version.


@pytest.mark.parametrize(
    "payload",
    ["!!!not-base64!!!", base64.b64encode(b"not gzip").decode(), 12345],
)
def test_malformed_diff_payload_is_seal_refused(tmp_path, fx, payload):
    task = fx.task(fx.gold_diff)
    _reseal(task, lambda so: so.update({"diff_gzip_base64": payload}))
    with pytest.raises(ros.SealRefused, match="payload_malformed:diff"):
        ros.load_sealed_task(task)


def test_malformed_untracked_payload_is_seal_refused(tmp_path, fx):
    task = fx.task(b"", untracked={"pkg/fast.py": "x = 1\n"})
    truncated = base64.b64encode(gzip.compress(b"x = 1\n")[:-6]).decode()
    _reseal(task, lambda so: so["untracked_files"][0].update({"gzip_base64": truncated}))
    with pytest.raises(ros.SealRefused, match="payload_malformed:untracked"):
        ros.load_sealed_task(task)


def _cli():
    from nexus.research import score_real_outcome_cli as cli

    return cli


def test_memory_wait_treats_unknown_as_low_with_bounded_backoff():
    cli = _cli()
    sleeps: list[int] = []
    readings = iter([None, None, 50])
    waited = cli.wait_for_memory(
        20, lambda m: None, probe=lambda: next(readings), sleep=sleeps.append
    )
    assert sleeps == [60, 120] and waited == 180
    sleeps.clear()
    logs: list[str] = []
    with pytest.raises(cli.MemoryCheckUnavailable):
        cli.wait_for_memory(20, logs.append, probe=lambda: None, sleep=sleeps.append)
    assert sleeps == list(cli.UNKNOWN_BACKOFF_SECONDS)
    assert any("unknown" in m for m in logs)
    sleeps.clear()
    readings = iter([10, 30])
    assert (
        cli.wait_for_memory(20, lambda m: None, probe=lambda: next(readings), sleep=sleeps.append)
        == 60
    )
    called = []
    cli.wait_for_memory(0, lambda m: None, probe=lambda: called.append(1), sleep=sleeps.append)
    assert called == []


def test_env_cache_keys_cover_interpreter_pythonpath_and_version(tmp_path, monkeypatch):
    base = ros.TestEnv("k", "/py/a", "r", {"python": "3.12.1"}, ("/x",))
    assert base.cache_key != ros.TestEnv("k", "/py/b", "r", {"python": "3.12.1"}, ("/x",)).cache_key
    assert base.cache_key != ros.TestEnv("k", "/py/a", "r", {"python": "3.12.2"}, ("/x",)).cache_key
    assert base.cache_key != ros.TestEnv("k", "/py/a", "r", {"python": "3.12.1"}, ("/y",)).cache_key
    wt = tmp_path / "base"
    wt.mkdir()
    (wt / "uv.lock").write_text("lock\n")
    provider = ros.UvEnvProvider(tmp_path / "envs", log=lambda m: None)
    interp = {"path": "/uv/python3.12", "version": "3.12.7"}
    monkeypatch.setattr(provider, "_interpreter", lambda: dict(interp))
    k1 = provider.env_key("repo", wt)[0]
    interp["path"] = "/other/python3.12"
    k2 = provider.env_key("repo", wt)[0]
    interp["version"] = "3.12.8"
    k3 = provider.env_key("repo", wt)[0]
    old_cache_key = base.cache_key
    monkeypatch.setattr(ros, "SCORER_VERSION", "9.9.9")
    k4 = provider.env_key("repo", wt)[0]
    assert len({k1, k2, k3, k4}) == 4
    assert base.cache_key != old_cache_key


def test_scorer_version_is_recorded_in_spec_amendment():
    root = Path(__file__).resolve().parents[2]
    assert ros.SCORER_VERSION == "1.3.1"
    amendments = (root / "docs/research/REAL_OUTCOME_SCORER_SPEC.amendments.md").read_text()
    assert f'SCORER_VERSION = "{ros.SCORER_VERSION}"' in amendments
    spec = (root / ros.SPEC_RELATIVE_PATH).read_bytes()
    # The pre-registered spec itself is frozen (spec header); amendments live beside it.
    assert hashlib.sha256(spec).hexdigest().startswith("315d95de21ea7ec8")
    # A10: the 1.3.0 row and note point to the v3 file, the Issue and the owner decision.
    assert "| `1.3.0` |" in amendments and "A10" in amendments
    assert "REAL_OUTCOME_SCORER_SPEC.v3.md" in amendments and "#2709" in amendments
    assert "「同意」" in amendments


# Amendment A5: GOLD port fallback when main moved between BASE and the merge.

STATUS_BASE = "status: base\nline2\n"
OLD_MUL_TEST = "def test_placeholder():\n    assert True  # base\n"
DRIFT_TEST_SUB = (
    "def test_placeholder():\n    assert True  # drift\n\n\n"
    "def test_sub_from_drift():\n    from pkg.extra import sub\n\n    assert sub(3, 1) == 2\n"
)


def _drift_then_fix(fx: Fixture, drift: dict[str, str], fix: dict[str, str]) -> str:
    """From BASE: one drift commit on main, then the human fix on top (M^1 = drift)."""
    up = fx.upstream
    _git(up, "checkout", "-q", "--detach", fx.base)
    _write(up, drift)
    _git(up, "add", "-A")
    _git(up, "commit", "-qm", "main moved")
    _write(up, fix)
    _git(up, "add", "-A")
    _git(up, "commit", "-qm", "human fix after drift")
    return _git(up, "rev-parse", "HEAD").strip()


def _fix_with(test_mul: str) -> dict[str, str]:
    return {"pkg/calc.py": FIXED, "tests/test_mul.py": test_mul}


def test_clean_port_records_v1_method_only(tmp_path, fx):
    r = _score(tmp_path, fx, fx.task(fx.gold_diff))
    assert r["gold_port_method"] == ros.GOLD_PORT_3WAY
    assert "gold_port_dropped_non_code_paths" not in r
    assert "gold_port_test_files_from_merge" not in r
    assert r["label"] == ros.RESOLVED


def test_docs_conflict_drops_doc_and_keeps_oracle(tmp_path):
    # Class "conflict only in a non-test doc/data file": v1 GOLD_PORT_FAILED.
    fx = Fixture(tmp_path, extra_base={"docs/status.md": STATUS_BASE})
    merge = _drift_then_fix(
        fx,
        {"docs/status.md": "status: drift\nline2\n"},
        {**_fix_with(MUL_TEST), "docs/status.md": "status: fixed\nline2\n"},
    )
    r = ros.score_task(fx.task(b"", merge=merge), _ctx(tmp_path, fx), candidate_override="gold")[
        "receipt"
    ]
    assert r["gold_port_method"] == ros.GOLD_PORT_PER_FILE
    assert r["gold_port_dropped_non_code_paths"] == ["docs/status.md"]
    assert r["gold_port_test_files_from_merge"] == []
    assert r["f2p_total"] == 3
    assert r["label"] == ros.RESOLVED


def test_test_file_conflict_takes_merge_tree_test_file(tmp_path):
    # Class "conflict in an oracle test file": the test file is set to its merge-commit
    # content; F2P still needs BASE+T fail and GOLD pass.
    fx = Fixture(tmp_path, extra_base={"tests/test_mul.py": OLD_MUL_TEST})
    merge = _drift_then_fix(
        fx,
        {"tests/test_mul.py": OLD_MUL_TEST.replace("# base", "# drift")},
        _fix_with(OLD_MUL_TEST.replace("# base", "# fix") + "\n\n" + MUL_TEST),
    )
    r = ros.score_task(fx.task(b"", merge=merge), _ctx(tmp_path, fx), candidate_override="gold")[
        "receipt"
    ]
    assert r["gold_port_method"] == ros.GOLD_PORT_PER_FILE
    assert r["gold_port_test_files_from_merge"] == ["tests/test_mul.py"]
    assert r["f2p_total"] == 3
    assert "tests.test_mul::test_placeholder" in r["p2p_a"]
    assert r["label"] == ros.RESOLVED


def test_test_file_missing_at_base_takes_merge_tree_test_file(tmp_path, fx):
    # Class "the PR modifies a test file that a later main commit added": git apply
    # reports "does not exist in index" under v1.
    merge = _drift_then_fix(
        fx,
        {"tests/test_mul.py": OLD_MUL_TEST},
        _fix_with(OLD_MUL_TEST + "\n\n" + MUL_TEST),
    )
    r = ros.score_task(fx.task(b"", merge=merge), _ctx(tmp_path, fx), candidate_override="gold")[
        "receipt"
    ]
    assert r["gold_port_test_files_from_merge"] == ["tests/test_mul.py"]
    assert r["f2p_total"] == 3
    assert r["label"] == ros.RESOLVED


def test_source_conflict_stays_gold_port_failed(tmp_path, fx):
    # A Python source conflict is never dropped or taken from the merge tree.
    merge = _drift_then_fix(
        fx,
        {
            "pkg/calc.py": BUGGY.replace(
                "def mul(a, b):\n    return a + b", "def mul(a, b):\n    return b + a"
            )
        },
        _fix_with(MUL_TEST),
    )
    r = _score(tmp_path, fx, fx.task(fx.gold_diff, merge=merge))
    assert (r["label"], r["sub_reason"]) == (ros.NOT_SCORABLE_ORACLE_INVALID, "GOLD_PORT_FAILED")
    assert r["gold_port_failed_paths"] == ["pkg/calc.py"]
    assert r["detail"] == "pr:7"


def test_fallback_cannot_make_a_wrong_candidate_resolved(tmp_path):
    # Main moved: a drift commit adds pkg/extra.py with a test in the oracle test file and
    # a doc line; the human fix conflicts with both. The merge-tree test file carries the
    # drift test, which fails on GOLD (no pkg/extra.py there), so it is never F2P.
    fx = Fixture(
        tmp_path,
        extra_base={"tests/test_mul.py": OLD_MUL_TEST, "docs/status.md": STATUS_BASE},
    )
    merge = _drift_then_fix(
        fx,
        {
            "tests/test_mul.py": DRIFT_TEST_SUB,
            "pkg/extra.py": "def sub(a, b):\n    return a - b\n",
            "docs/status.md": "status: drift\nline2\n",
        },
        {
            **_fix_with(DRIFT_TEST_SUB.replace("# drift", "# fix") + "\n\n" + MUL_TEST),
            "docs/status.md": "status: fixed\nline2\n",
        },
    )
    ctx = _ctx(tmp_path, fx)
    docs_only = fx.diff_from_base({"docs/status.md": "status: fixed\nline2\n"})
    partial_mul = fx.diff_from_base({
        "pkg/calc.py": BUGGY.replace(
            "def mul(a, b):\n    return a + b",
            "def mul(a, b):\n    return 6 if (a, b) == (2, 3) else a + b",
        )
    })
    wrong = (
        # implements only the drift (the sub() that the merge-tree test file checks)
        (b"", {"pkg/extra.py": "def sub(a, b):\n    return a - b\n"}, ros.UNRESOLVED),
        # copies only the dropped doc change
        (docs_only, None, ros.UNRESOLVED),
        # fixes one of three F2P nodes
        (partial_mul, None, ros.PARTIAL),
    )
    for diff, untracked, expected in wrong:
        r = ros.score_task(fx.task(diff, untracked=untracked, merge=merge), ctx)["receipt"]
        assert r["gold_port_method"] == ros.GOLD_PORT_PER_FILE
        assert r["gold_port_test_files_from_merge"] == ["tests/test_mul.py"]
        assert r["gold_port_dropped_non_code_paths"] == ["docs/status.md"]
        assert "tests.test_mul::test_sub_from_drift" not in r["f2p"]
        assert r["f2p_total"] == 3
        assert r["label"] == expected
    honest = fx.diff_from_base({"pkg/calc.py": FIXED})
    r = ros.score_task(fx.task(honest, merge=merge), ctx)["receipt"]
    assert r["label"] == ros.RESOLVED


def test_droppable_classification():
    assert ros.is_droppable_non_code("docs/a.md")
    assert ros.is_droppable_non_code("README.md")
    assert ros.is_droppable_non_code("docs/x/matrix.json")
    assert ros.is_droppable_non_code("nexus_wiki_vault/99_Schema/generated/agent-index.json")
    # Codex review round 2: config and workflow/action files are behaviour, never dropped.
    assert not ros.is_droppable_non_code(".github/actions/x/action.yml")
    assert not ros.is_droppable_non_code(".github/workflows/ci.md")
    assert not ros.is_droppable_non_code("package.json")
    assert not ros.is_droppable_non_code("src/pkg/config/model_workforce.yaml")
    # Agy review round 3: dependency manifests are never prose.
    assert not ros.is_droppable_non_code("requirements.txt")
    assert not ros.is_droppable_non_code("requirements/canonical-runtime.txt")
    assert ros.is_droppable_non_code("docs/notes.txt")
    assert not ros.is_droppable_non_code("pkg/a.py")
    assert not ros.is_droppable_non_code("scripts/run.sh")
    assert not ros.is_droppable_non_code("pyproject.toml")
    assert not ros.is_droppable_non_code("tests/data/fixture.json")  # oracle test file


CFG_TEST = (
    "import json\nfrom pathlib import Path\n\n\n"
    "def test_cfg_mode():\n"
    '    assert json.loads(Path("docs/mode.json").read_text())["mode"] == "fixed"\n'
)


def test_dropped_file_that_changes_an_oracle_outcome_stays_gold_port_failed(tmp_path):
    # Codex review (P1): a dropped data file the human tests read would make
    # test_cfg_mode fail on GOLD and silently leave F2P, so a candidate fixing only
    # mul() could be RESOLVED. GOLD_REF (GOLD + merge content of the dropped file) exposes
    # the outcome change and the task stays GOLD_PORT_FAILED.
    fx = Fixture(tmp_path, extra_base={"docs/mode.json": '{"mode": "base",\n "x": 1}\n'})
    merge = _drift_then_fix(
        fx,
        {"docs/mode.json": '{"mode": "base",\n "x": 2}\n'},
        {
            **_fix_with(MUL_TEST + "\n\n" + CFG_TEST),
            "docs/mode.json": '{"mode": "fixed",\n "x": 3}\n',
        },
    )
    mul_only = fx.diff_from_base({"pkg/calc.py": FIXED})
    r = _score(tmp_path, fx, fx.task(mul_only, merge=merge))
    assert (r["label"], r["sub_reason"]) == (ros.NOT_SCORABLE_ORACLE_INVALID, "GOLD_PORT_FAILED")
    assert r["detail"] == "dropped_paths_change_oracle_outcome"
    assert r["gold_ref_mismatch"] == ["tests.test_mul::test_cfg_mode"]
    assert r["gold_port_dropped_non_code_paths"] == ["docs/mode.json"]


def test_dropped_doc_with_no_oracle_effect_records_gold_ref_tree(tmp_path):
    fx = Fixture(tmp_path, extra_base={"docs/status.md": STATUS_BASE})
    merge = _drift_then_fix(
        fx,
        {"docs/status.md": "status: drift\nline2\n"},
        {**_fix_with(MUL_TEST), "docs/status.md": "status: fixed\nline2\n"},
    )
    r = _score(tmp_path, fx, fx.task(fx.diff_from_base({"pkg/calc.py": FIXED}), merge=merge))
    assert r["label"] == ros.RESOLVED
    assert "GOLD_REF" in r["trees"] and r["trees"]["GOLD_REF"] != r["trees"]["GOLD"]


def test_gold_port_path_restore_never_unlinks_through_escaping_parent(tmp_path, fx):
    # Codex review (P1): a PR path under a BASE symlink to outside the tree.
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "victim.txt").write_text("keep\n")
    repo = ros.GitRepo(tmp_path / "scorer-repo", [str(fx.upstream)])
    assert repo.ensure_commit(fx.base)
    wt = repo.worktree(tmp_path / "wt", fx.base)
    (wt / "linkdir").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ros.UnsafeTreePath):
        ros._set_path_from(repo, wt, fx.base, "linkdir/victim.txt")
    assert (outside / "victim.txt").read_text() == "keep\n"


class _TreeTimeoutRunner(ros.PytestRunner):
    """Times out every non-candidate run of ``targets`` on the named trees."""

    def __init__(self, *a, trees: set[str], targets: set[str], **kw):
        super().__init__(*a, **kw)
        self.trees, self.targets = trees, targets

    def run(self, env, tree, tree_id, target, ignores, run_idx, role=""):
        if tree.name in self.trees and target in self.targets and not role:
            return ros.RunResult({}, -1, True)
        return super().run(env, tree, tree_id, target, ignores, run_idx, role)


def _docs_drop_fixture(tmp_path: Path) -> tuple[Fixture, str]:
    fx = Fixture(tmp_path, extra_base={"docs/status.md": STATUS_BASE})
    merge = _drift_then_fix(
        fx,
        {"docs/status.md": "status: drift\nline2\n"},
        {**_fix_with(MUL_TEST), "docs/status.md": "status: fixed\nline2\n"},
    )
    return fx, merge


def test_gold_ref_oracle_run_failure_fails_closed(tmp_path):
    # Codex review round 2: a failed GOLD_REF oracle run must not pass the detector.
    fx, merge = _docs_drop_fixture(tmp_path)
    ctx = _ctx(tmp_path, fx)
    ctx.runner = _TreeTimeoutRunner(
        tmp_path / "work" / "scratch",
        timeout=300,
        log=lambda m: None,
        trees={"goldref"},
        targets={"tests/test_mul.py"},
    )
    task = fx.task(fx.diff_from_base({"pkg/calc.py": FIXED}), merge=merge)
    r = ros.score_task(task, ctx)["receipt"]
    assert (r["label"], r["sub_reason"]) == (ros.NOT_SCORABLE_ORACLE_INVALID, "GOLD_REF_RUN_FAILED")
    assert r["detail"] == "oracle"


def test_gold_ref_p2p_run_failure_excuses_nothing(tmp_path):
    # The candidate breaks add(). GOLD's P2P run times out, which under v1 alone would make
    # the suspect gold_also_fails. GOLD_REF also times out, so v2 excuses nothing, and (review
    # round 4, finding 5) the failure is not counted against the candidate either: the task
    # is NOT_SCORABLE with its own sub-reason.
    fx, merge = _docs_drop_fixture(tmp_path)
    ctx = _ctx(tmp_path, fx)
    ctx.runner = _TreeTimeoutRunner(
        tmp_path / "work" / "scratch",
        timeout=300,
        log=lambda m: None,
        trees={"gold", "goldref"},
        targets={"tests"},
    )
    calc = FIXED.replace("return a + b", "return a - b")
    r = ros.score_task(fx.task(fx.diff_from_base({"pkg/calc.py": calc}), merge=merge), ctx)[
        "receipt"
    ]
    assert r["gold_also_fails"] == []
    assert r["p2p_new_failures"] == []
    assert (r["label"], r["sub_reason"]) == (ros.NOT_SCORABLE_ORACLE_INVALID, "GOLD_REF_RUN_FAILED")
    assert r["p2p_baseline_failures"][-1]["tree"] == "GOLD_REF"


LONG_DOC = "status: {}\n2\n3\n4\n5\n6\n7\n8\n{}\n"


def test_gold_ref_uses_latest_merge_content_for_a_redropped_path(tmp_path, fx):
    # Codex review round 2: PR 1 drops docs/status.md; PR 2 changes it again cleanly.
    up = fx.upstream
    _git(up, "checkout", "-q", "--detach", fx.base)
    _write(up, {"docs/status.md": LONG_DOC.format("base", "end")})
    _git(up, "add", "-A")
    _git(up, "commit", "-qm", "status doc")
    fx.base = _git(up, "rev-parse", "HEAD").strip()
    merge1 = _drift_then_fix(
        fx,
        {"docs/status.md": LONG_DOC.format("drift", "end")},
        {**_fix_with(MUL_TEST), "docs/status.md": LONG_DOC.format("fix1", "end")},
    )
    _write(up, {"docs/status.md": LONG_DOC.format("fix1", "end2")})
    _git(up, "commit", "-qam", "pr2")
    merge2 = _git(up, "rev-parse", "HEAD").strip()
    repo = ros.GitRepo(tmp_path / "scorer-repo", [str(up)])
    for sha in (fx.base, merge1, merge2):
        assert repo.ensure_commit(sha)
    wt = repo.worktree(tmp_path / "wt", fx.base)
    prs = [
        {"number": 1, "merge_commit_sha": merge1},
        {"number": 2, "merge_commit_sha": merge2},
    ]
    port = ros.port_gold(repo, wt, prs)
    assert port.ok
    assert port.dropped_non_code_paths == ["docs/status.md"]
    assert port.dropped_from == {"docs/status.md": merge2}
    assert (wt / "docs/status.md").read_text() == LONG_DOC.format("base", "end2")


def test_gold_ref_node_present_on_one_tree_only_is_a_mismatch(tmp_path):
    # Agy review round 3: a test that is collected only when the dropped doc file has its
    # merge content (failing there) must not compare equal to "absent on GOLD".
    param_test = (
        "import json\nfrom pathlib import Path\n\nimport pytest\n\n"
        'CASES = json.loads(Path("docs/cases.json").read_text())["cases"]\n\n\n'
        '@pytest.mark.parametrize("c", CASES)\n'
        "def test_case(c):\n    assert c == 'never'\n"
    )
    fx = Fixture(tmp_path, extra_base={"docs/cases.json": '{"cases": [],\n "x": 1}\n'})
    merge = _drift_then_fix(
        fx,
        {"docs/cases.json": '{"cases": [],\n "x": 2}\n'},
        {
            **_fix_with(MUL_TEST + "\n\n" + param_test),
            "docs/cases.json": '{"cases": ["new"],\n "x": 3}\n',
        },
    )
    r = _score(tmp_path, fx, fx.task(fx.diff_from_base({"pkg/calc.py": FIXED}), merge=merge))
    assert (r["label"], r["sub_reason"]) == (ros.NOT_SCORABLE_ORACLE_INVALID, "GOLD_PORT_FAILED")
    # GOLD collects an empty-parametrize placeholder; GOLD_REF collects the real case.
    assert "tests.test_mul::test_case[new]" in r["gold_ref_mismatch"]


# Spec v2 review round 4.

GUARD_BASE_TEST = (
    "from pkg.guard import g\n\n\ndef test_placeholder():\n    assert True  # base\n\n\n"
    "def test_guard():\n    assert g() == 1\n"
)
GUARD_DRIFT_TEST = "def test_placeholder():\n    assert True  # drift\n"


def _guard_dropped_by_drift(tmp_path: Path) -> tuple[Fixture, str]:
    # BASE tests/test_mul.py::test_guard guards g(); a later main commit deletes it; the
    # human fix conflicts in that file, so GOLD takes the merge-tree file (no test_guard).
    fx = Fixture(
        tmp_path,
        extra_base={
            "tests/test_mul.py": GUARD_BASE_TEST,
            "pkg/guard.py": "def g():\n    return 1\n",
        },
    )
    merge = _drift_then_fix(
        fx,
        {"tests/test_mul.py": GUARD_DRIFT_TEST},
        _fix_with(GUARD_DRIFT_TEST.replace("# drift", "# fix") + "\n\n" + MUL_TEST),
    )
    return fx, merge


def test_base_test_lost_from_merge_taken_file_is_still_guarded(tmp_path):
    # Review round 4, finding 1 (reviewer repro): the candidate fixes mul() but breaks g().
    # Before: RESOLVED with p2p_new_failures == []. P2P(d) runs the BASE version of the
    # merge-taken file on BASE, CAND, GOLD (all with BASE test bytes) and catches it.
    fx, merge = _guard_dropped_by_drift(tmp_path)
    ctx = _ctx(tmp_path, fx)
    bad = fx.diff_from_base({"pkg/calc.py": FIXED, "pkg/guard.py": "def g():\n    return 2\n"})
    r = ros.score_task(fx.task(bad, merge=merge), ctx)["receipt"]
    assert r["gold_port_test_files_from_merge"] == ["tests/test_mul.py"]
    assert r["p2p_d_targets"] == ["tests/test_mul.py"]
    assert r["p2p_new_failures"] == ["tests.test_mul::test_guard"]
    assert r["label"] == ros.BROKE_EXISTING
    assert {"CAND@BASE_TESTS", "GOLD@BASE_TESTS"} <= set(r["trees"])
    honest = fx.diff_from_base({"pkg/calc.py": FIXED})
    r = ros.score_task(fx.task(honest, merge=merge), ctx)["receipt"]
    assert r["label"] == ros.RESOLVED
    assert r["p2p_d_total"] >= 2  # test_placeholder and test_guard pass on BASE


def test_base_test_the_human_fix_retires_is_gold_also_fails(tmp_path):
    # A BASE test that asserts the old (buggy) behaviour fails on GOLD@BASE_TESTS too, so
    # P2P(d) excuses it and an honest candidate is still RESOLVED.
    old = "from pkg.calc import mul\n\n\ndef test_mul_old():\n    assert mul(2, 3) == 5\n"
    fx = Fixture(tmp_path, extra_base={"tests/test_mul.py": old})
    merge = _drift_then_fix(
        fx,
        {"tests/test_mul.py": old + "\n\ndef test_drift():\n    assert True\n"},
        _fix_with(MUL_TEST),
    )
    r = _score(tmp_path, fx, fx.task(fx.diff_from_base({"pkg/calc.py": FIXED}), merge=merge))
    assert r["gold_port_test_files_from_merge"] == ["tests/test_mul.py"]
    assert r["gold_also_fails"] == ["tests.test_mul::test_mul_old"]
    assert r["label"] == ros.RESOLVED


def test_merge_taken_test_nodes_failing_on_gold_are_counted(tmp_path):
    # Diagnostic only: test_sub_from_drift needs pkg/extra.py from another main commit.
    fx = Fixture(tmp_path, extra_base={"tests/test_mul.py": OLD_MUL_TEST})
    merge = _drift_then_fix(
        fx,
        {"tests/test_mul.py": DRIFT_TEST_SUB, "pkg/extra.py": "def sub(a, b):\n    return a - b\n"},
        _fix_with(DRIFT_TEST_SUB.replace("# drift", "# fix") + "\n\n" + MUL_TEST),
    )
    r = _score(tmp_path, fx, fx.task(fx.diff_from_base({"pkg/calc.py": FIXED}), merge=merge))
    assert r["gold_port_merge_test_nodes_failing_on_gold"] == 1
    assert r["label"] == ros.RESOLVED


def test_merge_taken_conftest_present_at_base_is_refused(tmp_path):
    # A merge-taken conftest.py could change BASE tests in other files that are never
    # re-run at their BASE state, so v2 refuses rather than guess.
    fx = Fixture(tmp_path, extra_base={"tests/conftest.py": "X = 1\n"})
    merge = _drift_then_fix(
        fx,
        {"tests/conftest.py": "X = 2\n"},
        {**_fix_with(MUL_TEST), "tests/conftest.py": "X = 3\n"},
    )
    r = _score(tmp_path, fx, fx.task(fx.diff_from_base({"pkg/calc.py": FIXED}), merge=merge))
    assert (r["label"], r["sub_reason"]) == (ros.NOT_SCORABLE_ORACLE_INVALID, "GOLD_PORT_FAILED")
    assert r["detail"] == "merge_taken_test_support_file:tests/conftest.py"


def test_droppable_classification_excludes_package_and_runtime_data():
    # Review round 4, finding 2.
    assert not ros.is_droppable_non_code("pkg/GUIDE.md", in_python_package=True)
    assert not ros.is_droppable_non_code("nexus/prompts/system.md")
    assert not ros.is_droppable_non_code("app/templates/page.rst")
    assert not ros.is_droppable_non_code("docs/data/table.json")
    assert ros.is_droppable_non_code("docs/guide.md", in_python_package=False)


def test_prose_file_inside_a_python_package_is_never_dropped(tmp_path):
    fx = Fixture(tmp_path, extra_base={"pkg/GUIDE.md": STATUS_BASE})
    merge = _drift_then_fix(
        fx,
        {"pkg/GUIDE.md": "status: drift\nline2\n"},
        {**_fix_with(MUL_TEST), "pkg/GUIDE.md": "status: fixed\nline2\n"},
    )
    r = _score(tmp_path, fx, fx.task(fx.diff_from_base({"pkg/calc.py": FIXED}), merge=merge))
    assert (r["label"], r["sub_reason"]) == (ros.NOT_SCORABLE_ORACLE_INVALID, "GOLD_PORT_FAILED")
    assert r["gold_port_failed_paths"] == ["pkg/GUIDE.md"]


def test_gold_ref_tracks_a_redropped_path_through_a_per_file_port(tmp_path, fx):
    # Review round 4, finding 3: PR 1 drops docs/status.md. PR 2's whole patch fails (its
    # docs/other.md conflicts), and its docs/status.md change applies file by file:
    # GOLD_REF must still use PR 2's merge content for docs/status.md.
    up = fx.upstream
    _git(up, "checkout", "-q", "--detach", fx.base)
    _write(up, {"docs/status.md": LONG_DOC.format("base", "end"), "docs/other.md": "o: base\n"})
    _git(up, "add", "-A")
    _git(up, "commit", "-qm", "docs")
    fx.base = _git(up, "rev-parse", "HEAD").strip()
    merge1 = _drift_then_fix(
        fx,
        {"docs/status.md": LONG_DOC.format("drift", "end"), "docs/other.md": "o: drift\n"},
        {**_fix_with(MUL_TEST), "docs/status.md": LONG_DOC.format("fix1", "end")},
    )
    _write(up, {"docs/status.md": LONG_DOC.format("fix1", "end2"), "docs/other.md": "o: pr2\n"})
    _git(up, "commit", "-qam", "pr2")
    merge2 = _git(up, "rev-parse", "HEAD").strip()
    repo = ros.GitRepo(tmp_path / "scorer-repo", [str(up)])
    for sha in (fx.base, merge1, merge2):
        assert repo.ensure_commit(sha)
    wt = repo.worktree(tmp_path / "wt", fx.base)
    prs = [{"number": 1, "merge_commit_sha": merge1}, {"number": 2, "merge_commit_sha": merge2}]
    port = ros.port_gold(repo, wt, prs)
    assert port.ok
    assert sorted(port.dropped_non_code_paths) == ["docs/other.md", "docs/status.md"]
    assert port.dropped_from == {"docs/status.md": merge2, "docs/other.md": merge2}
    assert (wt / "docs/status.md").read_text() == LONG_DOC.format("base", "end2")


def test_unmerged_entries_left_by_a_file_step_fail_the_port(tmp_path, monkeypatch):
    # Review round 4, finding 4: the final unmerged-index check is the backstop when a
    # per-file step leaves conflict entries behind (here: the undo step is skipped).
    # The dropped prose file sorts last, so no later file step trips over the leftovers.
    fx = Fixture(tmp_path, extra_base={"zz_notes.md": STATUS_BASE})
    merge = _drift_then_fix(
        fx,
        {"zz_notes.md": "status: drift\nline2\n"},
        {**_fix_with(MUL_TEST), "zz_notes.md": "status: fixed\nline2\n"},
    )
    repo = ros.GitRepo(tmp_path / "scorer-repo", [str(fx.upstream)])
    for sha in (fx.base, merge):
        assert repo.ensure_commit(sha)
    wt = repo.worktree(tmp_path / "wt", fx.base)
    real = ros._set_path_from

    def skip_doc_undo(repo_, wt_, rev, path):
        if path != "zz_notes.md":
            real(repo_, wt_, rev, path)

    monkeypatch.setattr(ros, "_set_path_from", skip_doc_undo)
    port = ros.port_gold(repo, wt, [{"number": 7, "merge_commit_sha": merge}])
    assert not port.ok
    assert port.failed_pr == 7
    assert port.failed_paths == []


def test_overwrite_oracle_files_refuses_symlinked_source(tmp_path):
    # Review round 4: copy2 followed links, so an oracle source linking outside the tree
    # copied the outside file in.
    outside = tmp_path / "secret.txt"
    outside.write_text("secret\n")
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "tests").mkdir(parents=True)
    (dst / "tests").mkdir(parents=True)
    (src / "tests/test_x.py").symlink_to(outside)
    with pytest.raises(ros.UnsafeOracleSource):
        ros.overwrite_oracle_files(dst, src, ["tests/test_x.py"])
    assert not (dst / "tests/test_x.py").exists()


def test_symlinked_oracle_source_is_oracle_invalid(tmp_path, fx):
    up = fx.upstream
    _git(up, "checkout", "-q", "--detach", fx.base)
    _write(up, _fix_with(MUL_TEST))
    (up / "tests/test_link.py").symlink_to("/etc/hosts")
    _git(up, "add", "-A")
    _git(up, "commit", "-qm", "human fix with a linked test file")
    merge = _git(up, "rev-parse", "HEAD").strip()
    r = _score(tmp_path, fx, fx.task(fx.diff_from_base({"pkg/calc.py": FIXED}), merge=merge))
    assert (r["label"], r["sub_reason"]) == (ros.NOT_SCORABLE_ORACLE_INVALID, "ORACLE_FILE_UNSAFE")
    assert r["detail"] == "oracle_source_symlink:tests/test_link.py"


def test_gold_ref_p2p_failure_never_makes_a_correct_candidate_broke_existing(tmp_path):
    # Review round 4, finding 5: the honest candidate breaks test_legacy_mul exactly as the
    # human fix does (GOLD fails it too). A timed-out GOLD_REF run used to turn that into a
    # P2P new failure (BROKE_EXISTING); now the task is NOT_SCORABLE.
    fx = Fixture(
        tmp_path, extra_base={"tests/test_legacy.py": LEGACY_TEST, "docs/status.md": STATUS_BASE}
    )
    merge = _drift_then_fix(
        fx,
        {"docs/status.md": "status: drift\nline2\n"},
        {**_fix_with(MUL_TEST), "docs/status.md": "status: fixed\nline2\n"},
    )
    task = fx.task(fx.diff_from_base({"pkg/calc.py": FIXED}), merge=merge)
    r = _score(tmp_path, fx, task)
    assert r["gold_also_fails"] == ["tests.test_legacy::test_legacy_mul"]
    assert r["label"] == ros.RESOLVED
    ctx = _ctx(tmp_path, fx, work="work2")
    ctx.runner = _TreeTimeoutRunner(
        tmp_path / "work2" / "scratch",
        timeout=300,
        log=lambda m: None,
        trees={"goldref"},
        targets={"tests"},
    )
    r = ros.score_task(task, ctx)["receipt"]
    assert (r["label"], r["sub_reason"]) == (ros.NOT_SCORABLE_ORACLE_INVALID, "GOLD_REF_RUN_FAILED")
    assert r["p2p_new_failures"] == []


def test_receipt_spec_version_follows_gold_port_method(tmp_path, fx):
    ctx = _ctx(tmp_path, fx)
    ctx.spec_v2_sha256 = "2" * 64
    r = ros.score_task(fx.task(fx.gold_diff), ctx)["receipt"]
    assert (r["spec_version"], r["spec_sha256"]) == ("v1", "0" * 64)
    (tmp_path / "b").mkdir()
    fx2, merge = _docs_drop_fixture(tmp_path / "b")
    ctx2 = _ctx(tmp_path / "b", fx2)
    ctx2.spec_v2_sha256 = "2" * 64
    r = ros.score_task(fx2.task(fx2.diff_from_base({"pkg/calc.py": FIXED}), merge=merge), ctx2)[
        "receipt"
    ]
    assert (r["spec_version"], r["spec_sha256"]) == ("v2", "2" * 64)


def test_summary_reports_v1_only_and_v1_plus_v2_apart():
    def row(i: int, label: str, version: str | None) -> dict:
        r = {
            "label": label,
            "route": "B",
            "candidate_raw_status": "VALID",
            "capped": False,
            "candidate_empty": False,
            "failure_kind": None,
            "task_key": str(i),
        }
        if version:
            r["spec_version"] = version
        return r

    rows = [row(0, ros.RESOLVED, None), row(1, ros.UNRESOLVED, "v1"), row(2, ros.RESOLVED, "v2")]
    s = ros.summarize(rows)
    assert (s["resolved"], s["valid_oracle_n"]) == (1, 2)  # headline: pre-registered v1
    assert (s["v1_plus_v2"]["resolved"], s["v1_plus_v2"]["valid_oracle_n"]) == (2, 3)
    assert s["spec_version_counts"] == {"v1": 2, "v2": 1}


def test_spec_v2_file_names_v1_sha_and_is_post_hoc():
    root = Path(__file__).resolve().parents[2]
    v2 = (root / ros.SPEC_V2_RELATIVE_PATH).read_text()
    assert "315d95de21ea7ec82c97bf80165feaa052cb8a36fe99f3a1072d45ff74bb2bda" in v2
    assert "not pre-registered" in v2


def test_symlinked_base_oracle_file_in_rule3_trees_is_oracle_invalid(tmp_path):
    # Codex round 4 (P2): the Rule 3 trees copy every oracle file from BASE. A BASE oracle
    # file that is a link is candidate-independent, so it is ORACLE_FILE_UNSAFE, never the
    # candidate's NOT_RUNNABLE/APPLY_FAILED.
    fx = Fixture(tmp_path, extra_base={"tests/test_mul.py": OLD_MUL_TEST})
    up = fx.upstream
    _git(up, "checkout", "-q", "--detach", fx.base)
    (up / "tests/test_ln.py").symlink_to("test_add.py")
    _git(up, "add", "-A")
    _git(up, "commit", "-qm", "linked test at base")
    fx.base = _git(up, "rev-parse", "HEAD").strip()
    _drift_then_fix(
        fx,
        {"tests/test_mul.py": OLD_MUL_TEST.replace("# base", "# drift")},
        _fix_with(OLD_MUL_TEST.replace("# base", "# fix") + "\n\n" + MUL_TEST),
    )
    # The human fix also turns the link into a regular test file (amended into M).
    (up / "tests/test_ln.py").unlink()
    _write(up, {"tests/test_ln.py": "def test_ln():\n    assert True\n"})
    _git(up, "add", "-A")
    _git(up, "commit", "-q", "--amend", "--no-edit")
    merge = _git(up, "rev-parse", "HEAD").strip()
    r = _score(tmp_path, fx, fx.task(fx.diff_from_base({"pkg/calc.py": FIXED}), merge=merge))
    assert r["gold_port_test_files_from_merge"] == ["tests/test_mul.py"]
    assert (r["label"], r["sub_reason"]) == (ros.NOT_SCORABLE_ORACLE_INVALID, "ORACLE_FILE_UNSAFE")
    assert r["detail"] == "oracle_source_symlink:tests/test_ln.py"


# Spec v2 review round 5.


def test_merge_taken_conftest_absent_at_base_is_refused(tmp_path):
    # Review round 5, H1 (Opus repro): main adds tests/conftest.py, which hides
    # tests/test_add.py from collection; the human PR edits it, so GOLD takes it from M.
    # The candidate fixes mul() and breaks add(); BASE+T and CAND+T never collect
    # test_add, so it used to be RESOLVED. Any merge-taken non-module test file is refused.
    fx = Fixture(tmp_path)
    merge = _drift_then_fix(
        fx,
        {"tests/conftest.py": "collect_ignore = ['test_add.py']\n"},
        {**_fix_with(MUL_TEST), "tests/conftest.py": "collect_ignore = ['test_add.py']\nX = 1\n"},
    )
    calc = FIXED.replace("return a + b", "return a - b")
    r = _score(tmp_path, fx, fx.task(fx.diff_from_base({"pkg/calc.py": calc}), merge=merge))
    assert r["gold_port_test_files_from_merge"] == ["tests/conftest.py"]
    assert (r["label"], r["sub_reason"]) == (ros.NOT_SCORABLE_ORACLE_INVALID, "GOLD_PORT_FAILED")
    assert r["detail"] == "merge_taken_test_support_file:tests/conftest.py"


def test_gold_ref_p2p_failure_does_not_hide_a_regression_gold_passes(tmp_path):
    # Review round 5, M1 (Opus repro): the candidate breaks add(), which GOLD passes, so
    # it is a new failure whatever GOLD_REF says. A timed-out GOLD_REF P2P run used to make
    # the task NOT_SCORABLE; GOLD_REF is now run only for suspects that GOLD fails.
    fx, merge = _docs_drop_fixture(tmp_path)
    ctx = _ctx(tmp_path, fx)
    ctx.runner = _TreeTimeoutRunner(
        tmp_path / "work" / "scratch",
        timeout=300,
        log=lambda m: None,
        trees={"goldref"},
        targets={"tests"},
    )
    calc = FIXED.replace("return a + b", "return a - b")
    r = ros.score_task(fx.task(fx.diff_from_base({"pkg/calc.py": calc}), merge=merge), ctx)[
        "receipt"
    ]
    assert (r["label"], r["sub_reason"]) == (ros.BROKE_EXISTING, None)
    assert r["p2p_new_failures"] == ["tests.test_add::test_add"]
    assert all(d["tree"] != "GOLD_REF" for d in r["p2p_baseline_failures"])
    honest = fx.task(fx.diff_from_base({"pkg/calc.py": FIXED}), merge=merge)
    assert ros.score_task(honest, ctx)["receipt"]["label"] == ros.RESOLVED


VERSION_TEST = (
    "import json\nfrom pathlib import Path\n\nfrom pkg import calc\n\n\n"
    "def test_version():\n"
    '    assert calc.VERSION == json.loads(Path("docs/meta.json").read_text())["version"]\n'
)


def test_p2p_failure_explained_by_a_dropped_file_is_not_excused(tmp_path):
    # Review round 5, M2: the A5 core rule. test_version fails on GOLD (meta.json dropped,
    # so still at BASE) but passes on GOLD_REF (merge content). GOLD failing alone must not
    # excuse the candidate, whose VERSION matches neither: BROKE_EXISTING.
    fx = Fixture(
        tmp_path,
        extra_base={
            "pkg/calc.py": BUGGY + "\n\nVERSION = 1\n",
            "docs/meta.json": '{"version": 1,\n "x": 1}\n',
            "tests/test_version.py": VERSION_TEST,
        },
    )
    merge = _drift_then_fix(
        fx,
        {"docs/meta.json": '{"version": 1,\n "x": 2}\n'},
        {
            **_fix_with(MUL_TEST),
            "pkg/calc.py": FIXED + "\n\nVERSION = 2\n",
            "docs/meta.json": '{"version": 2,\n "x": 3}\n',
        },
    )
    cand = fx.diff_from_base({"pkg/calc.py": FIXED + "\n\nVERSION = 3\n"})
    r = _score(tmp_path, fx, fx.task(cand, merge=merge))
    assert r["gold_port_dropped_non_code_paths"] == ["docs/meta.json"]
    assert "tests" in r["p2p_targets"]
    assert r["gold_also_fails"] == []
    assert r["p2p_new_failures"] == ["tests.test_version::test_version"]
    assert r["label"] == ros.BROKE_EXISTING


def _summary_row(i: int, label: str, version: object = None, **extra) -> dict:
    r = {
        "label": label,
        "route": "B",
        "candidate_raw_status": "VALID",
        "capped": False,
        "candidate_empty": False,
        "failure_kind": None,
        "task_key": str(i),
        **extra,
    }
    if version is not None:
        r["spec_version"] = version
    return r


def test_summary_v1_block_maps_v2_receipts_to_gold_port_failed():
    # Review round 5, L1: under v1 a fallback task is NOT_SCORABLE / GOLD_PORT_FAILED.
    rows = [
        _summary_row(0, ros.RESOLVED),
        _summary_row(1, ros.NOT_SCORABLE_ORACLE_INVALID, "v1", sub_reason="GOLD_PORT_FAILED"),
        _summary_row(2, ros.RESOLVED, "v2"),
    ]
    s = ros.summarize(rows)
    assert s["counts"] == {ros.NOT_SCORABLE_ORACLE_INVALID: 2, ros.RESOLVED: 1}
    assert (s["resolved"], s["valid_oracle_n"]) == (1, 1)
    assert s["v1_plus_v2"]["counts"] == {ros.NOT_SCORABLE_ORACLE_INVALID: 1, ros.RESOLVED: 2}
    assert (s["v1_plus_v2"]["resolved"], s["v1_plus_v2"]["valid_oracle_n"]) == (2, 2)
    assert rows[2]["label"] == ros.RESOLVED  # the input receipt is not modified


def test_summary_excludes_unknown_spec_versions():
    # Review round 5, Codex 4: only v1 and v2 receipts are counted in the headline; v3
    # (1.3.0) has its own block, and any other version is in none.
    rows = [_summary_row(0, ros.RESOLVED), _summary_row(1, ros.UNRESOLVED, "v1")]
    before = ros.summarize(rows)
    after = ros.summarize([
        *rows,
        _summary_row(2, ros.RESOLVED, "v4"),
        _summary_row(3, ros.RESOLVED, "v4"),
        _summary_row(4, ros.RESOLVED, ""),
    ])
    for key in ("counts", "resolved", "valid_oracle_n", "ci95"):
        assert after[key] == before[key]
        assert after["v1_plus_v2"][key] == before["v1_plus_v2"][key]
    assert after["unknown_spec_versions"] == {"": 1, "v4": 2}
    assert before["unknown_spec_versions"] == {}
    assert after["spec_version_counts"] == {"": 1, "v1": 2, "v4": 2}
    assert "v3" not in after


@pytest.mark.parametrize("field", ["spec_sha256", "spec_v2_sha256"])
@pytest.mark.parametrize("value", ["", "abc", "A" * 64, "g" * 64, "0" * 63])
def test_score_context_requires_both_spec_hashes(tmp_path, fx, field, value):
    # Review round 5, L2 / Codex 3: a v2 receipt must never carry an empty spec hash.
    kw = {
        "work": tmp_path,
        "env_provider": LocalEnv(),
        "runner": ros.PytestRunner(tmp_path / "scratch", log=lambda m: None),
        "repo_sources": {},
        "spec_sha256": "0" * 64,
        "spec_v2_sha256": "2" * 64,
    }
    ros.ScoreContext(**kw)
    with pytest.raises(ValueError):
        ros.ScoreContext(**{**kw, field: value})


def test_score_context_has_no_default_spec_v2_hash(tmp_path):
    with pytest.raises(TypeError):
        ros.ScoreContext(
            work=tmp_path,
            env_provider=LocalEnv(),
            runner=ros.PytestRunner(tmp_path / "scratch", log=lambda m: None),
            repo_sources={},
            spec_sha256="0" * 64,
        )


def test_unsafe_gold_tree_in_rule3_build_is_oracle_invalid(tmp_path, monkeypatch):
    # Review round 5, L3: GOLD@BASE_TESTS is candidate-independent, so a failure to build
    # it is the oracle's, never the candidate's NOT_RUNNABLE / APPLY_FAILED.
    fx, merge = _guard_dropped_by_drift(tmp_path)
    real = ros.overwrite_oracle_files

    def unsafe_on_gold0(wt, src, files):
        if Path(wt).name == "gold0":
            raise ros.UnsafeTreePath("oracle_path_escapes:tests/test_mul.py")
        real(wt, src, files)

    monkeypatch.setattr(ros, "overwrite_oracle_files", unsafe_on_gold0)
    r = _score(tmp_path, fx, fx.task(fx.diff_from_base({"pkg/calc.py": FIXED}), merge=merge))
    assert (r["label"], r["sub_reason"]) == (ros.NOT_SCORABLE_ORACLE_INVALID, "ORACLE_FILE_UNSAFE")
    assert r["detail"] == "oracle_path_escapes:tests/test_mul.py"


# Amendment A6 (#2291): scratch TMPDIR/HOME cleanup, size receipt, per-run and per-task caps.


def _leak_test(trees: str = "", nbytes: int = 4096, home: bool = False) -> str:
    """Oracle test module that leaks ``nbytes`` into TMPDIR (and HOME) on the named
    scorer trees (cwd names, comma separated; empty = every tree)."""
    return MUL_TEST + (
        "\n\nimport os\nfrom pathlib import Path\n\n\n"
        "def test_leaks_into_tmpdir():\n"
        f"    if {trees!r} and Path.cwd().name not in {trees!r}.split(','):\n"
        "        return\n"
        f"    for var in ['TMPDIR'] + (['HOME'] if {home!r} else []):\n"
        '        d = Path(os.environ[var]) / ("leak-" + Path.cwd().name)\n'
        "        d.mkdir(exist_ok=True)\n"
        f'        (d / "blob.bin").write_bytes(b"x" * {nbytes})\n'
    )


def _scratch(tmp_path: Path) -> Path:
    return tmp_path / "work" / "scratch"


def test_scratch_tmp_is_emptied_after_task_and_size_recorded(tmp_path):
    fx = Fixture(tmp_path, mul_test=_leak_test(home=True))
    result = ros.score_task(fx.task(fx.diff_from_base({"pkg/calc.py": FIXED})), _ctx(tmp_path, fx))
    assert result["receipt"]["label"] == ros.RESOLVED
    # GOLD, BASE+T and CAND+T each leaked 4 KiB into TMPDIR and HOME before the cleanup.
    assert result["timing"]["scratch_tmp_bytes"] >= 3 * 4096
    assert result["timing"]["scratch_home_bytes"] >= 3 * 4096
    assert result["timing"]["scratch_tmp_cleanup_errors"] == []
    for sub in ("tmp", "home"):
        assert list((_scratch(tmp_path) / sub).iterdir()) == []  # leaks and junit gone


def test_scratch_cleanup_errors_are_recorded_not_raised(tmp_path, monkeypatch):
    fx = Fixture(tmp_path)
    monkeypatch.setattr(ros, "clean_scratch_tmp", lambda *a, **k: ["boom"])
    result = ros.score_task(fx.task(fx.diff_from_base({"pkg/calc.py": FIXED})), _ctx(tmp_path, fx))
    assert result["receipt"]["label"] == ros.RESOLVED
    assert result["timing"]["scratch_tmp_cleanup_errors"] == ["boom", "home/boom"]


def test_scratch_tmp_cleanup_keeps_only_live_junit_and_never_follows_links(tmp_path):
    tmp = tmp_path / "tmp"
    outside = tmp_path / "outside"
    (outside / "ro").mkdir(parents=True)
    (outside / "keep.txt").write_text("keep")
    (outside / "ro").chmod(0o500)
    (tmp / "nested" / "ro").mkdir(parents=True)
    (tmp / "nested" / "ro" / "f").write_bytes(b"y" * 10)
    (tmp / "nested" / "outlink").symlink_to(outside / "ro", target_is_directory=True)
    (tmp / "nested" / "ro").chmod(0o500)
    (tmp / "nested").chmod(0o500)
    (tmp / "junit-live.xml").write_text("<testsuite/>")
    (tmp / "junit-planted.xml").write_text("<testsuite/>")  # a test cannot persist files
    (tmp / "loose.bin").write_bytes(b"z" * 7)
    (tmp / "link").symlink_to(outside, target_is_directory=True)
    # A11: allocated size (st_blocks * 512), so each small file counts whole blocks.
    files = [tmp / "nested" / "ro" / "f", tmp / "junit-live.xml", tmp / "junit-planted.xml"]
    files.append(tmp / "loose.bin")
    # Independent of allocated_bytes: the blocks the OS reports, and never below the bytes.
    assert ros.tree_bytes(tmp) == sum(os.lstat(f).st_blocks * 512 for f in files)
    assert ros.tree_bytes(tmp) >= 10 + 2 * len("<testsuite/>") + 7
    try:
        assert ros.clean_scratch_tmp(tmp, keep={"junit-live.xml"}) == []
        assert sorted(p.name for p in tmp.iterdir()) == ["junit-live.xml"]
        assert (outside / "keep.txt").read_text() == "keep"
        # The read-only directory behind the link kept its mode: chmod never followed it.
        assert (outside / "ro").stat().st_mode & 0o777 == 0o500
    finally:
        (outside / "ro").chmod(0o700)


def test_scratch_tmp_cleanup_never_raises(tmp_path, monkeypatch):
    tmp = tmp_path / "tmp"
    tmp.mkdir()

    def denied(_path):
        raise PermissionError("denied")

    monkeypatch.setattr(ros.os, "scandir", denied)
    errors = ros.clean_scratch_tmp(tmp)
    assert len(errors) == 1 and errors[0].startswith("scandir:PermissionError")


def _cap_receipt(tmp_path, monkeypatch, trees: str, **fixture_kw):
    monkeypatch.setattr(ros, "SCRATCH_TMP_CAP_BYTES", 1000)
    fx = Fixture(tmp_path, mul_test=_leak_test(trees), **fixture_kw)
    result = ros.score_task(fx.task(fx.diff_from_base({"pkg/calc.py": FIXED})), _ctx(tmp_path, fx))
    assert list((_scratch(tmp_path) / "tmp").iterdir()) == []
    return result["receipt"]


def test_scratch_tmp_cap_on_gold_is_oracle_invalid(tmp_path, monkeypatch):
    r = _cap_receipt(tmp_path, monkeypatch, "gold")
    assert (r["label"], r["sub_reason"]) == (ros.NOT_SCORABLE_ORACLE_INVALID, ros.ORACLE_RUN_FAILED)
    assert r["detail"].startswith(f"{ros.SCRATCH_TMP_CAP_EXCEEDED}:GOLD:")


def test_scratch_tmp_cap_on_base_t_is_oracle_invalid(tmp_path, monkeypatch):
    # Without A6 handling, BASE+T's empty outcomes would make every GOLD-pass node F2P.
    r = _cap_receipt(tmp_path, monkeypatch, "baset")
    assert (r["label"], r["sub_reason"]) == (ros.NOT_SCORABLE_ORACLE_INVALID, ros.ORACLE_RUN_FAILED)
    assert r["detail"].startswith(f"{ros.SCRATCH_TMP_CAP_EXCEEDED}:BASE+T:")
    assert "f2p" not in r


def test_scratch_tmp_cap_on_cand_t_is_not_runnable(tmp_path, monkeypatch):
    r = _cap_receipt(tmp_path, monkeypatch, "candt")
    assert (r["label"], r["sub_reason"]) == (ros.NOT_RUNNABLE, ros.SCRATCH_TMP_CAP_EXCEEDED)
    assert r["detail"].startswith(f"{ros.SCRATCH_TMP_CAP_EXCEEDED}:CAND+T:")
    assert ros.CAND_ROLE in r["detail"]
    assert "shadow_label" not in r


def test_scratch_task_cap_fails_the_task(tmp_path, monkeypatch):
    monkeypatch.setattr(ros, "SCRATCH_TMP_TASK_CAP_BYTES", 6000)
    fx = Fixture(tmp_path, mul_test=_leak_test())
    result = ros.score_task(fx.task(fx.diff_from_base({"pkg/calc.py": FIXED})), _ctx(tmp_path, fx))
    r = result["receipt"]
    # Each tree leaks 4 KiB once (under the per-run cap): GOLD's leak fits, BASE+T's
    # crosses the task cap.
    assert (r["label"], r["sub_reason"]) == (
        ros.NOT_SCORABLE_ORACLE_INVALID,
        ros.SCRATCH_TMP_TASK_CAP_EXCEEDED,
    )
    assert r["detail"].startswith(f"{ros.SCRATCH_TMP_TASK_CAP_EXCEEDED}:BASE+T:")


def _leak_tree(tmp_path: Path, nbytes: int) -> Path:
    tree = tmp_path / "tree"
    _write(
        tree,
        {
            "tests/test_leak.py": (
                "import os\nfrom pathlib import Path\n\n\ndef test_leak():\n"
                f'    (Path(os.environ["TMPDIR"]) / "blob").write_bytes(b"x" * {nbytes})\n'
            )
        },
    )
    return tree


def _runner(tmp_path: Path) -> ros.PytestRunner:
    return ros.PytestRunner(tmp_path / "scratch", timeout=300, log=lambda m: None)


def test_node_ids_are_relative_to_the_tree_inside_an_outer_pytest_repo(tmp_path):
    outer = tmp_path / "outer"
    _write(outer, {"pytest.ini": "[pytest]\n"})
    tree = outer / "work" / "tree"
    _write(tree, {"tests/test_a.py": "def test_a():\n    pass\n"})
    env = LocalEnv().get("fixture-repo", tree)
    runner = ros.PytestRunner(outer / "work" / "scratch", timeout=300, log=lambda m: None)
    assert runner.run(env, tree, "t", "tests", (), 0).outcomes == {"tests.test_a::test_a": ros.PASS}


def test_scratch_tmp_cap_run_is_not_cached(tmp_path, monkeypatch):
    tree = _leak_tree(tmp_path, 100)
    env = LocalEnv().get("fixture-repo", tree)
    runner = _runner(tmp_path)
    ok = runner.run(env, tree, "t1", "tests", (), 0)
    assert ok.diagnostic is None and ok.outcomes == {"tests.test_leak::test_leak": ros.PASS}
    tmp_bytes, home_bytes, errors = runner.clean_tmp()
    assert tmp_bytes >= 100 and errors == []
    monkeypatch.setattr(ros, "SCRATCH_TMP_CAP_BYTES", 50)
    n_cached = len(list(runner.cache.iterdir()))
    for _ in range(2):  # re-executed every time: a cap failure is never replayed
        with pytest.raises(ros.ScratchTmpCapExceeded) as exc:
            runner.run(env, tree, "t2", "tests", (), 0)
        assert exc.value.kind == ros.SCRATCH_TMP_CAP_EXCEEDED
        assert exc.value.left_bytes >= 100
        assert (exc.value.result.outcomes, exc.value.result.exit_code) == (
            {},
            ros.SCRATCH_TMP_CAP_EXIT_CODE,
        )
        runner.clean_tmp()
    assert len(list(runner.cache.iterdir())) == n_cached


def test_scratch_tmp_cap_is_per_run_delta(tmp_path, monkeypatch):
    tree = _leak_tree(tmp_path, 10)
    env = LocalEnv().get("fixture-repo", tree)
    runner = _runner(tmp_path)
    runner.tmp.mkdir(parents=True)
    (runner.tmp / "earlier-run.bin").write_bytes(b"x" * 200_000)  # left by an earlier run
    # A11: allocated bytes; the 10-byte leak is one block, well under the cap.
    monkeypatch.setattr(ros, "SCRATCH_TMP_CAP_BYTES", 100_000)
    assert runner.run(env, tree, "t", "tests", (), 0).outcomes


def test_scratch_tmp_cap_excludes_own_junit(tmp_path, monkeypatch):
    tree = _leak_tree(tmp_path, 0)
    env = LocalEnv().get("fixture-repo", tree)
    runner = _runner(tmp_path)
    # The junit report alone is a few hundred bytes; the run leaves nothing else.
    monkeypatch.setattr(ros, "SCRATCH_TMP_CAP_BYTES", 20)
    monkeypatch.setattr(ros, "SCRATCH_TMP_TASK_CAP_BYTES", 20)
    assert runner.run(env, tree, "t", "tests", (), 0).outcomes


def test_run_kills_leftover_children_of_the_run(tmp_path):
    tree = tmp_path / "tree"
    _write(
        tree,
        {
            "tests/test_spawn.py": (
                "import subprocess\n\n\ndef test_spawn():\n"
                "    subprocess.Popen(['/bin/sh', '-c', 'sleep 1; echo x > \"$TMPDIR/orphan\"'])\n"
            )
        },
    )
    env = LocalEnv().get("fixture-repo", tree)
    runner = _runner(tmp_path)
    assert runner.run(env, tree, "t", "tests", (), 0).outcomes
    time.sleep(2)
    assert not (runner.tmp / "orphan").exists()


def test_symlinked_scratch_tmp_is_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_text("keep")
    tree = _leak_tree(tmp_path, 1)
    env = LocalEnv().get("fixture-repo", tree)
    runner = _runner(tmp_path)
    runner.scratch.mkdir(parents=True, exist_ok=True)
    runner.tmp.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ros.ScratchUnsafe):
        runner.run(env, tree, "t", "tests", (), 0)
    with pytest.raises(ros.ScratchUnsafe):
        runner.clean_tmp()
    assert (outside / "keep").read_text() == "keep"


def test_second_scorer_on_same_work_dir_fails_fast(tmp_path, fx):
    fcntl = pytest.importorskip("fcntl")
    ctx = _ctx(tmp_path, fx)
    ctx.work.mkdir(parents=True, exist_ok=True)
    with open(ctx.work / ros.SCORER_LOCK_NAME, "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ros.ScorerBusy):
            ros.score_task(fx.task(fx.diff_from_base({"pkg/calc.py": FIXED})), ctx)
    # Released: the next task scores normally.
    assert ros.score_task(fx.task(fx.gold_diff), ctx)["receipt"]["label"] == ros.RESOLVED


def test_scratch_task_cap_on_candidate_run_is_not_runnable(tmp_path, monkeypatch):
    # Only CAND+T leaks: under the per-run cap, but over the task cap. A leaky candidate
    # must stay in the denominator (NOT_RUNNABLE), never be dropped as not scorable.
    monkeypatch.setattr(ros, "SCRATCH_TMP_TASK_CAP_BYTES", 3000)
    fx = Fixture(tmp_path, mul_test=_leak_test("candt"))
    r = ros.score_task(fx.task(fx.diff_from_base({"pkg/calc.py": FIXED})), _ctx(tmp_path, fx))[
        "receipt"
    ]
    assert (r["label"], r["sub_reason"]) == (ros.NOT_RUNNABLE, ros.SCRATCH_TMP_TASK_CAP_EXCEEDED)
    assert r["detail"].startswith(f"{ros.SCRATCH_TMP_TASK_CAP_EXCEEDED}:CAND+T:")
    assert "shadow_label" not in r


def test_scratch_home_leak_counts_toward_per_run_cap(tmp_path, monkeypatch):
    tree = tmp_path / "tree"
    _write(
        tree,
        {
            "tests/test_home.py": (
                "import os\nfrom pathlib import Path\n\n\ndef test_home():\n"
                '    (Path(os.environ["HOME"]) / "blob").write_bytes(b"x" * 5000)\n'
            )
        },
    )
    env = LocalEnv().get("fixture-repo", tree)
    runner = _runner(tmp_path)
    monkeypatch.setattr(ros, "SCRATCH_TMP_CAP_BYTES", 1000)
    with pytest.raises(ros.ScratchTmpCapExceeded) as exc:
        runner.run(env, tree, "t", "tests", (), 0)
    assert exc.value.kind == ros.SCRATCH_TMP_CAP_EXCEEDED and exc.value.left_bytes >= 5000


# Amendment A9: opt-in OS sandbox for pytest runs (default "none" = v1 §8 unchanged).


def _os_runner(scratch: Path, timeout: int = 300, **kw) -> ros.PytestRunner | None:
    """A bound "os" runner where the OS barrier exists (macOS).

    Without one (Linux CI, or a disable variable set) these tests never skip: they assert
    the fail-closed path instead (the runner refuses before creating anything, so nothing
    can run) and return None, after which the caller returns.
    """
    # A11: "os" needs an existing store dir (denied to every confined run).
    kw.setdefault("store", scratch.parent / "_store")
    Path(kw["store"]).mkdir(parents=True, exist_ok=True)
    if sandboxed_lane.os_sandbox_available():
        return ros.PytestRunner(
            scratch, timeout=timeout, log=lambda m: None, sandbox=ros.SANDBOX_OS, **kw
        )
    with pytest.raises(sandboxed_lane.SandboxError, match="no_os_barrier"):
        ros.PytestRunner(scratch, timeout=timeout, log=lambda m: None, sandbox=ros.SANDBOX_OS, **kw)
    assert not scratch.exists()
    return None


SANDBOX_PROBE_TEST = (
    "import os, socket\n"
    "from pathlib import Path\n\n\n"
    "def test_ok():\n    pass\n\n\n"
    "def test_net():\n"
    "    socket.create_connection(('1.1.1.1', 53), timeout=2).close()\n\n\n"
    "def test_net_denied_by_barrier():\n"
    "    try:\n"
    "        socket.create_connection(('1.1.1.1', 53), timeout=2).close()\n"
    "    except PermissionError:\n"
    "        return\n"
    "    raise AssertionError('connect was not refused by the sandbox')\n\n\n"
    "def test_write_outside():\n"
    "    (Path(__file__).resolve().parents[2] / 'escape.txt').write_text('x')\n\n\n"
    "def test_kill_own_child():\n"
    "    import signal, subprocess\n"
    "    child = subprocess.Popen(['/bin/sleep', '30'])\n"
    "    os.kill(child.pid, signal.SIGKILL)\n"
    "    assert child.wait(timeout=10) == -signal.SIGKILL\n\n\n"
    "def test_signal_outside_denied():\n"
    "    try:\n"
    "        os.kill(1, 0)\n"
    "    except PermissionError:\n"
    "        return\n"
    "    raise AssertionError('signalled a process outside the run')\n\n\n"
    "def test_write_allowed():\n"
    "    (Path(os.environ['TMPDIR']) / 'ok.txt').write_text('x')\n"
    "    (Path(os.environ['HOME']) / 'ok.txt').write_text('x')\n"
    "    (Path(__file__).resolve().parent / 'ok.txt').write_text('x')\n"
)


def _sandbox_probe_tree(tmp_path: Path) -> Path:
    tree = tmp_path / "trees" / "tree"
    _write(tree, {"tests/test_probe.py": SANDBOX_PROBE_TEST})
    return tree


def test_default_sandbox_none_runs_the_v1_command_and_env(tmp_path, monkeypatch):
    tree = tmp_path / "tree"
    _write(tree, {"tests/test_a.py": "def test_a():\n    pass\n"})
    env = LocalEnv().get("fixture-repo", tree)
    runner = _runner(tmp_path)
    assert runner.sandbox == ros.SANDBOX_NONE
    seen: list[tuple[list[str], dict[str, str]]] = []
    real_popen = subprocess.Popen

    def spy(cmd, **kwargs):
        seen.append((list(cmd), dict(kwargs["env"])))
        return real_popen(cmd, **kwargs)

    monkeypatch.setattr(ros.subprocess, "Popen", spy)
    key = runner.result_key(env, "t", "tests", ["b", "a"], 0)
    assert runner.run(env, tree, "t", "tests", ["b", "a"], 0).outcomes
    junit = runner.tmp / f"junit-{key}.xml"
    pythonpath = ":".join([str(tree), *env.extra_pythonpath])
    # Exactly the 1.2.3 command and env (spec §8 + A8 --rootdir): no sandbox-exec wrapper.
    assert seen == [
        (
            [
                sys.executable,
                "-m",
                "pytest",
                "tests",
                "-q",
                "-p",
                "no:cacheprovider",
                f"--rootdir={tree.resolve()}",
                f"--junitxml={junit}",
                "--ignore=a",
                "--ignore=b",
            ],
            {
                "PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin",
                "HOME": str(runner.scratch / "home"),
                "TMPDIR": str(runner.scratch / "tmp"),
                "PYTHONPATH": pythonpath,
                "PYTHONHASHSEED": "0",
                "PYTHONDONTWRITEBYTECODE": "1",
                "LANG": "en_US.UTF-8",
                "TZ": "UTC",
            },
        )
    ]
    # The "none" result key is the 1.2.3 formula (no sandbox component).
    assert key == ros.sha256_bytes(
        json.dumps([env.cache_key, "t", "tests", ["a", "b"], 0, ""]).encode()
    )


def test_sandbox_mode_separates_result_cache_keys(tmp_path):
    env = LocalEnv().get("fixture-repo", tmp_path)
    runner = _runner(tmp_path)
    none_key = runner.result_key(env, "t", "tests", [], 0, "cand")
    runner.sandbox = ros.SANDBOX_OS  # key only; no run (works without a barrier)
    runner.store = tmp_path / "store"
    os_key = runner.result_key(env, "t", "tests", [], 0, "cand")
    assert none_key != os_key
    assert os_key == ros.sha256_bytes(
        json.dumps([
            env.cache_key,
            "t",
            "tests",
            [],
            0,
            "cand",
            "sandbox:os",
            f"profile:{runner.sandbox_profile_sha256}",
        ]).encode()
    )


def _hash_runner(scratch: Path, **kw) -> ros.PytestRunner:
    kw.setdefault("store", scratch.parent / "_store")
    runner = ros.PytestRunner(scratch, log=lambda m: None, **kw)
    runner.sandbox = ros.SANDBOX_OS  # the hash needs no barrier, so this runs everywhere
    return runner


def test_sandbox_profile_hash_ignores_work_dir_and_home(tmp_path, monkeypatch):
    assert ros.PytestRunner(tmp_path / "none", log=lambda m: None).sandbox_profile_sha256 is None
    first = _hash_runner(tmp_path / "a" / "work" / "scratch").sandbox_profile_sha256
    monkeypatch.setenv("HOME", str(tmp_path / "other-home"))
    second = _hash_runner(tmp_path / "b" / "elsewhere" / "scratch").sandbox_profile_sha256
    assert first == second and len(first or "") == 64


def test_sandbox_profile_hash_and_result_key_track_profile_changes(tmp_path, monkeypatch):
    env = LocalEnv().get("fixture-repo", tmp_path)
    before = _hash_runner(tmp_path / "s1")
    before_key = before.result_key(env, "t", "tests", [], 0)  # hashes the real profile
    real = sandboxed_lane.build_sandbox_profile

    def without_child_signals(**kwargs):
        return real(**{**kwargs, "allow_signal_same_sandbox": False})

    monkeypatch.setattr(sandboxed_lane, "build_sandbox_profile", without_child_signals)
    after = _hash_runner(tmp_path / "s2")
    assert before.sandbox_profile_sha256 != after.sandbox_profile_sha256
    assert before_key != after.result_key(env, "t", "tests", [], 0)
    # A11: there is no store-less "os" profile, so no hash for one either.
    no_store = _hash_runner(tmp_path / "s3", store=None)
    with pytest.raises(sandboxed_lane.SandboxError, match="store_required"):
        no_store.sandbox_profile_sha256


def test_shared_profile_signals_stay_self_only_unless_asked(tmp_path):
    kwargs = {"writable": [str(tmp_path)], "read_roots": [str(tmp_path)]}
    default = sandboxed_lane.build_sandbox_profile(**kwargs)
    widened = sandboxed_lane.build_sandbox_profile(**kwargs, allow_signal_same_sandbox=True)
    assert "same-sandbox" not in default and "(allow signal (target self))" in default
    assert widened.splitlines() == [
        *default.splitlines()[: default.splitlines().index("(allow signal (target self))") + 1],
        "(allow signal (target same-sandbox))",
        *default.splitlines()[default.splitlines().index("(allow signal (target self))") + 1 :],
    ]


def test_unknown_sandbox_mode_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        ros.PytestRunner(tmp_path / "scratch", sandbox="docker")


@pytest.mark.parametrize("how", ["probe", "env_var"])
def test_sandbox_os_refuses_without_a_barrier(tmp_path, monkeypatch, how):
    if how == "probe":
        monkeypatch.setattr(sandboxed_lane, "os_sandbox_available", lambda: False)
    else:
        monkeypatch.setenv("NEXUS_DISABLE_OS_SANDBOX", "1")
    with pytest.raises(sandboxed_lane.SandboxError, match="no_os_barrier"):
        ros.PytestRunner(tmp_path / "scratch", sandbox=ros.SANDBOX_OS, store=tmp_path)


def test_sandbox_os_run_refuses_when_barrier_disappears(tmp_path, monkeypatch):
    """A runner bound to "os" never falls back to an unconfined run."""
    tree = tmp_path / "tree"
    _write(tree, {"tests/test_a.py": "def test_a():\n    pass\n"})
    env = LocalEnv().get("fixture-repo", tree)
    runner = _runner(tmp_path)
    runner.sandbox = ros.SANDBOX_OS
    runner.store = tmp_path / "store"
    monkeypatch.setattr(sandboxed_lane, "os_sandbox_available", lambda: False)

    def no_popen(*a, **k):
        raise AssertionError("ran without the OS barrier")

    monkeypatch.setattr(ros.subprocess, "Popen", no_popen)
    with pytest.raises(sandboxed_lane.SandboxError, match="no_os_barrier"):
        runner.run(env, tree, "t", "tests", (), 0)
    assert list(runner.cache.iterdir()) == []


def test_cli_sandbox_os_refuses_before_scoring(tmp_path, monkeypatch, capsys):
    from nexus.research import score_real_outcome_cli as cli

    monkeypatch.setattr(cli, "os_sandbox_available", lambda: False)

    def no_scoring(*a, **k):
        raise AssertionError("scored without the OS barrier")

    monkeypatch.setattr(cli.ros, "score_task", no_scoring)
    monkeypatch.setattr(cli.ros, "load_sealed_task", no_scoring)
    store = tmp_path / "store"
    (store / "tasks").mkdir(parents=True)
    rc = cli.main([
        "--store",
        str(store),
        "--out",
        str(tmp_path / "out"),
        "--work",
        str(tmp_path / "work"),
        "--task",
        "James3014__nexus-runtime--1",
        "--sandbox",
        "os",
    ])
    assert rc == 7
    assert "refusing to score unconfined" in capsys.readouterr().err
    assert not (tmp_path / "out").exists() and not (tmp_path / "work").exists()


def test_cli_sandbox_defaults_to_none():
    from nexus.research import score_real_outcome_cli as cli

    assert cli.parse_args(["--out", "o"]).sandbox == ros.SANDBOX_NONE
    assert cli.parse_args(["--out", "o", "--sandbox", "os"]).sandbox == ros.SANDBOX_OS
    with pytest.raises(SystemExit):
        cli.parse_args(["--out", "o", "--sandbox", "docker"])


def test_receipt_records_runner_sandbox_none(tmp_path, fx):
    receipt = ros.score_task(fx.task(b""), _ctx(tmp_path, fx), candidate_override="empty")[
        "receipt"
    ]
    assert receipt["runner_sandbox"] == ros.SANDBOX_NONE
    assert receipt["runner_sandbox_profile_sha256"] is None


def test_sandbox_os_denies_network_and_outside_writes(tmp_path):
    tree = _sandbox_probe_tree(tmp_path)
    env = LocalEnv().get("fixture-repo", tree)
    confined = _os_runner(tmp_path / "scratch-os")
    if confined is None:
        return
    res = confined.run(env, tree, "t", "tests", (), 0)
    node = "tests.test_probe::"
    assert res.outcomes == {
        node + "test_ok": ros.PASS,
        node + "test_net": ros.FAIL,
        node + "test_net_denied_by_barrier": ros.PASS,
        node + "test_write_outside": ros.FAIL,
        node + "test_kill_own_child": ros.PASS,
        node + "test_signal_outside_denied": ros.PASS,
        node + "test_write_allowed": ros.PASS,
    }
    assert not (tmp_path / "trees" / "escape.txt").exists()
    # The unconfined run of the same tree gives the same node ids, and its outside write
    # succeeds (network is not blocked there, so its test_net outcome is not asserted).
    plain = ros.PytestRunner(tmp_path / "scratch-none", timeout=300, log=lambda m: None)
    unconfined = plain.run(env, tree, "t", "tests", (), 0).outcomes
    assert set(unconfined) == set(res.outcomes)
    assert unconfined[node + "test_ok"] == ros.PASS
    assert unconfined[node + "test_write_outside"] == ros.PASS
    assert unconfined[node + "test_net_denied_by_barrier"] == ros.FAIL


def test_sandbox_os_keeps_timeout_and_group_kill(tmp_path):
    tree = tmp_path / "tree"
    _write(
        tree,
        {
            "tests/test_spawn.py": (
                "import subprocess, time\n\n\ndef test_spawn():\n"
                "    subprocess.Popen(['/bin/sh', '-c', 'sleep 5; echo x > \"$TMPDIR/orphan\"'])\n"
                "    time.sleep(60)\n"
            )
        },
    )
    env = LocalEnv().get("fixture-repo", tree)
    runner = _os_runner(tmp_path / "scratch", timeout=2)
    if runner is None:
        return
    res = runner.run(env, tree, "t", "tests", (), 0)
    assert (res.timed_out, res.exit_code, res.outcomes) == (True, -1, {})
    time.sleep(5)  # the orphan would have written by now had it survived the group kill
    assert not (runner.tmp / "orphan").exists()


def test_sandbox_os_gold_self_check_resolves_and_is_recorded(tmp_path, fx):
    ctx = _ctx(tmp_path, fx)
    runner = _os_runner(ctx.work / "scratch-os")
    if runner is None:
        return
    ctx.runner = runner
    receipt = ros.score_task(fx.task(b""), ctx, candidate_override="gold")["receipt"]
    assert receipt["runner_sandbox"] == ros.SANDBOX_OS
    assert receipt["runner_sandbox_profile_sha256"] == runner.sandbox_profile_sha256
    assert len(runner.sandbox_profile_sha256 or "") == 64
    assert receipt["label"] == ros.RESOLVED


# A9 review fixes: per-run HOME/TMPDIR in "os" mode, extra import roots, unreadable paths.

LEAK_WRITER_TEST = (
    "import json, os\n"
    "from pathlib import Path\n\n\n"
    "def test_leave_fix(tmp_path):\n"
    "    paths = [\n"
    "        Path(os.environ['TMPDIR']) / 'leak-gold.txt',\n"
    "        Path(os.environ['HOME']) / 'leak-gold.txt',\n"
    "        tmp_path / 'leak-gold.txt',\n"
    "    ]\n"
    "    for path in paths:\n"
    "        path.write_text('the fix')\n"
    "    out = Path(__file__).resolve().parent / 'paths.json'\n"
    "    out.write_text(json.dumps([str(p) for p in paths]))\n"
)

READ_DENIED_TEST = (
    "import json, os\n"
    "from pathlib import Path\n\n\n"
    "def test_cannot_read():\n"
    "    paths = json.loads((Path(__file__).resolve().parent / 'targets.json').read_text())\n"
    "    readable = []\n"
    "    for p in paths:\n"
    "        try:\n"
    "            Path(p).read_text()\n"
    "        except OSError:\n"
    "            continue\n"
    "        readable.append(p)\n"
    "    scratch = Path(os.environ['TMPDIR']).parents[2]\n"
    "    for root in (Path(os.environ['TMPDIR']), Path(os.environ['HOME']), scratch):\n"
    "        try:\n"
    "            found = list(root.rglob('leak-*'))\n"
    "        except OSError:\n"
    "            continue\n"
    "        for f in found:\n"
    "            try:\n"
    "                f.read_text()\n"
    "            except OSError:\n"
    "                continue\n"
    "            readable.append(str(f))\n"
    "    assert readable == []\n"
)


def test_sandbox_os_gold_leftovers_are_invisible_to_a_later_candidate_run(tmp_path):
    work = tmp_path / "work"
    gold = work / "trees" / "task" / "gold"
    cand = work / "trees" / "task" / "cand"
    _write(gold, {"tests/test_gold.py": LEAK_WRITER_TEST})
    _write(cand, {"tests/test_cand.py": READ_DENIED_TEST})
    env = LocalEnv().get("fixture-repo", gold)
    runner = _os_runner(work / "scratch")
    if runner is None:
        return
    res = runner.run(env, gold, "g", "tests", (), 0, role="GOLD")
    assert res.outcomes == {"tests.test_gold::test_leave_fix": ros.PASS}
    leaked = json.loads((gold / "tests" / "paths.json").read_text())
    assert len(leaked) == 3
    # The GOLD run's own HOME/TMPDIR were per-run and are gone; nothing reached the shared ones.
    assert not any(Path(p).exists() for p in leaked)
    assert list(runner.runs.iterdir()) == []
    assert ros.tree_bytes(runner.tmp) == 0 and ros.tree_bytes(runner.home) == 0
    (cand / "tests" / "targets.json").write_text(json.dumps(leaked))
    res = runner.run(env, cand, "c", "tests", (), 0, role="CAND+T")
    assert res.outcomes == {"tests.test_cand::test_cannot_read": ros.PASS}
    assert list(runner.runs.iterdir()) == []


def test_sandbox_os_session_escaping_child_cannot_touch_the_next_run(tmp_path):
    work = tmp_path / "work"
    first = work / "trees" / "task" / "first"
    second = work / "trees" / "task" / "second"
    attack = (
        'S="$TMPDIR/../../.."; end=$(($(date +%s) + 8)); '
        'while [ "$(date +%s)" -lt "$end" ]; do '
        'echo x > "$S/tmp/planted"; echo x > "$S/home/planted"; '
        'echo "{}" > "$S/pytest-cache/planted.json"; '
        'for d in "$S"/runs/*; do echo x > "$d/tmp/planted"; echo junk > "$d/junit.xml"; done; '
        "sleep 0.1; done"
    )
    _write(
        first,
        {
            "tests/test_escape.py": (
                "import subprocess\nfrom pathlib import Path\n\n\n"
                "def test_escape():\n"
                f"    child = subprocess.Popen(['/bin/sh', '-c', {attack!r}],"
                " start_new_session=True)\n"
                "    (Path(__file__).resolve().parent / 'child.pid').write_text(str(child.pid))\n"
            )
        },
    )
    _write(
        second,
        {
            "tests/test_next.py": (
                "import os, time\nfrom pathlib import Path\n\n\n"
                "def test_next():\n"
                "    time.sleep(2)\n"
                "    assert not (Path(os.environ['TMPDIR']) / 'planted').exists()\n"
            )
        },
    )
    env = LocalEnv().get("fixture-repo", first)
    runner = _os_runner(work / "scratch")
    if runner is None:
        return
    assert runner.run(env, first, "a", "tests", (), 0).outcomes == {
        "tests.test_escape::test_escape": ros.PASS
    }
    pid = int((first / "tests" / "child.pid").read_text())
    try:
        res = runner.run(env, second, "b", "tests", (), 0)
        os.kill(pid, 0)  # the escaped child really outlived the first run's group kill
    finally:
        with contextlib.suppress(OSError):
            os.kill(pid, 9)
    assert (res.outcomes, res.exit_code, res.timed_out) == (
        {"tests.test_next::test_next": ros.PASS},
        0,
        False,
    )
    assert not [p for p in runner.scratch.rglob("planted*")]
    key = runner.result_key(env, "b", "tests", (), 0)
    cached = json.loads((runner.cache / f"{key}.json").read_text())
    assert cached["outcomes"] == {"tests.test_next::test_next": ros.PASS}


@pytest.mark.parametrize("which", ["work", "work_parent", "repos", "trees", "store"])
def test_sandbox_os_refuses_extra_import_roots_covering_work(tmp_path, monkeypatch, which):
    work = tmp_path / "w" / "work"
    store = tmp_path / "store"
    tree = work / "trees" / "task" / "cand"
    _write(tree, {"tests/test_a.py": "def test_a():\n    pass\n"})
    root = {
        "work": work,
        "work_parent": work.parent,
        "repos": work / "repos" / "r",
        "trees": work / "trees" / "task" / "gold",
        "store": store / "tasks",
    }[which]
    root.mkdir(parents=True, exist_ok=True)
    runner = ros.PytestRunner(work / "scratch", log=lambda m: None, store=store)
    runner.sandbox = ros.SANDBOX_OS  # the check runs before any barrier-specific step
    monkeypatch.setattr(sandboxed_lane, "os_sandbox_available", lambda: True)

    def no_popen(*a, **k):
        raise AssertionError("ran with an overbroad import root")

    monkeypatch.setattr(ros.subprocess, "Popen", no_popen)
    env = ros.TestEnv("e", sys.executable, "fixture", extra_pythonpath=(str(root),))
    with pytest.raises(sandboxed_lane.SandboxError, match="read_root_overbroad"):
        runner.run(env, tree, "t", "tests", (), 0)
    assert list(runner.runs.iterdir()) == [] and list(runner.cache.iterdir()) == []


def test_sandbox_os_cannot_read_repos_sibling_trees_or_home(tmp_path):
    import shutil
    import tempfile

    work = tmp_path / "work"
    store = tmp_path / "store"
    runner = _os_runner(work / "scratch", store=store)
    if runner is None:
        return
    cand = work / "trees" / "task" / "cand"
    _write(cand, {"tests/test_cand.py": READ_DENIED_TEST})
    secrets = [
        work / "repos" / "repo" / ".git" / "secret.txt",
        work / "trees" / "task" / "gold" / "secret.txt",
        store / "tasks" / "secret.txt",
    ]
    home_dir = Path(tempfile.mkdtemp(prefix=".wt-83-probe-", dir=Path.home()))
    try:
        secrets.append(home_dir / "secret.txt")
        for path in secrets:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("secret")
        (cand / "tests" / "targets.json").write_text(json.dumps([str(p) for p in secrets]))
        env = LocalEnv().get("fixture-repo", cand)
        node = "tests.test_cand::test_cannot_read"
        res = runner.run(env, cand, "c", "tests", (), 0)
        assert res.outcomes == {node: ros.PASS}
        # Control: unconfined, the same test reads them all (so the paths are real).
        plain = ros.PytestRunner(tmp_path / "plain", timeout=300, log=lambda m: None)
        assert plain.run(env, cand, "c", "tests", (), 0).outcomes == {node: ros.FAIL}
    finally:
        shutil.rmtree(home_dir, ignore_errors=True)


@pytest.mark.parametrize("where", ["work_bin", "work_itself", "trees", "repos", "store"])
def test_sandbox_os_refuses_an_interpreter_or_env_dir_covering_work(tmp_path, monkeypatch, where):
    """Env dir / interpreter prefix are read roots too: one covering <work> would expose
    sibling trees (GOLD), so it is refused before anything runs."""
    work = tmp_path / "w" / "work"
    store = tmp_path / "store"
    tree = work / "trees" / "task" / "cand"
    _write(tree, {"tests/test_a.py": "def test_a():\n    pass\n"})
    python = {
        "work_bin": work / "bin" / "python",  # env dir == <work>
        "work_itself": work / "python",  # env dir == <work>'s parent
        "trees": work / "trees" / "task" / "gold" / "venv" / "bin" / "python",
        "repos": work / "repos" / "r" / "venv" / "bin" / "python",
        "store": store / "venv" / "bin" / "python",
    }[where]
    python.parent.mkdir(parents=True, exist_ok=True)
    python.symlink_to(sys.executable)
    runner = ros.PytestRunner(work / "scratch", log=lambda m: None, store=store)
    runner.sandbox = ros.SANDBOX_OS  # the check runs before any barrier-specific step
    monkeypatch.setattr(sandboxed_lane, "os_sandbox_available", lambda: True)

    def no_popen(*a, **k):
        raise AssertionError("ran with an overbroad read root")

    monkeypatch.setattr(ros.subprocess, "Popen", no_popen)
    env = ros.TestEnv("e", str(python), "fixture")
    with pytest.raises(sandboxed_lane.SandboxError, match="read_root_overbroad"):
        runner.run(env, tree, "t", "tests", (), 0)
    assert list(runner.runs.iterdir()) == [] and list(runner.cache.iterdir()) == []


def test_sandbox_os_uv_env_layout_is_accepted(tmp_path, monkeypatch):
    """The scorer's own layout (<work>/envs/<key>/bin/python) is not overbroad."""
    work = tmp_path / "work"
    tree = work / "trees" / "task" / "cand"
    _write(tree, {"tests/test_a.py": "def test_a():\n    pass\n"})
    python = work / "envs" / "abc" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    runner = ros.PytestRunner(work / "scratch", log=lambda m: None, store=tmp_path / "store")
    runner.sandbox = ros.SANDBOX_OS
    monkeypatch.setattr(sandboxed_lane, "os_sandbox_available", lambda: True)
    launch = runner._confine(ros.TestEnv("e", str(python), "fixture"), tree, work / "scratch" / "r")
    assert launch[:2] == [sandboxed_lane.SANDBOX_EXEC, "-p"]
    assert str((work / "envs" / "abc").resolve()) in launch[2]


def test_sandbox_os_survivor_growth_in_a_recreated_run_dir_is_counted(tmp_path, monkeypatch):
    work = tmp_path / "work"
    runner = _os_runner(work / "scratch")
    if runner is None:
        return
    first = work / "trees" / "task" / "first"
    second = work / "trees" / "task" / "second"
    grow = _survivor_script(5000)
    _write(
        first,
        {
            "tests/test_survivor.py": (
                "import subprocess\nfrom pathlib import Path\n\n\n"
                "def test_survivor():\n"
                f"    child = subprocess.Popen(['/bin/sh', '-c', {grow!r}],"
                " start_new_session=True)\n"
                "    (Path(__file__).resolve().parent / 'child.pid').write_text(str(child.pid))\n"
            )
        },
    )
    # A11: the survivor can re-create its dir only while a later run of the same scoring
    # has re-created the task parent; this run keeps it there for 3 s (the survivor
    # retries every 0.1 s, so no fixed race with the cleanup).
    _write(
        second,
        {"tests/test_next.py": "import time\n\n\ndef test_next():\n    time.sleep(3)\n"},
    )
    env = LocalEnv().get("fixture-repo", first)
    assert runner.run(env, first, "a", "tests", (), 0).outcomes
    pid = int((first / "tests" / "child.pid").read_text())
    try:
        monkeypatch.setattr(ros, "SCRATCH_TMP_TASK_CAP_BYTES", 1000)
        with pytest.raises(ros.ScratchTmpCapExceeded) as exc:
            runner.run(env, second, "b", "tests", (), 0)
        assert exc.value.kind == ros.SCRATCH_TMP_TASK_CAP_EXCEEDED
        assert exc.value.left_bytes >= 4096  # the survivor's re-created dir was counted
    finally:
        with contextlib.suppress(OSError):
            os.kill(pid, 9)
    runner.clean_tmp()
    assert list(runner.runs.iterdir()) == []


def test_sandbox_profile_hash_and_confine_share_one_root_source(tmp_path, monkeypatch):
    work = tmp_path / "work"
    tree = work / "trees" / "task" / "cand"
    tree.mkdir(parents=True)
    before = _hash_runner(work / "scratch").sandbox_profile_sha256
    monkeypatch.setattr(ros, "_PROFILE_ROOT_SPEC", (*ros._PROFILE_ROOT_SPEC, ("read", "new_kind")))
    runner = _hash_runner(work / "scratch")
    assert runner.sandbox_profile_sha256 != before
    # _confine must supply a real value for every kind of the same source.
    monkeypatch.setattr(sandboxed_lane, "os_sandbox_available", lambda: True)
    env = ros.TestEnv("e", sys.executable, "fixture")
    with pytest.raises(KeyError, match="new_kind"):
        runner._confine(env, tree, work / "scratch" / "runs" / "r")


def _record_tree_paths(monkeypatch) -> list[Path]:
    seen: list[Path] = []
    real = ros.GitRepo.worktree

    def spy(self, dest, sha):
        seen.append(Path(dest))
        return real(self, dest, sha)

    monkeypatch.setattr(ros.GitRepo, "worktree", spy)
    return seen


def test_tree_paths_stay_fixed_in_none_mode(tmp_path, fx, monkeypatch):
    seen = _record_tree_paths(monkeypatch)
    task = fx.task(b"")
    receipt = ros.score_task(task, _ctx(tmp_path, fx), candidate_override="gold")["receipt"]
    assert receipt["label"] == ros.RESOLVED
    assert seen and {p.parent for p in seen} == {tmp_path / "work" / "trees" / task.name}


def test_sandbox_os_rescoring_uses_fresh_tree_paths(tmp_path, fx, monkeypatch):
    """A survivor that keeps planting a conftest.py at the previous scoring's tree paths
    never reaches the next scoring of the same task."""
    import shutil
    import threading

    ctx = _ctx(tmp_path, fx)
    runner = _os_runner(ctx.work / "scratch-os")
    if runner is None:
        return
    ctx.runner = runner
    seen = _record_tree_paths(monkeypatch)
    task = fx.task(b"")
    first = ros.score_task(task, ctx, candidate_override="gold")["receipt"]
    assert first["label"] == ros.RESOLVED
    first_paths = list(seen)
    seen.clear()
    assert {p.parent.parent for p in first_paths} == {ctx.work / "trees"}
    assert all(p.parent.name.startswith(task.name + "-") for p in first_paths)
    stop = threading.Event()

    def plant() -> None:
        while not stop.is_set():
            for path in first_paths:
                with contextlib.suppress(OSError):
                    path.mkdir(parents=True, exist_ok=True)
                    (path / "conftest.py").write_text("raise RuntimeError('planted')\n")
            time.sleep(0.02)

    planter = threading.Thread(target=plant, daemon=True)
    shutil.rmtree(runner.cache)
    runner.cache.mkdir()  # the second scoring really runs the tests again
    planter.start()
    try:
        second = ros.score_task(task, ctx, candidate_override="gold")["receipt"]
    finally:
        stop.set()
        planter.join()
    assert second["label"] == ros.RESOLVED
    assert seen and not set(seen) & set(first_paths)


# Spec v3 (A10, #2709): metadata-only stub for the BASE project, opt-in.

V3_PYPROJECT = '[project]\nname = "Nexus.Certify_Demo"\nversion = "0.3.0"\n'


def _venv(tmp: Path) -> tuple[Path, Path]:
    """A fresh venv (no pip) and its single site-packages directory."""
    env_dir = tmp / "env"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(env_dir)],
        check=True,
        capture_output=True,
    )
    site = ros._site_packages(env_dir)
    assert site is not None
    return env_dir, site


def _env_python(env_dir: Path, code: str, pythonpath: Path | None, cwd: Path):
    env = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
    if pythonpath is not None:
        env["PYTHONPATH"] = str(pythonpath)
    return subprocess.run(
        [str(env_dir / "bin" / "python"), "-c", code],
        env=env,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_v3_stub_has_normalized_name_and_metadata_version_works(tmp_path):
    base = tmp_path / "base"
    _write(base, {"pyproject.toml": V3_PYPROJECT, "product/__init__.py": "VALUE = 'base'\n"})
    env_dir, site = _venv(tmp_path)
    stub, reason = ros.write_project_metadata_stub(base, site)
    assert reason is None and stub is not None
    assert stub == {
        "name": "Nexus.Certify_Demo",
        "version": "0.3.0",
        "dist_info": "nexus_certify_demo-0.3.0.dist-info",
    }
    dist = site / stub["dist_info"]
    assert sorted(p.name for p in dist.iterdir()) == ["INSTALLER", "METADATA", "RECORD", "WHEEL"]
    assert (dist / "WHEEL").read_text() == (
        "Wheel-Version: 1.0\nGenerator: nexus-real-outcome-scorer\nRoot-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    )
    listed = [line.split(",")[0] for line in (dist / "RECORD").read_text().splitlines()]
    assert sorted(listed) == sorted(
        f"{stub['dist_info']}/{f}" for f in ("INSTALLER", "METADATA", "RECORD", "WHEEL")
    )
    assert (dist / "METADATA").read_text() == (
        "Metadata-Version: 2.1\nName: Nexus.Certify_Demo\nVersion: 0.3.0\n"
    )
    for line in (dist / "RECORD").read_text().splitlines():
        path, digest, size = line.split(",")
        if path.endswith("/RECORD"):
            assert (digest, size) == ("", "")
            continue
        body = (site / path).read_bytes()
        want = base64.urlsafe_b64encode(hashlib.sha256(body).digest()).rstrip(b"=").decode()
        assert (digest, int(size)) == (f"sha256={want}", len(body))
    tree = tmp_path / "tree"
    shutil.copytree(base, tree)
    code = (
        "import importlib.metadata as m\n"
        "print(m.version('nexus-certify-demo'), m.version('Nexus_Certify.Demo'))"
    )
    out = _env_python(env_dir, code, tree, tmp_path)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["0.3.0", "0.3.0"]


def test_v3_stub_never_shadows_the_tree(tmp_path):
    base = tmp_path / "base"
    _write(base, {"pyproject.toml": V3_PYPROJECT, "product/__init__.py": "VALUE = 'base'\n"})
    env_dir, site = _venv(tmp_path)
    before = {p.relative_to(env_dir) for p in env_dir.rglob("*")}
    stub, _ = ros.write_project_metadata_stub(base, site)
    assert stub is not None
    added = {p.relative_to(env_dir) for p in env_dir.rglob("*")} - before
    dist_rel = site.relative_to(env_dir) / stub["dist_info"]
    assert added == {
        dist_rel,
        *(dist_rel / f for f in ("INSTALLER", "METADATA", "RECORD", "WHEEL")),
    }
    assert not [p for p in added if p.suffix in {".pth", ".py", ".pyc", ".so", ".json"}]
    tree = tmp_path / "tree"
    shutil.copytree(base, tree)
    (tree / "product" / "__init__.py").write_text("VALUE = 'tree'\n")
    code = "import product, importlib.metadata as m; print(product.VALUE, product.__file__)"
    out = _env_python(env_dir, code, tree, tmp_path)
    assert out.returncode == 0, out.stderr
    value, file = out.stdout.split()
    assert value == "tree" and Path(file).resolve().is_relative_to(tree.resolve())
    # Without the tree on PYTHONPATH the project code is not importable at all.
    out = _env_python(env_dir, "import product", None, tmp_path)
    assert out.returncode != 0 and "ModuleNotFoundError" in out.stderr


@pytest.mark.parametrize(
    ("pyproject", "reason"),
    [
        ('[project]\nname = "x"\ndynamic = ["version"]\n', "dynamic_version"),
        ('[project]\nname = "x"\n', "version_missing"),
        ("[tool.x]\na = 1\n", "no_project_table"),
        ('[project]\nversion = "1"\n', "project_name_missing_or_invalid"),
        ("[project\n", "pyproject_unreadable:TOMLDecodeError"),
        (None, "no_pyproject_toml"),
    ],
)
def test_v3_no_static_version_means_no_stub_and_a_reason(tmp_path, pyproject, reason):
    base = tmp_path / "base"
    base.mkdir()
    if pyproject is not None:
        (base / "pyproject.toml").write_text(pyproject)
    site = tmp_path / "site"
    site.mkdir()
    assert ros.write_project_metadata_stub(base, site) == (None, reason)
    assert list(site.iterdir()) == []


@pytest.mark.parametrize(
    ("entry", "metadata"),
    [
        ("nexus_certify_demo-0.2.0.dist-info", None),
        ("nexus-certify-demo-0.2.0.dist-info", None),
        ("Nexus.Certify.Demo-0.2.0.dist-info", None),
        ("nexus_certify_demo-0.2.0-py3.12.egg-info", None),
        ("nexus_certify_demo.egg-info", "file"),
        ("odd-name-9.dist-info", "Name: Nexus-Certify.DEMO\n"),
    ],
)
def test_v3_stub_refuses_when_project_already_installed(tmp_path, entry, metadata):
    base = tmp_path / "base"
    _write(base, {"pyproject.toml": V3_PYPROJECT})
    site = tmp_path / "site"
    site.mkdir()
    if metadata == "file":  # an egg-info that is itself the PKG-INFO file
        (site / entry).write_text("Metadata-Version: 1.0\nName: nexus-certify-demo\n")
    else:
        (site / entry).mkdir()
        if metadata:
            (site / entry / "METADATA").write_text(metadata)
    assert ros.write_project_metadata_stub(base, site) == (
        None,
        f"project_already_installed:{entry}",
    )
    assert sorted(p.name for p in site.iterdir()) == [entry]


def test_v3_stub_survives_deeply_nested_pyproject(tmp_path):
    base = tmp_path / "base"
    deep = "[" * 100000 + "]" * 100000
    _write(base, {"pyproject.toml": f'[project]\nname = "demo"\nversion = "1.0"\nx = {deep}\n'})
    site = tmp_path / "site"
    site.mkdir()
    stub, reason = ros.write_project_metadata_stub(base, site)
    assert stub is None and reason == "pyproject_unreadable:RecursionError"
    assert list(site.iterdir()) == []


def test_v3_stub_ignores_other_projects_with_a_shared_prefix(tmp_path):
    base = tmp_path / "base"
    _write(base, {"pyproject.toml": V3_PYPROJECT})
    site = tmp_path / "site"
    other = site / "nexus_certify_demo_extra-1.0.dist-info"
    other.mkdir(parents=True)
    (other / "METADATA").write_text("Metadata-Version: 2.1\nName: nexus-certify-demo-extra\n")
    (site / "nexus_certify_demo_tools.egg-info").mkdir()  # no Name, rest is not a version
    (site / "nexus_certify_demo-2bar-1.0.dist-info").mkdir()  # no Name; "2bar" is no version
    stub, reason = ros.write_project_metadata_stub(base, site)
    assert reason is None and stub is not None
    assert stub["dist_info"] == "nexus_certify_demo-0.3.0.dist-info"


@pytest.mark.parametrize(
    ("name", "version", "reason"),
    [
        ('"demo\\n"', '"1.0"', "project_name_missing_or_invalid"),
        ('"d\u00e9mo"', '"1.0"', "project_name_missing_or_invalid"),
        ('"\u212aelvin"', '"1.0"', "project_name_missing_or_invalid"),  # KELVIN SIGN
        ('"../x"', '"1.0"', "project_name_missing_or_invalid"),
        ('"a/b"', '"1.0"', "project_name_missing_or_invalid"),
        ('"demo"', '"1.0\\n"', "version_invalid"),
        ('"demo"', '" 1.0"', "version_invalid"),
        ('"demo"', '"1.\u0661"', "version_invalid"),  # ARABIC-INDIC DIGIT ONE
        ('"demo"', '"../1.0"', "version_invalid"),
        ('"demo"', '"1.0/x"', "version_invalid"),
        ('"demo"', '"not-a-version"', "version_invalid"),
        ('"demo"', "1", "version_invalid"),
    ],
)
def test_v3_stub_rejects_unsafe_name_or_version(tmp_path, name, version, reason):
    base = tmp_path / "base"
    base.mkdir()
    (base / "pyproject.toml").write_text(f"[project]\nname = {name}\nversion = {version}\n")
    site = tmp_path / "site"
    site.mkdir()
    assert ros.write_project_metadata_stub(base, site) == (None, reason)
    assert list(site.iterdir()) == []


def test_v3_version_fallback_regex_without_packaging(tmp_path, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_packaging(name, *a, **k):
        if name.startswith("packaging"):
            raise ImportError(name)
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_packaging)
    for good in ("1.0", "0.3.0", "1!2.0rc1.post2.dev3+local.1", "2.0b1"):
        assert ros._valid_version(good), good
    for bad in ("1.0\n", "x1", "1.0/x", "..", "1..0", "1.0+", ""):
        assert not ros._valid_version(bad), bad


class _FakeUv:
    """Stands in for ``subprocess`` inside UvEnvProvider: records argv and env, and lays
    out an env directory the way ``uv sync`` / ``uv venv`` would."""

    TimeoutExpired = subprocess.TimeoutExpired

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, str] | None]] = []

    def run(self, cmd, **kw):
        self.calls.append((list(cmd), kw.get("env")))
        out = ""
        if cmd[:3] == ["uv", "python", "find"]:
            out = "/uv/python3.12\n"
        elif cmd[:1] == ["uv"] and cmd[1:2] == ["--version"]:
            out = "uv 0.0.test\n"
        elif len(cmd) > 1 and cmd[1] == "-c":
            out = "3.12.7\n"
        elif cmd[:2] == ["uv", "sync"]:
            env_dir = Path(kw["env"]["UV_PROJECT_ENVIRONMENT"])
            (env_dir / "lib" / "python3.12" / "site-packages").mkdir(parents=True)
        elif cmd[:2] == ["uv", "venv"]:
            (Path(cmd[-1]) / "lib" / "python3.12" / "site-packages").mkdir(parents=True)
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")


LEARNING_PIN = "a" * 40


def _recipe_bases(tmp: Path) -> dict[str, tuple[str, Path]]:
    nexus = tmp / "nexus-new"
    _write(
        nexus,
        {
            "pyproject.toml": V3_PYPROJECT,
            "uv.lock": "lock\n",
            "requirements/canonical-learning.txt": "x==1\n",
            "requirements/canonical-runtime.txt": "y==1\n",
        },
    )
    groups = tmp / "core"
    _write(groups, {"pyproject.toml": V3_PYPROJECT, "uv.lock": "lock\n"})
    pins = tmp / "runtime"
    _write(
        pins,
        {
            "pyproject.toml": V3_PYPROJECT,
            ".github/workflows/tests.yml": (
                f"  repository: James3014/nexus-learning\n  ref: {LEARNING_PIN}\n"
            ),
        },
    )
    return {
        "uv-sync-all-extras+canonical": ("Nexus-new", nexus),
        "uv-sync-all-groups": ("nexus-core", groups),
        "uv-venv-runtime-pins": ("nexus-runtime", pins),
    }


def _build(tmp: Path, monkeypatch, spec_version: str | None, repo: str, base: Path):
    fake = _FakeUv()
    monkeypatch.setattr(ros, "subprocess", fake)
    kw = {} if spec_version is None else {"spec_version": spec_version}
    provider = ros.UvEnvProvider(tmp / f"envs-{spec_version}-{repo}", log=lambda m: None, **kw)
    env = provider.get(repo, base)
    return env, fake.calls, provider


def _v124_key(repo: str, recipe: str, base: Path) -> str:
    """The 1.2.4 env-key formula, copied verbatim (only SCORER_VERSION moved on)."""
    files = [
        "pyproject.toml",
        "uv.lock",
        "requirements/canonical-learning.txt",
        "requirements/canonical-runtime.txt",
    ]
    digests = {f: ros.sha256_bytes((base / f).read_bytes()) for f in files if (base / f).exists()}
    if recipe == "uv-venv-runtime-pins":
        digests["learning_pin"] = LEARNING_PIN
    interp = {"path": "/uv/python3.12", "version": "3.12.7"}
    parts = [repo, recipe, "3.12", digests, interp, [], ros.SCORER_VERSION]
    return ros.sha256_bytes(json.dumps(parts, sort_keys=True).encode())


def _v124_argv(recipe: str, base: Path, env_dir: Path) -> list[list[str]]:
    py = str(env_dir / "bin" / "python")
    if recipe == "uv-venv-runtime-pins":
        return [
            ["uv", "venv", "-q", "--python", "3.12", str(env_dir)],
            [
                "uv", "pip", "install", "--python", py, *ros.UvEnvProvider.RUNTIME_PINS,
                "nexus-learning @ git+https://github.com/James3014/nexus-learning.git@"
                + LEARNING_PIN,
            ],
        ]  # fmt: skip
    sync = [
        "uv", "sync", "--directory", str(base), "--frozen", "--all-groups",
        "--no-install-project", "--python", "3.12",
    ]  # fmt: skip
    if recipe == "uv-sync-all-groups":
        return [sync]
    return [
        [*sync, "--all-extras"],
        ["uv", "pip", "install", "--python", py, "-r", str(base / "requirements/canonical-learning.txt")],
        ["uv", "pip", "install", "--python", py, "-r", str(base / "requirements/canonical-runtime.txt")],
    ]  # fmt: skip


@pytest.mark.parametrize("recipe", list(ros.NO_INSTALL_PROJECT_RECIPES) + ["uv-venv-runtime-pins"])
def test_v1_default_env_build_is_unchanged(tmp_path, monkeypatch, recipe):
    repo, base = _recipe_bases(tmp_path)[recipe]
    env, calls, provider = _build(tmp_path, monkeypatch, None, repo, base)
    assert provider.spec_version == ros.SPEC_V1
    assert env.recipe == recipe
    assert env.key == _v124_key(repo, recipe, base)
    env_dir = provider.envs_dir / env.key[:16]
    build = [(c, e) for c, e in calls if c[:2] in (["uv", "sync"], ["uv", "venv"], ["uv", "pip"])]
    assert [c for c, _ in build] == _v124_argv(recipe, base, env_dir)
    want_env = {k: v for k, v in os.environ.items() if k not in {"VIRTUAL_ENV", "PYTHONPATH"}}
    want_env["UV_PROJECT_ENVIRONMENT"] = str(env_dir)
    assert all(e == want_env for _, e in build)
    assert set(env.description) == {
        "python",
        "python_path",
        "scorer_version",
        "uv",
        "recipe",
        "inputs",
    }
    assert not list(env_dir.rglob("*.dist-info"))
    assert env.cache_key == ros.sha256_bytes(
        json.dumps([env.key, env.python, "3.12.7", [], ros.SCORER_VERSION], sort_keys=True).encode()
    )


@pytest.mark.parametrize("recipe", list(ros.NO_INSTALL_PROJECT_RECIPES) + ["uv-venv-runtime-pins"])
def test_v3_env_build_adds_only_the_stub_and_a_separate_key(tmp_path, monkeypatch, recipe):
    repo, base = _recipe_bases(tmp_path)[recipe]
    v1, v1_calls, _ = _build(tmp_path, monkeypatch, "v1", repo, base)
    v3, v3_calls, provider = _build(tmp_path, monkeypatch, "v3", repo, base)
    assert v1.key != v3.key and v1.cache_key != v3.cache_key
    env_dir = provider.envs_dir / v3.key[:16]
    v1_dir = tmp_path / f"envs-v1-{repo}" / v1.key[:16]
    # Same commands and environment apart from the env directory itself.
    assert [c for c, _ in v3_calls] == [
        [a.replace(str(v1_dir), str(env_dir)) for a in c] for c, _ in v1_calls
    ]
    assert v3.description["spec_version"] == "v3"
    stub = json.loads(v3.description["project_metadata_stub"])
    reason = json.loads(v3.description["project_metadata_stub_reason"])
    dists = sorted(p.name for p in env_dir.rglob("*.dist-info"))
    if recipe == "uv-venv-runtime-pins":
        assert (stub, reason) == (None, "recipe_without_project_install:uv-venv-runtime-pins")
        assert dists == []
    else:
        assert reason is None
        assert stub["dist_info"] == "nexus_certify_demo-0.3.0.dist-info"
        assert dists == [stub["dist_info"]]
    # A cached v3 env keeps its stub record.
    again = provider.get(repo, base)
    assert again.description == v3.description


def test_v3_dynamic_version_env_records_reason(tmp_path, monkeypatch):
    base = tmp_path / "core"
    _write(
        base, {"pyproject.toml": '[project]\nname = "x"\ndynamic = ["version"]\n', "uv.lock": "l\n"}
    )
    env, _, provider = _build(tmp_path, monkeypatch, "v3", "nexus-core", base)
    assert json.loads(env.description["project_metadata_stub"]) is None
    assert json.loads(env.description["project_metadata_stub_reason"]) == "dynamic_version"
    assert not list((provider.envs_dir / env.key[:16]).rglob("*.dist-info"))


def test_spec_version_is_validated():
    with pytest.raises(ValueError):
        ros.UvEnvProvider(Path("e"), spec_version="v2")
    ctx: dict[str, Any] = {
        "work": Path("w"),
        "env_provider": None,
        "runner": None,
        "repo_sources": {},
        "spec_sha256": "0" * 64,
        "spec_v2_sha256": "2" * 64,
    }
    with pytest.raises(ValueError, match="spec_v3_sha256"):
        ros.ScoreContext(**ctx, spec_version="v3")
    with pytest.raises(ValueError):
        ros.ScoreContext(**ctx, spec_version="v2")
    ros.ScoreContext(**ctx)  # v1 needs no v3 hash


class _StubLocalEnv(LocalEnv):
    """LocalEnv plus the v3 stub, written to an extra import root (a dist-info directory
    is found on any sys.path entry, as in site-packages)."""

    def __init__(self, root: Path):
        self.root = root

    def get(self, repo: str, base_wt: Path) -> ros.TestEnv:
        env = super().get(repo, base_wt)
        site = self.root / "site"
        shutil.rmtree(site, ignore_errors=True)
        site.mkdir(parents=True)
        stub, reason = ros.write_project_metadata_stub(base_wt, site)
        desc = {
            "spec_version": "v3",
            "project_metadata_stub": json.dumps(stub, sort_keys=True),
            "project_metadata_stub_reason": json.dumps(reason),
        }
        return ros.TestEnv(
            "fixture-env-v3", env.python, "fixture", desc, (*env.extra_pythonpath, str(site))
        )


METADATA_TEST = (
    "import importlib.metadata\n\nVERSION = importlib.metadata.version('fixture-proj')\n\n\n"
    "def test_version():\n    assert VERSION == '1.0'\n"
)


def _v3_ctx(tmp: Path, fx: Fixture, work: str = "work-v3", env=None) -> ros.ScoreContext:
    ctx = _ctx(tmp, fx, work=work)
    return dataclasses.replace(
        ctx,
        env_provider=env or ctx.env_provider,
        spec_version="v3",
        spec_v3_sha256="3" * 64,
    )


def test_v3_stub_restores_p2p_and_catches_a_regression(tmp_path):
    # The #2709 shape: a BASE test reads the project's own metadata at import time.
    fx = Fixture(
        tmp_path,
        extra_base={
            "pyproject.toml": '[project]\nname = "fixture-proj"\nversion = "1.0"\n',
            "tests/test_version.py": METADATA_TEST,
        },
    )
    broken = fx.diff_from_base({"pkg/calc.py": FIXED.replace("return a + b", "return a - b")})
    task = fx.task(broken)
    v1 = ros.score_task(task, _ctx(tmp_path, fx))["receipt"]
    v3 = ros.score_task(task, _v3_ctx(tmp_path, fx, env=_StubLocalEnv(tmp_path / "stub")))[
        "receipt"
    ]
    # v1: `pytest tests` stops at PackageNotFoundError, so the regression is invisible.
    assert v1["label"] == ros.RESOLVED and v1["p2p_total"] == 0
    assert v3["label"] == ros.BROKE_EXISTING
    assert "tests.test_add::test_add" in v3["p2p_new_failures"]
    assert v3["p2p_total"] >= 2
    assert (v3["spec_version"], v3["spec_sha256"], v3["spec_v3_base_rules"]) == (
        "v3",
        "3" * 64,
        "v1",
    )
    assert v3["project_metadata_stub"] == {
        "name": "fixture-proj",
        "version": "1.0",
        "dist_info": "fixture_proj-1.0.dist-info",
    }
    assert v3["project_metadata_stub_reason"] is None
    same = {"name": "fixture-proj", "version": "1.0"}
    assert v3["project_metadata_tree_versions"] == {"GOLD": same, "CAND": same}
    assert v3["project_metadata_version_mismatch"] is False
    assert "project_metadata_tree_versions" not in v1
    gold_ctx = _v3_ctx(tmp_path, fx, work="w-gold", env=_StubLocalEnv(tmp_path / "s2"))
    gold = ros.score_task(task, gold_ctx, candidate_override="gold")["receipt"]
    assert gold["label"] == ros.RESOLVED


def test_v3_flags_a_candidate_project_version_without_changing_the_label(tmp_path):
    pyproject = '[project]\nname = "fixture-proj"\nversion = "1.0"\n'
    fx = Fixture(
        tmp_path,
        extra_base={"pyproject.toml": pyproject, "tests/test_version.py": METADATA_TEST},
    )
    bumped = fx.diff_from_base({
        "pkg/calc.py": FIXED,
        "pyproject.toml": pyproject.replace('"1.0"', '"1.1"'),
    })
    ctx = _v3_ctx(tmp_path, fx, env=_StubLocalEnv(tmp_path / "stub"))
    r = ros.score_task(fx.task(bumped), ctx)["receipt"]
    # The env carries BASE's metadata (1.0), so the BASE test still passes: RESOLVED.
    assert r["label"] == ros.RESOLVED
    assert r["project_metadata_stub"]["version"] == "1.0"
    assert r["project_metadata_tree_versions"] == {
        "GOLD": {"name": "fixture-proj", "version": "1.0"},
        "CAND": {"name": "fixture-proj", "version": "1.1"},
    }
    assert r["project_metadata_version_mismatch"] is True


def test_v1_receipt_shape_is_unchanged(tmp_path, fx):
    r = ros.score_task(fx.task(fx.gold_diff), _ctx(tmp_path, fx))["receipt"]
    assert (r["spec_version"], r["spec_sha256"]) == ("v1", "0" * 64)
    assert not {
        "spec_v3_base_rules",
        "project_metadata_stub",
        "project_metadata_stub_reason",
        "project_metadata_tree_versions",
        "project_metadata_version_mismatch",
    } & set(r)
    pending = ros.score_task(fx.task(terminal=None), _ctx(tmp_path, fx, work="w2"))["receipt"]
    assert set(pending) == V124_BASE_RECEIPT_KEYS | {"flaky_dropped"}


# The keys of a 1.2.4 receipt before any scoring step (``_base_receipt``).
V124_BASE_RECEIPT_KEYS = {
    "schema",
    "scorer_version",
    "runner_sandbox",
    "runner_sandbox_profile_sha256",
    "spec_sha256",
    "spec_version",
    "task_key",
    "repo",
    "issue",
    "route",
    "base_sha",
    "candidate_digest",
    "candidate_empty",
    "candidate_override",
    "candidate_raw_status",
    "failure_kind",
    "scope_valid",
    "capped",
    "leakage_flags",
    "label",
    "sub_reason",
    "shadow_label",
}


def test_v3_receipt_with_a_provider_without_stub_and_with_the_a5_fallback(tmp_path, fx):
    r = ros.score_task(fx.task(fx.gold_diff), _v3_ctx(tmp_path, fx))["receipt"]
    assert r["label"] == ros.RESOLVED
    assert (r["project_metadata_stub"], r["project_metadata_stub_reason"]) == (
        None,
        "env_provider_without_v3_stub",
    )
    (tmp_path / "b").mkdir()
    fx2, merge = _docs_drop_fixture(tmp_path / "b")
    task = fx2.task(fx2.diff_from_base({"pkg/calc.py": FIXED}), merge=merge)
    r = ros.score_task(task, _v3_ctx(tmp_path / "b", fx2))["receipt"]
    assert r["gold_port_method"] != "3way"
    assert (r["spec_version"], r["spec_sha256"], r["spec_v3_base_rules"]) == ("v3", "3" * 64, "v2")


def _golden_rows() -> list[dict]:
    def row(i, label, version=None, **extra):
        r = {
            "label": label,
            "route": "B" if i % 2 else "C",
            "candidate_raw_status": "VALID" if i % 3 else "TIMEOUT",
            "capped": i % 4 == 0,
            "candidate_empty": i == 5,
            "failure_kind": None,
            "task_key": f"t{i}",
            "leakage_flags": ["x"] if i == 2 else [],
            **extra,
        }
        if version is not None:
            r["spec_version"] = version
        return r

    return [
        row(0, ros.RESOLVED),
        row(1, ros.UNRESOLVED, "v1"),
        row(2, ros.RESOLVED, "v2"),
        row(3, ros.BROKE_EXISTING, "v1"),
        row(4, ros.NOT_SCORABLE_ORACLE_INVALID, "v1", sub_reason="GOLD_PORT_FAILED"),
        row(5, ros.NO_CANDIDATE, "v1"),
        row(6, ros.PARTIAL, "v2"),
        row(7, ros.RESOLVED, "v1"),
    ]


# sha256 of json.dumps(summarize(_golden_rows()), sort_keys=True) under scorer 1.2.4.
V124_SUMMARY_SHA256 = "0f2bd6522b7adfb49b66b4c4e252ddf05c8de740ee28cccd335a86563f03251a"


def test_v1_v2_receipts_summarize_exactly_as_1_2_4():
    s = ros.summarize(_golden_rows())
    assert "v3" not in s
    assert hashlib.sha256(json.dumps(s, sort_keys=True).encode()).hexdigest() == (
        V124_SUMMARY_SHA256
    )


def test_summary_v3_block_is_apart_from_v1_headline():
    rows = _golden_rows()
    before = ros.summarize(rows)
    v3_rows = [
        _summary_row(10, ros.BROKE_EXISTING, "v3"),
        _summary_row(11, ros.RESOLVED, "v3"),
        _summary_row(12, ros.NOT_SCORABLE_ORACLE_INVALID, "v3", sub_reason="GOLD_PORT_FAILED"),
    ]
    after = ros.summarize([*rows, *v3_rows])
    for key in set(before) - {"spec_version_counts"}:
        assert after[key] == before[key], key
    assert after["spec_version_counts"] == {"v1": 6, "v2": 2, "v3": 3}
    assert after["unknown_spec_versions"] == {}
    assert after["v3"] == ros._summary(v3_rows)
    assert after["v3"]["counts"] == {
        ros.BROKE_EXISTING: 1,
        ros.NOT_SCORABLE_ORACLE_INVALID: 1,
        ros.RESOLVED: 1,
    }
    assert (after["v3"]["resolved"], after["v3"]["valid_oracle_n"]) == (1, 2)


def test_cli_spec_version_defaults_to_v1():
    from nexus.research import score_real_outcome_cli as cli

    assert cli.parse_args(["--out", "o"]).spec_version == ros.SPEC_V1
    assert cli.parse_args(["--out", "o", "--spec-version", "v3"]).spec_version == ros.SPEC_V3
    with pytest.raises(SystemExit):
        cli.parse_args(["--out", "o", "--spec-version", "v2"])


def test_spec_v3_file_names_base_specs_and_is_post_hoc():
    root = Path(__file__).resolve().parents[2]
    v3 = (root / ros.SPEC_V3_RELATIVE_PATH).read_text()
    v2_sha = hashlib.sha256((root / ros.SPEC_V2_RELATIVE_PATH).read_bytes()).hexdigest()
    assert "315d95de21ea7ec82c97bf80165feaa052cb8a36fe99f3a1072d45ff74bb2bda" in v3
    assert v2_sha in v3
    assert "not pre-registered" in v3 and "#2709" in v3
    assert "uv-venv-runtime-pins" in v3


# Amendment A11 (#2751): allocated-size caps, run-dir role attribution, store required,
# interpreter-prefix refusal, version parse limit.


def test_tree_bytes_counts_allocated_blocks_of_a_sparse_file(tmp_path):
    sparse = tmp_path / "d" / "sparse.bin"
    sparse.parent.mkdir()
    with open(sparse, "wb") as handle:
        handle.seek(4 * 1024**3)  # 4 GiB apparent size, almost nothing allocated
        handle.write(b"x")
    st = os.lstat(sparse)
    assert st.st_size == 4 * 1024**3 + 1
    assert ros.tree_bytes(tmp_path / "d") == st.st_blocks * 512 < 1024**2
    dense = tmp_path / "e" / "dense.bin"
    dense.parent.mkdir()
    dense.write_bytes(b"y" * 100_000)
    assert ros.tree_bytes(tmp_path / "e") >= 100_000  # a normal file counts at least its size


def test_allocated_bytes_falls_back_to_st_size_without_st_blocks():
    import types

    assert ros.allocated_bytes(types.SimpleNamespace(st_size=123)) == 123  # type: ignore[arg-type]


def _survivor_script(nbytes: int, log: Path | None = None) -> str:
    """A session-escaping child that keeps re-creating its (deleted) run dir and filling
    ``grow`` there until it is killed; no fixed sleep, so the test does not race the
    runner's cleanup. ``log`` (in its tree) records each attempt: ok or denied."""
    record = ""
    if log is not None:
        record = (
            f'; if [ -s "$TMPDIR/grow" ]; then echo ok >> "{log}"; else echo denied >> "{log}"; fi'
        )
    return (
        # cd /: the survivor holds nothing under the scoring's paths (not reapable), so
        # these tests exercise the path confinement on its own.
        'cd /; while :; do mkdir -p "$TMPDIR" 2>/dev/null; '
        f'[ -s "$TMPDIR/grow" ] || head -c {nbytes} /dev/urandom > "$TMPDIR/grow" 2>/dev/null'
        f"{record}; sleep 0.1; done"
    )


def _wait_for_grow(runner: ros.PytestRunner, nbytes: int, timeout: float = 30) -> Path | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for path in runner.runs.rglob("grow") if runner.runs.exists() else ():
            with contextlib.suppress(OSError):
                if path.stat().st_size >= nbytes:
                    return path
        time.sleep(0.1)
    return None


def _survivor_tree(root: Path, script: str) -> Path:
    _write(
        root,
        {
            "tests/test_survivor.py": (
                "import subprocess\nfrom pathlib import Path\n\n\n"
                "def test_survivor():\n"
                f"    child = subprocess.Popen(['/bin/sh', '-c', {script!r}],"
                " start_new_session=True)\n"
                "    (Path(__file__).resolve().parent / 'child.pid').write_text(str(child.pid))\n"
            )
        },
    )
    return root


def _unconfined_os_runner(scratch: Path, monkeypatch) -> ros.PytestRunner:
    """The "os" code path (per-run dirs, task parents, cap attribution) without
    sandbox-exec, so the accounting is tested on every platform."""
    runner = ros.PytestRunner(scratch, timeout=300, log=lambda m: None)
    runner.sandbox = ros.SANDBOX_OS
    runner.store = scratch.parent / "_store"
    monkeypatch.setattr(runner, "_confine", lambda env, tree, run_dir: [])
    # The reaper needs lsof; record its input instead (tested on its own below).
    reaped: list[list[Path]] = []

    def record(prefixes):
        reaped.append(list(prefixes))
        return []

    monkeypatch.setattr(runner, "reap_survivors", record)
    runner.reaped_prefixes = reaped  # type: ignore[attr-defined]
    return runner


def _leftover(runner: ros.PytestRunner, name: str, nbytes: int, foreign: bool = False) -> Path:
    """A run dir as a session-escaping child re-creates it: in the current task scoring's
    parent, or (``foreign``) under another scoring's parent."""
    if foreign:
        parent = runner.runs / "0ther0task000"
    else:
        if runner.task_dir is None:
            runner.task_dir = runner.runs / "c0rrent0task"
        parent = runner.task_dir
    blob = parent / name / "tmp" / "blob"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"z" * nbytes)
    return blob


@pytest.mark.parametrize(
    ("leftover", "attributed"), [("candt-0123456789abcdef-aaaa", ros.CAND_ROLE), ("oracle-x", "")]
)
def test_task_cap_trip_is_charged_to_the_role_of_the_leftover_run_dir(
    tmp_path, monkeypatch, leftover, attributed
):
    runner = _unconfined_os_runner(tmp_path / "work" / "scratch", monkeypatch)
    tree = _leak_tree(tmp_path, 0)
    env = LocalEnv().get("fixture-repo", tree)
    _leftover(runner, leftover, 200_000)
    monkeypatch.setattr(ros, "SCRATCH_TMP_TASK_CAP_BYTES", 100_000)
    with pytest.raises(ros.ScratchTmpCapExceeded) as exc:
        runner.run(env, tree, "t", "tests", (), 0)  # a candidate-independent run
    assert exc.value.kind == ros.SCRATCH_TMP_TASK_CAP_EXCEEDED
    assert (exc.value.role, exc.value.attributed_role) == ("", attributed)
    assert runner.task_dir is not None
    assert [p.name for p in runner.task_dir.iterdir()] == [leftover]  # own run dir gone


def test_per_run_cap_trip_from_candidate_leftover_growth_is_charged_to_the_candidate(
    tmp_path, monkeypatch
):
    runner = _unconfined_os_runner(tmp_path / "work" / "scratch", monkeypatch)
    tree = tmp_path / "tree"
    _write(
        tree,
        {
            "tests/test_grow.py": (
                "import os\nfrom pathlib import Path\n\n\ndef test_grow():\n"
                "    parent = Path(os.environ['TMPDIR']).parents[1]\n"
                "    (parent / 'candt-x' / 'tmp' / 'grow').write_bytes(b'g' * 300_000)\n"
            )
        },
    )
    env = LocalEnv().get("fixture-repo", tree)
    _leftover(runner, "candt-x", 10)
    monkeypatch.setattr(ros, "SCRATCH_TMP_CAP_BYTES", 100_000)
    with pytest.raises(ros.ScratchTmpCapExceeded) as exc:
        runner.run(env, tree, "t", "tests", (), 0)
    assert exc.value.kind == ros.SCRATCH_TMP_CAP_EXCEEDED
    assert (exc.value.role, exc.value.attributed_role) == ("", ros.CAND_ROLE)


def test_none_mode_cap_attribution_is_unchanged(tmp_path, monkeypatch):
    tree = _leak_tree(tmp_path, 200_000)
    env = LocalEnv().get("fixture-repo", tree)
    runner = _runner(tmp_path)
    monkeypatch.setattr(ros, "SCRATCH_TMP_CAP_BYTES", 100_000)
    with pytest.raises(ros.ScratchTmpCapExceeded) as exc:
        runner.run(env, tree, "t", "tests", (), 0)
    assert (exc.value.role, exc.value.attributed_role) == ("", "")
    assert not runner.runs.exists()


@pytest.mark.parametrize(
    ("leftover", "label", "sub_reason"),
    [
        ("candt-x", ros.NOT_RUNNABLE, ros.SCRATCH_TMP_TASK_CAP_EXCEEDED),
        ("oracle-x", ros.NOT_SCORABLE_ORACLE_INVALID, ros.SCRATCH_TMP_TASK_CAP_EXCEEDED),
    ],
)
def test_candidate_survivor_leftover_keeps_the_task_in_the_denominator(
    tmp_path, fx, monkeypatch, leftover, label, sub_reason
):
    ctx = _ctx(tmp_path, fx)
    runner = _unconfined_os_runner(ctx.work / "scratch", monkeypatch)
    ctx.runner = runner
    # A survivor of a run of THIS scoring (same task parent): begin_task keeps it.
    _leftover(runner, leftover, 200_000)
    monkeypatch.setattr(runner, "begin_task", lambda task_key: None)
    monkeypatch.setattr(ros, "SCRATCH_TMP_TASK_CAP_BYTES", 100_000)
    receipt = ros.score_task(fx.task(b""), ctx, candidate_override="gold")["receipt"]
    assert (receipt["label"], receipt["sub_reason"]) == (label, sub_reason)
    assert receipt.get("cap_attributed_role") == (
        ros.CAND_ROLE if label == ros.NOT_RUNNABLE else None
    )
    assert not runner.runs.exists() or not list(runner.runs.iterdir())  # A6 cleanup


def test_candidate_leftover_from_an_earlier_task_is_not_charged_to_this_candidate(
    tmp_path, monkeypatch
):
    """Bytes under another task scoring's parent: neither charged nor refused (A11)."""
    runner = _unconfined_os_runner(tmp_path / "work" / "scratch", monkeypatch)
    tree = _leak_tree(tmp_path, 0)
    env = LocalEnv().get("fixture-repo", tree)
    _leftover(runner, "candt-earlier", 200_000, foreign=True)
    runner.begin_task("James3014/this#2")
    monkeypatch.setattr(ros, "SCRATCH_TMP_TASK_CAP_BYTES", 100_000)
    with pytest.raises(ros.ScratchInfraAbort, match="foreign_run_dir_leftover"):
        runner.run(env, tree, "t", "tests", (), 0)
    assert list(runner.cache.iterdir()) == []


def test_real_candidate_survivor_growth_is_charged_to_the_candidate(tmp_path, monkeypatch):
    """A candidate-role run's session-escaping child re-creates its deleted run dir and
    writes there; the next candidate-independent run's task-cap trip is the candidate's."""
    runner = _unconfined_os_runner(tmp_path / "work" / "scratch", monkeypatch)
    cand = _survivor_tree(tmp_path / "cand", _survivor_script(300_000))
    base = _leak_tree(tmp_path, 0)
    env = LocalEnv().get("fixture-repo", cand)
    assert runner.run(env, cand, "c", "tests", (), 0, ros.CAND_ROLE).outcomes
    pid = int((cand / "tests" / "child.pid").read_text())
    try:
        grown = _wait_for_grow(runner, 300_000)
        assert grown is not None and grown.parents[1].name.startswith("candt-")
        monkeypatch.setattr(ros, "SCRATCH_TMP_TASK_CAP_BYTES", 100_000)
        with pytest.raises(ros.ScratchTmpCapExceeded) as exc:
            runner.run(env, base, "b", "tests", (), 0)
        assert exc.value.kind == ros.SCRATCH_TMP_TASK_CAP_EXCEEDED
        assert (exc.value.role, exc.value.attributed_role) == ("", ros.CAND_ROLE)
    finally:
        with contextlib.suppress(OSError):
            os.kill(pid, 9)


def test_rescore_of_the_same_task_gets_a_fresh_run_parent(tmp_path, monkeypatch):
    """An earlier scoring's parent is removed by clean_tmp; if anything re-appears there
    (only possible unconfined) it is foreign to the rescore: an infra abort, no label."""
    runner = _unconfined_os_runner(tmp_path / "work" / "scratch", monkeypatch)
    tree = _leak_tree(tmp_path, 0)
    env = LocalEnv().get("fixture-repo", tree)
    runner.begin_task("James3014/x#7")
    assert runner.run(env, tree, "t1", "tests", (), 0).outcomes
    first_parent = runner.task_dir
    runner.clean_tmp()
    assert runner.task_dir is None and not list(runner.runs.iterdir())
    assert first_parent is not None
    blob = first_parent / "candt-old" / "tmp" / "blob"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"z" * 200_000)
    runner.begin_task("James3014/x#7")  # the same task, scored again
    monkeypatch.setattr(ros, "SCRATCH_TMP_TASK_CAP_BYTES", 100_000)
    with pytest.raises(ros.ScratchInfraAbort, match="foreign_run_dir_leftover"):
        runner.run(env, tree, "t2", "tests", (), 0)
    assert runner.task_dir is not None and runner.task_dir.name != first_parent.name


def test_another_tasks_survivor_aborts_scoring_without_a_receipt(tmp_path, fx, monkeypatch):
    ctx = _ctx(tmp_path, fx)
    runner = _unconfined_os_runner(ctx.work / "scratch", monkeypatch)
    ctx.runner = runner
    _leftover(runner, "candt-x", 200_000, foreign=True)
    monkeypatch.setattr(ros, "SCRATCH_TMP_TASK_CAP_BYTES", 100_000)
    with pytest.raises(ros.ScratchInfraAbort):
        ros.score_task(fx.task(b""), ctx, candidate_override="gold")
    assert not list(runner.runs.iterdir())  # cleanup still ran


def test_cap_measurement_is_one_scan_so_a_survivor_cannot_shift_blame(tmp_path, monkeypatch):
    """layer1-rie F1: the total and the candidate share come from ONE walk. A survivor
    that empties its dir right after it was walked (the old window between two scans)
    still has its bytes charged to the candidate, consistently with the total."""
    runner = _unconfined_os_runner(tmp_path / "work" / "scratch", monkeypatch)
    tree = _leak_tree(tmp_path, 0)
    env = LocalEnv().get("fixture-repo", tree)
    blob = _leftover(runner, "candt-x", 200_000)
    calls: list[str] = []
    real_measure = runner.measure
    real_walk = ros._regular_files
    phase = {"after": False}

    def measure(current, *args):
        calls.append("measure")
        phase["after"] = len(calls) == 2  # the post-run measurement
        return real_measure(current, *args)

    def walk(root):
        yield from real_walk(root)
        if phase["after"] and root.name == "candt-x":
            blob.unlink()  # the survivor empties its dir just after it was counted

    monkeypatch.setattr(runner, "measure", measure)
    monkeypatch.setattr(ros, "_regular_files", walk)
    monkeypatch.setattr(ros, "SCRATCH_TMP_TASK_CAP_BYTES", 100_000)
    with pytest.raises(ros.ScratchTmpCapExceeded) as exc:
        runner.run(env, tree, "t", "tests", (), 0)
    assert calls == ["measure", "measure"]  # one walk before, one after
    assert not blob.exists()
    assert (exc.value.role, exc.value.attributed_role) == ("", ros.CAND_ROLE)


def test_hard_links_are_counted_once_and_in_favour_of_the_candidate(tmp_path, monkeypatch):
    big = tmp_path / "d" / "big.bin"
    big.parent.mkdir()
    big.write_bytes(b"h" * 100_000)
    os.link(big, tmp_path / "d" / "link.bin")
    assert ros.tree_bytes(tmp_path / "d") == os.lstat(big).st_blocks * 512  # once
    runner = _unconfined_os_runner(tmp_path / "work" / "scratch", monkeypatch)
    oracle_blob = _leftover(runner, "oracle-x", 100_000)
    cand_dir = runner.task_dir / "candt-x" / "tmp"
    cand_dir.mkdir(parents=True)
    os.link(oracle_blob, cand_dir / "linked")
    usage = runner.measure(None)
    size = os.lstat(oracle_blob).st_blocks * 512
    assert (usage.total, usage.own_candidate, usage.foreign) == (size, size, 0)


def test_sandbox_os_survivor_cannot_recreate_its_dir_after_the_task_parent_is_gone(
    tmp_path, monkeypatch
):
    """Real sandbox-exec: while the task parent exists a survivor can re-create its own
    run dir; after clean_tmp removes the parent it can create nothing under runs/, and
    the next task is unaffected. Without a barrier: the fail-closed refusal."""
    work = tmp_path / "work"
    runner = _os_runner(work / "scratch")
    if runner is None:
        return
    cand = work / "trees" / "a" / "cand"
    log = cand / "attempts.log"
    _survivor_tree(cand, _survivor_script(5000, log))
    nxt = work / "trees" / "b" / "base"
    _write(nxt, {"tests/test_next.py": "def test_next():\n    pass\n"})
    env = LocalEnv().get("fixture-repo", cand)
    runner.begin_task("James3014/a#1")
    assert runner.run(env, cand, "c", "tests", (), 0, ros.CAND_ROLE).outcomes
    pid = int((cand / "tests" / "child.pid").read_text())
    try:
        # The survivor is alive and retrying, but its parent is already gone.
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not (log.exists() and "denied" in log.read_text()):
            time.sleep(0.1)
        assert "denied" in log.read_text()
        runner.clean_tmp()
        mark = len(log.read_text().splitlines())
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if log.read_text().splitlines()[mark:].count("denied") >= 5:
                break
            time.sleep(0.1)
        assert log.read_text().splitlines()[mark:].count("denied") >= 5
        assert "ok" not in log.read_text().splitlines()[mark:]
        assert list(runner.runs.iterdir()) == []  # nothing re-created under runs/
        runner.begin_task("James3014/b#2")
        monkeypatch.setattr(ros, "SCRATCH_TMP_TASK_CAP_BYTES", 1000)
        res = runner.run(env, nxt, "n", "tests", (), 0)
        assert res.outcomes == {"tests.test_next::test_next": ros.PASS}
    finally:
        with contextlib.suppress(OSError):
            os.kill(pid, 9)


@pytest.mark.parametrize("store", [None, "", "missing"])
def test_sandbox_os_requires_an_existing_store(tmp_path, store):
    arg = tmp_path / "missing" if store == "missing" else store
    with pytest.raises(sandboxed_lane.SandboxError, match="store_required"):
        ros.PytestRunner(tmp_path / "scratch", sandbox=ros.SANDBOX_OS, store=arg)
    assert not (tmp_path / "scratch").exists()


def test_sandbox_os_confine_refuses_a_runner_without_store(tmp_path, monkeypatch):
    runner = ros.PytestRunner(tmp_path / "work" / "scratch", log=lambda m: None)
    runner.sandbox = ros.SANDBOX_OS  # bypasses the constructor check
    monkeypatch.setattr(sandboxed_lane, "os_sandbox_available", lambda: True)
    tree = tmp_path / "work" / "trees" / "t" / "cand"
    tree.mkdir(parents=True)
    with pytest.raises(sandboxed_lane.SandboxError, match="store_required"):
        runner._confine(ros.TestEnv("e", sys.executable, "fixture"), tree, tmp_path / "r")


@pytest.mark.parametrize("where", ["inside_trees", "covers_work"])
def test_sandbox_os_refuses_an_overbroad_interpreter_prefix(tmp_path, monkeypatch, where):
    """The env dir is fine; only the interpreter it resolves to is overbroad."""
    work = tmp_path / "w" / "work"
    tree = work / "trees" / "task" / "cand"
    _write(tree, {"tests/test_a.py": "def test_a():\n    pass\n"})
    real = {
        "inside_trees": work / "trees" / "task" / "gold" / "pfx" / "bin" / "python3",
        "covers_work": tmp_path / "w" / "bin" / "python3",  # prefix tmp/w contains work
    }[where]
    real.parent.mkdir(parents=True, exist_ok=True)
    real.write_text("")  # never executed: refused before Popen
    venv_python = tmp_path / "venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.symlink_to(real)
    runner = ros.PytestRunner(work / "scratch", log=lambda m: None, store=tmp_path / "store")
    runner.sandbox = ros.SANDBOX_OS
    monkeypatch.setattr(sandboxed_lane, "os_sandbox_available", lambda: True)

    def no_popen(*a, **k):
        raise AssertionError("ran with an overbroad interpreter prefix")

    monkeypatch.setattr(ros.subprocess, "Popen", no_popen)
    env = ros.TestEnv("e", str(venv_python), "fixture")
    with pytest.raises(sandboxed_lane.SandboxError) as exc:
        runner.run(env, tree, "t", "tests", (), 0)
    assert str(exc.value) == f"read_root_overbroad:{real.resolve().parent.parent}"
    assert list(runner.runs.iterdir()) == [] and list(runner.cache.iterdir()) == []


def test_valid_version_rejects_a_version_over_the_int_digit_limit(tmp_path):
    huge = "1" * 5000
    assert not ros._valid_version(huge)
    base = tmp_path / "base"
    base.mkdir()
    (base / "pyproject.toml").write_text(f'[project]\nname = "demo"\nversion = "{huge}"\n')
    site = tmp_path / "site"
    site.mkdir()
    assert ros.write_project_metadata_stub(base, site) == (None, "version_invalid")


@pytest.fixture(autouse=True)
def _plenty_of_scratch_disk(monkeypatch):
    """A11: "os" runs check host free disk; tests see a roomy disk unless they say not."""
    import collections

    usage = collections.namedtuple("usage", "total used free")
    monkeypatch.setattr(ros, "_disk_usage", lambda path: usage(10 * 1024**4, 0, 9 * 1024**4))


def _fake_disk(monkeypatch, *, total: int, free: int) -> None:
    import collections

    usage = collections.namedtuple("usage", "total used free")
    monkeypatch.setattr(ros, "_disk_usage", lambda path: usage(total, total - free, free))


@pytest.mark.parametrize(
    ("total", "free", "floor", "aborts"),
    [
        (1000 * 1024**3, 30 * 1024**3, None, True),  # under the default 40 GiB floor
        (1000 * 1024**3, 41 * 1024**3, None, False),  # 4.1 % free is fine: no percentage
        (1000 * 1024**3, 30 * 1024**3, 20 * 1024**3, False),  # a lower floor (CLI flag)
        (1000 * 1024**3, 100 * 1024**3, 200 * 1024**3, True),  # a higher floor
    ],
)
def test_sandbox_os_host_disk_check_before_every_run(
    tmp_path, monkeypatch, total, free, floor, aborts
):
    runner = _unconfined_os_runner(tmp_path / "work" / "scratch", monkeypatch)
    assert runner.min_free_disk_bytes == ros.SCRATCH_MIN_FREE_BYTES == 40 * 1024**3
    if floor is not None:
        runner.min_free_disk_bytes = floor
    tree = _leak_tree(tmp_path, 0)
    env = LocalEnv().get("fixture-repo", tree)
    _fake_disk(monkeypatch, total=total, free=free)
    if not aborts:
        assert runner.run(env, tree, "t", "tests", (), 0).outcomes
        return

    def no_popen(*a, **k):
        raise AssertionError("ran on a full disk")

    monkeypatch.setattr(ros.subprocess, "Popen", no_popen)
    with pytest.raises(ros.ScratchInfraAbort, match="host_disk_low"):
        runner.run(env, tree, "t", "tests", (), 0)
    assert list(runner.cache.iterdir()) == []
    assert not runner.runs.exists() or list(runner.runs.iterdir()) == []


def test_none_mode_does_not_check_host_disk(tmp_path, monkeypatch):
    _fake_disk(monkeypatch, total=1000, free=1)
    tree = _leak_tree(tmp_path, 0)
    env = LocalEnv().get("fixture-repo", tree)
    assert _runner(tmp_path).run(env, tree, "t", "tests", (), 0).outcomes


def test_cli_infra_abort_exits_8_without_a_receipt(tmp_path, monkeypatch):
    from nexus.research import score_real_outcome_cli as cli

    def abort(*a, **k):
        raise ros.ScratchInfraAbort("host_disk_low:test")

    monkeypatch.setattr(cli.ros, "score_task", abort)
    monkeypatch.setattr(cli, "wait_for_memory", lambda *a, **k: 0.0)
    store = tmp_path / "store"
    (store / "tasks" / "James3014__nexus-runtime--1").mkdir(parents=True)
    out = tmp_path / "out"
    rc = cli.main([
        "--store",
        str(store),
        "--out",
        str(out),
        "--work",
        str(tmp_path / "work"),
        "--task",
        "James3014__nexus-runtime--1",
    ])
    assert rc == ros.INFRA_ABORT_EXIT_CODE == 8
    assert not list(out.rglob("real_outcome.json"))


def test_cli_min_free_disk_gib_flag_sets_the_runner_floor(tmp_path, monkeypatch):
    from nexus.research import score_real_outcome_cli as cli

    assert cli.parse_args(["--out", "o"]).min_free_disk_gib == 40
    assert cli.parse_args(["--out", "o"]).min_free_percent == 20  # memory only, unchanged
    seen: dict[str, int] = {}

    def capture(task_dir, ctx, candidate_override=None):
        seen["floor"] = ctx.runner.min_free_disk_bytes
        raise ros.ScratchInfraAbort("stop")

    monkeypatch.setattr(cli.ros, "score_task", capture)
    monkeypatch.setattr(cli, "wait_for_memory", lambda *a, **k: 0.0)
    store = tmp_path / "store"
    (store / "tasks" / "James3014__nexus-runtime--1").mkdir(parents=True)
    rc = cli.main([
        "--store",
        str(store),
        "--out",
        str(tmp_path / "out"),
        "--work",
        str(tmp_path / "work"),
        "--task",
        "James3014__nexus-runtime--1",
        "--min-free-disk-gib",
        "12.5",
    ])
    assert rc == ros.INFRA_ABORT_EXIT_CODE
    assert seen["floor"] == int(12.5 * 1024**3)


def _usage(free: int):
    import collections

    return collections.namedtuple("usage", "total used free")(10 * 1024**4, 0, free)


def test_disk_filling_during_a_gold_run_is_an_infra_abort_not_a_receipt(tmp_path, fx, monkeypatch):
    """Codex r2 P1: the host-disk check also runs right after every "os" run, before
    its result is read or cached, so a GOLD run that failed because the disk filled up
    mid-run never becomes a candidate-independent refusal receipt."""
    ctx = _ctx(tmp_path, fx)
    runner = _unconfined_os_runner(ctx.work / "scratch", monkeypatch)
    ctx.runner = runner
    state = {"tree": "", "calls": 0, "ok_runs": 0, "gold_runs": 0}
    real_execute = runner._execute

    def execute(env, tree, *args, **kwargs):
        state["tree"], state["calls"] = Path(tree).name, 0
        if state["tree"] == "gold":
            state["gold_runs"] += 1
        result = real_execute(env, tree, *args, **kwargs)
        state["ok_runs"] += 1
        return result

    def disk_usage(path):
        if state["tree"] == "gold":
            state["calls"] += 1
            if state["calls"] == 2:  # the after-check of the GOLD run only
                return _usage(1)
        return _usage(9 * 1024**4)

    monkeypatch.setattr(runner, "_execute", execute)
    monkeypatch.setattr(ros, "_disk_usage", disk_usage)
    with pytest.raises(ros.ScratchInfraAbort, match="host_disk_low"):
        ros.score_task(fx.task(b""), ctx, candidate_override="gold")
    assert state["gold_runs"] == 1
    assert len(list(runner.cache.iterdir())) == state["ok_runs"]  # GOLD run not cached


def test_env_build_failure_on_a_full_disk_is_an_infra_abort(tmp_path, fx, monkeypatch):
    ctx = _ctx(tmp_path, fx)
    runner = _unconfined_os_runner(ctx.work / "scratch", monkeypatch)
    ctx.runner = runner

    class FailingEnv:
        def get(self, repo, base_wt):
            raise ros.EnvBuildError("No space left on device")

    ctx.env_provider = FailingEnv()
    monkeypatch.setattr(ros, "_disk_usage", lambda path: _usage(1))
    with pytest.raises(ros.ScratchInfraAbort, match="host_disk_low"):
        ros.score_task(fx.task(b""), ctx, candidate_override="gold")
    # With room on the disk the same failure is the ordinary ENV_FAILED refusal.
    monkeypatch.setattr(ros, "_disk_usage", lambda path: _usage(9 * 1024**4))
    receipt = ros.score_task(fx.task(b""), ctx, candidate_override="gold")["receipt"]
    assert (receipt["label"], receipt["sub_reason"]) == (
        ros.NOT_SCORABLE_ORACLE_INVALID,
        "ENV_FAILED",
    )


def test_a_candidate_run_tripping_a_cap_only_by_foreign_bytes_is_an_infra_abort(
    tmp_path, monkeypatch
):
    """Codex r2 P2: the foreign check applies to every role, the candidate's too."""
    runner = _unconfined_os_runner(tmp_path / "work" / "scratch", monkeypatch)
    tree = _leak_tree(tmp_path, 0)
    env = LocalEnv().get("fixture-repo", tree)
    _leftover(runner, "candt-x", 200_000, foreign=True)
    monkeypatch.setattr(ros, "SCRATCH_TMP_TASK_CAP_BYTES", 100_000)
    with pytest.raises(ros.ScratchInfraAbort, match="foreign_run_dir_leftover"):
        runner.run(env, tree, "t", "tests", (), 0, ros.CAND_ROLE)
    assert list(runner.cache.iterdir()) == []


def test_a_candidate_runs_own_growth_is_still_charged_to_the_candidate(tmp_path, monkeypatch):
    runner = _unconfined_os_runner(tmp_path / "work" / "scratch", monkeypatch)
    tree = _leak_tree(tmp_path, 200_000)
    env = LocalEnv().get("fixture-repo", tree)
    monkeypatch.setattr(ros, "SCRATCH_TMP_CAP_BYTES", 100_000)
    with pytest.raises(ros.ScratchTmpCapExceeded) as exc:
        runner.run(env, tree, "t", "tests", (), 0, ros.CAND_ROLE)
    assert (exc.value.role, exc.value.attributed_role) == (ros.CAND_ROLE, ros.CAND_ROLE)


@pytest.mark.parametrize(
    ("role", "level", "own", "foreign", "expected"),
    [
        ("", 150, 0, 0, ("", False)),  # oracle growth: refusal as before
        ("", 150, 60, 0, (ros.CAND_ROLE, False)),  # needs this scoring's candidate bytes
        ("", 150, 0, 60, ("", True)),  # needs foreign bytes: infra
        ("", 150, 30, 30, ("", True)),  # needs both together: infra
        ("", 150, 60, 60, ("", True)),  # foreign alone is decisive: infra
        (ros.CAND_ROLE, 150, 0, 0, (ros.CAND_ROLE, False)),  # the candidate's own run
        (ros.CAND_ROLE, 150, 0, 60, (ros.CAND_ROLE, True)),  # ... unless foreign decides
    ],
)
def test_charge_cap_rule_table(role, level, own, foreign, expected):
    assert ros._charge_cap(role, level, 100, own=own, foreign=foreign) == expected


# A11 round 3: rename-before-delete, survivor reaper, candidate tree growth, HOST_DISK_LOW.

TIGHT_SURVIVOR_CODE = (
    "import os, sys, time, pathlib\n"
    "os.setsid()\n"
    "os.chdir('/')  # holds nothing under the scoring's paths: the reaper cannot see it\n"
    "rd = pathlib.Path(sys.argv[1]); n = 0; end = time.time() + 40\n"
    "while time.time() < end:\n"
    "    try:\n"
    "        rd.mkdir(exist_ok=True)\n"
    "        (rd / 'tmp').mkdir(exist_ok=True)\n"
    "        if n % 50 == 0:\n"
    "            (rd / 'tmp' / f'g{n}').write_bytes(os.urandom(20000))\n"
    "        n += 1\n"
    "    except Exception:\n"
    "        pass\n"
)
TIGHT_SURVIVOR_TEST = (
    "import os, sys, pathlib, subprocess\n\n"
    f"CODE = {TIGHT_SURVIVOR_CODE!r}\n\n\n"
    "def test_spawn():\n"
    "    rd = pathlib.Path(os.environ['TMPDIR']).parent\n"
    "    child = subprocess.Popen([sys.executable, '-c', CODE, str(rd)],\n"
    "                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
    "    (pathlib.Path(__file__).resolve().parent / 'child.pid').write_text(str(child.pid))\n"
)


def test_sandbox_os_survivor_in_a_tight_loop_cannot_outrace_clean_tmp(tmp_path, monkeypatch):
    """Independent review A: a survivor re-creating its run dir in a tight loop keeps
    running THROUGH clean_tmp. The run parent is renamed away first (atomic), so nothing
    re-appears under runs/ and the next task is unaffected. Real sandbox-exec on macOS;
    the fail-closed refusal elsewhere."""
    work = tmp_path / "work"
    runner = _os_runner(work / "scratch")
    if runner is None:
        return
    cand = work / "trees" / "a" / "candt"
    _write(cand, {"tests/test_spawn.py": TIGHT_SURVIVOR_TEST})
    nxt = work / "trees" / "b" / "base"
    _write(nxt, {"tests/test_next.py": "def test_next():\n    pass\n"})
    env = LocalEnv().get("fixture-repo", cand)
    runner.begin_task("James3014/a#1")
    assert runner.run(env, cand, "c", "tests", (), 0, ros.CAND_ROLE).outcomes
    pid = int((cand / "tests" / "child.pid").read_text())
    try:
        os.kill(pid, 0)  # the survivor is running
        for _ in range(3):
            runner.clean_tmp()
            time.sleep(1.5)
            assert not runner.runs.exists() or list(runner.runs.iterdir()) == []
        os.kill(pid, 0)  # still running throughout, still unable to write
        runner.begin_task("James3014/b#2")
        monkeypatch.setattr(ros, "SCRATCH_TMP_CAP_BYTES", 1000)
        monkeypatch.setattr(ros, "SCRATCH_TMP_TASK_CAP_BYTES", 1000)
        res = runner.run(env, nxt, "n", "tests", (), 0)
        assert res.outcomes == {"tests.test_next::test_next": ros.PASS}
    finally:
        with contextlib.suppress(OSError):
            os.kill(pid, 9)


def test_os_scoring_renames_its_trees_parent_before_deleting_and_reaps(tmp_path, fx, monkeypatch):
    ctx = _ctx(tmp_path, fx)
    runner = _unconfined_os_runner(ctx.work / "scratch", monkeypatch)
    ctx.runner = runner
    renames: list[tuple[str, str]] = []
    real_rename = os.rename

    def spy(src, dst, *a, **k):
        renames.append((str(src), str(dst)))
        return real_rename(src, dst, *a, **k)

    monkeypatch.setattr(ros.os, "rename", spy)
    task = fx.task(b"")
    result = ros.score_task(task, ctx, candidate_override="gold")
    assert result["receipt"]["label"] == ros.RESOLVED
    trees = ctx.work / "trees"
    moved = [(s, d) for s, d in renames if Path(s).parent == trees]
    assert len(moved) == 1 and Path(moved[0][0]).name.startswith(task.name + "-")
    assert Path(moved[0][1]).name.startswith(ros.TRASH_PREFIX)
    assert list(trees.iterdir()) == []  # the trash is gone too
    worktrees = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=ctx.work / "repos" / fx.repo_name,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert str(trees) not in worktrees  # pruned
    # The reaper saw the trees parent, its trash and the run parents.
    prefixes = runner.reaped_prefixes[-1]  # the end-of-scoring reap
    assert Path(moved[0][1]) in prefixes and runner.runs in prefixes
    assert result["timing"]["reaped_pids"] == []


def test_reaper_kills_only_processes_holding_paths_under_the_prefixes(tmp_path):
    runner = ros.PytestRunner(tmp_path / "scratch", log=lambda m: None)
    inside = tmp_path / "trash" / "run"
    inside.mkdir(parents=True)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    held = inside / "held.bin"
    holder_code = (
        "import os, sys, time\n"
        "f = open(sys.argv[1], 'wb'); f.write(b'x' * 10); f.flush(); os.unlink(sys.argv[1])\n"
        "print('ready', flush=True); time.sleep(60)\n"
    )
    cwd_holder = subprocess.Popen(["/bin/sleep", "60"], cwd=inside)
    fd_holder = subprocess.Popen(
        [sys.executable, "-c", holder_code, str(held)], stdout=subprocess.PIPE, text=True
    )
    bystander = subprocess.Popen(["/bin/sleep", "60"], cwd=outside)
    try:
        assert fd_holder.stdout is not None and fd_holder.stdout.readline() == "ready\n"
        if not any(os.path.isfile(p) for p in ros.LSOF_CANDIDATES):
            with pytest.raises(ros.ScratchInfraAbort, match="lsof_unavailable"):
                runner.reap_survivors([tmp_path / "trash"])
            return
        reaped = runner.reap_survivors([tmp_path / "trash"])
        assert sorted(reaped) == sorted([cwd_holder.pid, fd_holder.pid])
        assert cwd_holder.wait(timeout=10) == -9 and fd_holder.wait(timeout=10) == -9
        assert bystander.poll() is None  # never touched
    finally:
        for proc in (cwd_holder, fd_holder, bystander):
            with contextlib.suppress(OSError):
                proc.kill()
            proc.wait()


def _tree_writer(root: Path, nbytes: int) -> Path:
    _write(
        root,
        {
            "tests/test_fill.py": (
                "from pathlib import Path\n\n\ndef test_fill():\n"
                f"    (Path(__file__).resolve().parent / 'fill.bin').write_bytes(b'f' * {nbytes})\n"
            )
        },
    )
    return root


def test_candidate_tree_growth_counts_toward_its_runs_cap(tmp_path, monkeypatch):
    runner = _unconfined_os_runner(tmp_path / "work" / "scratch", monkeypatch)
    cand = _tree_writer(tmp_path / "cand", 300_000)
    env = LocalEnv().get("fixture-repo", cand)
    monkeypatch.setattr(ros, "SCRATCH_TMP_CAP_BYTES", 100_000)
    with pytest.raises(ros.ScratchTmpCapExceeded) as exc:
        runner.run(env, cand, "c", "tests", (), 0, ros.CAND_ROLE)
    assert exc.value.kind == ros.SCRATCH_TMP_CAP_EXCEEDED
    assert (exc.value.role, exc.value.attributed_role) == (ros.CAND_ROLE, ros.CAND_ROLE)
    assert exc.value.left_bytes >= 300_000


def test_an_oracle_runs_tree_is_not_counted(tmp_path, monkeypatch):
    runner = _unconfined_os_runner(tmp_path / "work" / "scratch", monkeypatch)
    base = _tree_writer(tmp_path / "base", 300_000)
    env = LocalEnv().get("fixture-repo", base)
    monkeypatch.setattr(ros, "SCRATCH_TMP_CAP_BYTES", 100_000)
    assert runner.run(env, base, "b", "tests", (), 0).outcomes  # as before A11


def test_disk_low_before_any_candidate_bytes_is_infra(tmp_path, monkeypatch):
    runner = _unconfined_os_runner(tmp_path / "work" / "scratch", monkeypatch)
    base = _leak_tree(tmp_path, 0)
    env = LocalEnv().get("fixture-repo", base)
    monkeypatch.setattr(ros, "_disk_usage", lambda path: _usage(1))
    with pytest.raises(ros.ScratchInfraAbort, match="host_disk_low"):
        runner.run(env, base, "b", "tests", (), 0)


def test_per_run_cap_trip_needing_foreign_growth_is_an_infra_abort(tmp_path, monkeypatch):
    """layer1-rie LOW: the per-run cap's foreign branch (growth under another scoring's
    parent during this run) is an infra abort, not a refusal."""
    runner = _unconfined_os_runner(tmp_path / "work" / "scratch", monkeypatch)
    tree = tmp_path / "tree"
    _write(
        tree,
        {
            "tests/test_grow.py": (
                "import os\nfrom pathlib import Path\n\n\ndef test_grow():\n"
                "    runs = Path(os.environ['TMPDIR']).parents[2]\n"
                "    (runs / '0ther0task000' / 'x' / 'tmp' / 'grow').write_bytes(b'g' * 300_000)\n"
            )
        },
    )
    env = LocalEnv().get("fixture-repo", tree)
    _leftover(runner, "x", 10, foreign=True)
    monkeypatch.setattr(ros, "SCRATCH_TMP_CAP_BYTES", 100_000)
    with pytest.raises(ros.ScratchInfraAbort, match="foreign_run_dir_leftover:SCRATCH_TMP_CAP"):
        runner.run(env, tree, "t", "tests", (), 0)
    assert list(runner.cache.iterdir()) == []


def _disk_by_phase(monkeypatch, runner: ros.PytestRunner, before: int, after: int) -> dict:
    """Host free bytes: ``before`` until the first candidate run has finished, ``after``
    from then on (another process may take disk in between)."""
    state = {"cand_done": 0}
    real_execute = runner._execute

    def execute(env, tree, target, ignores, run_idx, role, *rest):
        try:
            return real_execute(env, tree, target, ignores, run_idx, role, *rest)
        finally:
            if role == ros.CAND_ROLE:
                state["cand_done"] += 1

    monkeypatch.setattr(runner, "_execute", execute)
    monkeypatch.setattr(
        ros, "_disk_usage", lambda path: _usage(after if state["cand_done"] else before)
    )
    return state


@pytest.mark.parametrize(
    ("headroom", "charged"),
    [(100_000, True), (1024**3, False)],  # its 300 kB used up the headroom / they did not
)
def test_host_disk_low_after_a_candidate_filled_its_tree(tmp_path, monkeypatch, headroom, charged):
    """A11 rule: free_start (first candidate run) is above the floor; the candidate then
    writes 300 kB into its tree and the disk ends 200 kB below the floor. Charged
    (HOST_DISK_LOW, NOT_RUNNABLE) iff the candidate's bytes (visible + reclaimed by the
    reap) cover the whole headroom it started with; else infra abort."""
    short = 200_000
    runner = _unconfined_os_runner(tmp_path / "work" / "scratch", monkeypatch)
    cand = _tree_writer(tmp_path / "cand", 300_000)
    base = _leak_tree(tmp_path, 0)
    env = LocalEnv().get("fixture-repo", cand)
    floor = runner.min_free_disk_bytes
    _disk_by_phase(monkeypatch, runner, floor + headroom, floor - short)
    assert runner.run(env, cand, "c", "tests", (), 0, ros.CAND_ROLE).outcomes is not None
    assert runner.free_start == floor + headroom
    if charged:
        with pytest.raises(ros.ScratchTmpCapExceeded) as exc:
            runner.run(env, base, "b", "tests", (), 0)
        assert exc.value.kind == ros.SCRATCH_HOST_DISK_LOW == "HOST_DISK_LOW"
        assert (exc.value.role, exc.value.attributed_role) == ("", ros.CAND_ROLE)
    else:
        with pytest.raises(ros.ScratchInfraAbort, match="host_disk_low"):
            runner.run(env, base, "b", "tests", (), 0)


def test_host_disk_low_right_after_the_candidate_run_that_filled_it(tmp_path, monkeypatch):
    runner = _unconfined_os_runner(tmp_path / "work" / "scratch", monkeypatch)
    cand = _tree_writer(tmp_path / "cand", 300_000)
    env = LocalEnv().get("fixture-repo", cand)
    floor = runner.min_free_disk_bytes
    calls = {"n": 0}

    def disk(path):  # pre-run check: 100 kB headroom; post-run check: 200 kB short
        calls["n"] += 1
        return _usage(floor + 100_000 if calls["n"] == 1 else floor - 200_000)

    monkeypatch.setattr(ros, "_disk_usage", disk)
    with pytest.raises(ros.ScratchTmpCapExceeded) as exc:
        runner.run(env, cand, "c", "tests", (), 0, ros.CAND_ROLE)
    assert (exc.value.kind, exc.value.attributed_role) == (
        ros.SCRATCH_HOST_DISK_LOW,
        ros.CAND_ROLE,
    )
    assert list(runner.cache.iterdir()) == []


def test_another_process_taking_disk_between_candidate_runs_is_infra(tmp_path, monkeypatch):
    """layer1-rie R2: 1 GiB headroom at free_start; another process takes nearly all of
    it between candidate runs; the honest candidate's 300 kB tip the disk 200 kB below
    the floor. They do not account for the 1 GiB headroom: infra abort, not charged."""
    runner = _unconfined_os_runner(tmp_path / "work" / "scratch", monkeypatch)
    cand = _tree_writer(tmp_path / "cand", 300_000)
    env = LocalEnv().get("fixture-repo", cand)
    floor = runner.min_free_disk_bytes
    _disk_by_phase(monkeypatch, runner, floor + 1024**3, floor - 200_000)
    assert runner.run(env, cand, "c1", "tests", (), 0, ros.CAND_ROLE).outcomes is not None
    with pytest.raises(ros.ScratchInfraAbort, match="host_disk_low"):
        runner.run(env, cand, "c2", "tests", (), 0, ros.CAND_ROLE)
    assert len(list(runner.cache.iterdir())) == 1


def test_host_disk_low_charged_to_the_candidate_is_a_not_runnable_receipt(
    tmp_path, fx, monkeypatch
):
    ctx = _ctx(tmp_path, fx)
    runner = _unconfined_os_runner(ctx.work / "scratch", monkeypatch)
    ctx.runner = runner
    floor = runner.min_free_disk_bytes
    _disk_by_phase(monkeypatch, runner, floor + 10, floor - 1)
    monkeypatch.setattr(runner, "_candidate_bytes", lambda current: 10**6)
    receipt = ros.score_task(fx.task(b""), ctx, candidate_override="gold")["receipt"]
    assert (receipt["label"], receipt["sub_reason"]) == (
        ros.NOT_RUNNABLE,
        ros.SCRATCH_HOST_DISK_LOW,
    )


def test_candidate_runs_reap_their_survivors_before_the_post_run_disk_check(tmp_path, monkeypatch):
    """layer1-rie R1: a candidate's setsid child holds an unlinked file in its run dir;
    while it lives the disk reads below the floor. At the post-run shortfall the
    candidate scope is reaped, free space recovers, and the candidate is charged
    (HOST_DISK_LOW). Real sandbox-exec on macOS; elsewhere the fail-closed refusal."""
    work = tmp_path / "work"
    runner = _os_runner(work / "scratch")
    if runner is None:
        return
    cand = work / "trees" / "a" / "candt"
    holder = (
        "import os, sys, time\n"
        "os.setsid()\n"
        "p = os.path.join(os.environ['TMPDIR'], 'held.bin')\n"
        "f = open(p, 'wb'); f.write(b'x' * 100000); f.flush(); os.unlink(p)\n"
        "time.sleep(60)\n"
    )
    pidfile = cand / "holder.pid"
    _write(
        cand,
        {
            "tests/test_hold.py": (
                "import subprocess, sys, time\nfrom pathlib import Path\n\n\n"
                "def test_hold():\n"
                f"    child = subprocess.Popen([sys.executable, '-c', {holder!r}],"
                " stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
                f"    Path({str(pidfile)!r}).write_text(str(child.pid))\n"
                "    time.sleep(1)\n"
            )
        },
    )
    floor = runner.min_free_disk_bytes

    def holder_alive() -> bool:
        if not pidfile.exists():
            return False
        try:
            os.kill(int(pidfile.read_text()), 0)
        except (ProcessLookupError, ValueError):
            return False
        return True

    monkeypatch.setattr(
        ros, "_disk_usage", lambda path: _usage(floor - 1 if holder_alive() else 9 * 1024**4)
    )
    env = LocalEnv().get("fixture-repo", cand)
    runner.begin_task("James3014/a#1")
    try:
        with pytest.raises(ros.ScratchTmpCapExceeded) as exc:
            runner.run(env, cand, "c", "tests", (), 0, ros.CAND_ROLE)
        assert (exc.value.kind, exc.value.attributed_role) == (
            ros.SCRATCH_HOST_DISK_LOW,
            ros.CAND_ROLE,
        )
        pid = int(pidfile.read_text())
        assert runner.reaped_pids == [pid] and not holder_alive()
    finally:
        if pidfile.exists():
            with contextlib.suppress(OSError, ValueError):
                os.kill(int(pidfile.read_text()), 9)


def test_reaper_fails_closed_when_a_process_survives_sigkill(tmp_path, monkeypatch):
    runner = ros.PytestRunner(tmp_path / "scratch", log=lambda m: None)
    inside = tmp_path / "trash"
    inside.mkdir()
    holder = subprocess.Popen(["/bin/sleep", "60"], cwd=inside)
    try:
        if not any(os.path.isfile(p) for p in ros.LSOF_CANDIDATES):
            with pytest.raises(ros.ScratchInfraAbort, match="lsof_unavailable"):
                runner.reap_survivors([inside])
            return
        monkeypatch.setattr(ros, "_pid_alive", lambda pid: True)  # "survives" SIGKILL
        monkeypatch.setattr(ros, "REAP_WAIT_SECONDS", 0.2)
        with pytest.raises(ros.ScratchInfraAbort, match="reap_failed"):
            runner.reap_survivors([inside])
    finally:
        with contextlib.suppress(OSError):
            holder.kill()
        holder.wait()


def _late_holder_tree(root: Path, ready: Path, *, hold_space: bool) -> Path:
    """A candidate test whose setsid child holds NOTHING when the run ends (cwd /, no
    fds). After 1 s it either opens a file in the candidate tree, writes 100 kB, unlinks
    it and keeps it open (``hold_space``), or just chdirs into the tree and idles (a
    harmless daemon). It then touches ``ready``."""
    if hold_space:
        act = (
            "f = open(os.path.join(tree, 'late.bin'), 'wb'); f.write(b'x' * 100000);"
            " f.flush(); os.unlink(os.path.join(tree, 'late.bin'))\n"
        )
    else:
        act = "os.chdir(tree)\n"
    child = (
        "import os, sys, time\n"
        "os.setsid(); os.chdir('/')\n"
        "for fd in range(3, 256):\n"
        "    try:\n"
        "        os.close(fd)\n"
        "    except OSError:\n"
        "        pass\n"
        "tree = sys.argv[1]; time.sleep(1)\n" + act + "open(sys.argv[2], 'w').close()\n"
        "time.sleep(60)\n"
    )
    _write(
        root,
        {
            "tests/test_late.py": (
                "import subprocess, sys\nfrom pathlib import Path\n\n\n"
                "def test_late():\n"
                "    tree = str(Path(__file__).resolve().parents[1])\n"
                f"    child = subprocess.Popen([sys.executable, '-c', {child!r}, tree, {str(ready)!r}],"
                " stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,"
                " stderr=subprocess.DEVNULL, close_fds=True)\n"
                f"    Path({str(ready)!r} + '.pid').write_text(str(child.pid))\n"
            )
        },
    )
    return root


def _late_holder_scenario(tmp_path, monkeypatch, *, hold_space: bool):
    """Shared driver for the R1b / harmless-daemon tests (real sandbox-exec on macOS;
    returns None after asserting the fail-closed refusal elsewhere)."""
    work = tmp_path / "work"
    runner = _os_runner(work / "scratch")
    if runner is None:
        return None
    cand = work / "trees" / "a" / "candt"
    ready = cand / "late.ready"
    _late_holder_tree(cand, ready, hold_space=hold_space)
    base = work / "trees" / "a" / "baset"
    _write(base, {"tests/test_b.py": "def test_b():\n    pass\n"})
    pidfile = Path(str(ready) + ".pid")
    floor = runner.min_free_disk_bytes

    def holder_alive() -> bool:
        try:
            os.kill(int(pidfile.read_text()), 0)
        except (OSError, ValueError):
            return False
        return True

    external = {"taken": False}

    def disk(path):
        if hold_space and ready.exists() and holder_alive():
            return _usage(floor - 1)  # the held unlinked file filled the disk
        if external["taken"]:
            return _usage(floor - 10 * 1024**2)  # another process took 10 MiB
        return _usage(9 * 1024**4)

    monkeypatch.setattr(ros, "_disk_usage", disk)
    env = LocalEnv().get("fixture-repo", cand)
    runner.begin_task("James3014/a#1")
    assert runner.run(env, cand, "c", "tests", (), 0, ros.CAND_ROLE).outcomes
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and not ready.exists():
        time.sleep(0.1)
    assert ready.exists() and holder_alive()
    return runner, env, base, pidfile, holder_alive, external


def test_r1b_late_holder_is_reaped_at_the_shortfall_and_charged(tmp_path, monkeypatch):
    """layer1-rie R1b: the survivor holds nothing when the candidate run ends, then opens
    a deleted file in the candidate tree and fills the disk. The next run's shortfall
    reaps the candidate scope, free space recovers, and the candidate is charged."""
    got = _late_holder_scenario(tmp_path, monkeypatch, hold_space=True)
    if got is None:
        return
    runner, env, base, pidfile, holder_alive, _external = got
    try:
        with pytest.raises(ros.ScratchTmpCapExceeded) as exc:
            runner.run(env, base, "b", "tests", (), 0)
        assert (exc.value.kind, exc.value.role, exc.value.attributed_role) == (
            ros.SCRATCH_HOST_DISK_LOW,
            "",
            ros.CAND_ROLE,
        )
        assert runner.reaped_pids == [int(pidfile.read_text())] and not holder_alive()
    finally:
        with contextlib.suppress(OSError, ValueError):
            os.kill(int(pidfile.read_text()), 9)


def test_harmless_daemon_plus_external_disk_use_is_infra_not_charged(tmp_path, monkeypatch):
    """layer1-rie / Gemini: an honest candidate leaves a daemon that holds no space; an
    external process takes the disk. The reap kills the daemon but frees nothing, the
    candidate's visible bytes do not explain the shortfall: infra abort, no charge."""
    got = _late_holder_scenario(tmp_path, monkeypatch, hold_space=False)
    if got is None:
        return
    runner, env, base, pidfile, holder_alive, external = got
    try:
        external["taken"] = True
        with pytest.raises(ros.ScratchInfraAbort, match="host_disk_low"):
            runner.run(env, base, "b", "tests", (), 0)
        assert runner.reaped_pids == [int(pidfile.read_text())] and not holder_alive()
    finally:
        with contextlib.suppress(OSError, ValueError):
            os.kill(int(pidfile.read_text()), 9)


def test_a_shortfall_before_any_candidate_run_is_infra_without_reaping(tmp_path, monkeypatch):
    runner = _unconfined_os_runner(tmp_path / "work" / "scratch", monkeypatch)
    base = _leak_tree(tmp_path, 0)
    env = LocalEnv().get("fixture-repo", base)
    monkeypatch.setattr(ros, "_disk_usage", lambda path: _usage(1))
    with pytest.raises(ros.ScratchInfraAbort, match="no candidate run yet"):
        runner.run(env, base, "b", "tests", (), 0)
    assert runner.reaped_prefixes == []
