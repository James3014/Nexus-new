"""Fixture tests and self-checks for the #1216 real-outcome scorer (spec §11)."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import subprocess
import sys
import time
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
    assert ros.SCORER_VERSION == "1.2.1"
    amendments = (root / "docs/research/REAL_OUTCOME_SCORER_SPEC.amendments.md").read_text()
    assert f'SCORER_VERSION = "{ros.SCORER_VERSION}"' in amendments
    spec = (root / ros.SPEC_RELATIVE_PATH).read_bytes()
    # The pre-registered spec itself is frozen (spec header); amendments live beside it.
    assert hashlib.sha256(spec).hexdigest().startswith("315d95de21ea7ec8")


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
    # Review round 5, Codex 4: only v1 and v2 receipts are counted.
    rows = [_summary_row(0, ros.RESOLVED), _summary_row(1, ros.UNRESOLVED, "v1")]
    before = ros.summarize(rows)
    after = ros.summarize([
        *rows,
        _summary_row(2, ros.RESOLVED, "v3"),
        _summary_row(3, ros.RESOLVED, "v3"),
        _summary_row(4, ros.RESOLVED, ""),
    ])
    for key in ("counts", "resolved", "valid_oracle_n", "ci95"):
        assert after[key] == before[key]
        assert after["v1_plus_v2"][key] == before["v1_plus_v2"][key]
    assert after["unknown_spec_versions"] == {"": 1, "v3": 2}
    assert before["unknown_spec_versions"] == {}
    assert after["spec_version_counts"] == {"": 1, "v1": 2, "v3": 2}


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
    assert ros.tree_bytes(tmp) == 10 + 2 * len("<testsuite/>") + 7
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
    (runner.tmp / "earlier-run.bin").write_bytes(b"x" * 5000)  # left by an earlier run
    monkeypatch.setattr(ros, "SCRATCH_TMP_CAP_BYTES", 1000)
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
