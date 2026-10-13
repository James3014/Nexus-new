"""Fixture tests and self-checks for the #1216 real-outcome scorer (spec §11)."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

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

    def __init__(self, tmp: Path, repo_name: str = "fixture-repo", gate: str | None = None):
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
        }
        if gate:
            files["scripts/ops/pr_impact_gate.py"] = gate
        _write(self.upstream, files)
        _git(self.upstream, "add", "-A")
        _git(self.upstream, "commit", "-qm", "base")
        self.base = _git(self.upstream, "rev-parse", "HEAD").strip()
        _write(self.upstream, {"README.md": "main moved\n"})
        _git(self.upstream, "commit", "-qam", "drift")
        _write(self.upstream, {"pkg/calc.py": FIXED, "tests/test_mul.py": MUL_TEST})
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
            so["untracked_files"].append(
                {
                    "path": path,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size": len(data),
                    "gzip_base64": base64.b64encode(gzip.compress(data, mtime=0)).decode(),
                }
            )
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
    def get(self, repo: str, base_wt: Path) -> ros.TestEnv:
        return ros.TestEnv("fixture-env", sys.executable, "fixture")


def _ctx(tmp: Path, fx: Fixture, work: str = "work") -> ros.ScoreContext:
    w = tmp / work
    return ros.ScoreContext(
        work=w,
        env_provider=LocalEnv(),
        runner=ros.PytestRunner(w / "scratch", timeout=300, log=lambda m: None),
        repo_sources={fx.repo_name: [str(fx.upstream)]},
        spec_sha256="0" * 64,
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
    partial = fx.diff_from_base(
        {
            "pkg/calc.py": BUGGY.replace(
                "def mul(a, b):\n    return a + b",
                "def mul(a, b):\n    return 6 if (a, b) == (2, 3) else a + b",
            )
        }
    )
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
    diff = fx.diff_from_base(
        {
            "pkg/calc.py": BUGGY.replace(
                "def mul(a, b):\n    return a + b", "from pkg.fast import mul  # noqa: F811"
            )
        }
    )
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
    script = Path(__file__).resolve().parents[2] / "scripts/research/score_real_outcome.py"
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
    diff = fx.diff_from_base(
        {"pkg/calc.py": FIXED.replace("a + b", "a - b"), "scripts/ops/pr_impact_gate.py": evil_gate}
    )
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
        for i, lab in enumerate(
            [
                ros.RESOLVED,
                ros.NO_CANDIDATE,
                ros.NOT_RUNNABLE,
                ros.NOT_SCORABLE_NO_ORACLE,
                ros.PENDING_GROUND_TRUTH,
            ]
        )
    ]
    s = ros.summarize(rows)
    assert s["valid_oracle_n"] == 3 and s["resolved"] == 1
    assert s["counts"][ros.PENDING_GROUND_TRUTH] == 1
