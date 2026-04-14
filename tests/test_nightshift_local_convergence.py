import subprocess
import time
from pathlib import Path

from scripts.nightshift import AutoResearchNightShift, RoundOutcome, _cleanup_stale_swarm_locks


class FakeGateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def ask_structured(self, prompt, payload, **kwargs):
        self.calls.append(
            {
                "prompt": prompt,
                "payload": payload,
                "kwargs": kwargs,
            }
        )
        return self.responses.pop(0)


def init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "nightshift@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "NightShift Test"],
        cwd=path,
        check=True,
        capture_output=True,
    )


def test_resolve_target_file_from_path_task():
    shift = AutoResearchNightShift("scripts/test_repair_dummy.py", max_rounds=1)
    resolved = shift._resolve_target_file()
    assert resolved == "scripts/test_repair_dummy.py"


def test_run_round_generates_validated_scored_candidate(tmp_path):
    target = tmp_path / "sample.py"
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    gateway = FakeGateway(
        [
            (
                {
                    "status": "PASS",
                    "summary": "fix math bug",
                    "target_file": "sample.py",
                    "content": "def add(a, b):\n    return a + b\n",
                    "changed_regions": ["body"],
                },
                '{"output":"generation"}',
            ),
            (
                {
                    "status": "PASS",
                    "summary": "validated and improved",
                    "score": 8.5,
                    "issues": [],
                },
                '{"output":"judge"}',
            ),
        ]
    )
    shift = AutoResearchNightShift("sample.py", max_rounds=1, gateway=gateway)
    shift.resolved_target_file = "sample.py"
    shift.hub.load_program_rules = lambda _: "keep the file correct"
    shift.feynman_auditor.run_advisory_audit = lambda **_: {
        "status": "PASS",
        "warnings": [],
    }
    shift._run_tier1_validation = lambda _workpath: (True, "tier1_pass")

    outcome = shift._run_round(1, tmp_path)

    assert outcome.status == "SCORED"
    assert outcome.score == 8.5
    assert target.read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"
    assert len(gateway.calls) == 2


def test_run_stops_after_convergence_patience(tmp_path):
    init_git_repo(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "target.py"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    shift = AutoResearchNightShift(
        "target.py",
        max_rounds=6,
        convergence_patience=2,
        keep_worktree=True,
    )
    shift.project_root = tmp_path
    shift.tracelog_path = tmp_path / "tracelog.jsonl"
    shift.optimization_curve_path = tmp_path / "optimization_curve.csv"
    shift.resolved_target_file = "target.py"
    shift.worktree_mgr.lease = lambda task_id, branch_prefix: (task_id, branch_prefix, tmp_path)
    shift._resolve_target_file = lambda: "target.py"

    outcomes = iter(
        [
            RoundOutcome(7.0, "value = 2\n", "SCORED", "improved"),
            RoundOutcome(0.0, "", "NO_CHANGE", "same file"),
            RoundOutcome(0.0, "", "NO_CHANGE", "same file"),
            RoundOutcome(9.0, "value = 3\n", "SCORED", "should not run"),
        ]
    )
    call_counter = {"count": 0}

    def fake_run_round(round_id, workpath):
        call_counter["count"] += 1
        return next(outcomes)

    records = []
    shift._run_round = fake_run_round
    shift._commit_candidate = lambda *args, **kwargs: (True, "ok")
    shift._run_tier2_validation = lambda _workpath: (True, "tier2_pass")
    shift._log_trace = lambda *args, **kwargs: records.append(args[1])

    result = shift.run()

    assert result["status"] == "COMPLETED"
    assert call_counter["count"] == 3
    assert records == ["IMPROVED", "NO_CHANGE", "NO_CHANGE", "CONVERGED"]


def test_run_round_rejects_ast_no_change(tmp_path):
    target = tmp_path / "sample.py"
    target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    gateway = FakeGateway(
        [
            (
                {
                    "status": "PASS",
                    "summary": "whitespace tidy",
                    "patch": "def add(a, b):\n    return a + b\n\n",
                },
                '{"output":"generation"}',
            ),
        ]
    )

    shift = AutoResearchNightShift("sample.py", max_rounds=1, gateway=gateway)
    shift.resolved_target_file = "sample.py"
    outcome = shift._run_round(1, tmp_path)

    assert outcome.status == "REJECTED_AST_NO_CHANGE"
    assert len(gateway.calls) == 1


def test_run_does_not_promote_when_tier2_fails(tmp_path):
    init_git_repo(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "target.py"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)

    shift = AutoResearchNightShift("target.py", max_rounds=1, convergence_patience=1, keep_worktree=True)
    shift.project_root = tmp_path
    shift.tracelog_path = tmp_path / "tracelog.jsonl"
    shift.lesson_writeback_path = tmp_path / ".nexus/reports/lesson_writeback.json"
    shift.resolved_target_file = "target.py"
    shift.worktree_mgr.lease = lambda task_id, branch_prefix: (task_id, branch_prefix, tmp_path)
    shift._resolve_target_file = lambda: "target.py"
    shift._run_round = lambda *_args, **_kwargs: RoundOutcome(9.0, "value = 2\n", "SCORED", "improved")
    shift._run_tier2_validation = lambda _workpath: (False, "pytest exploded")

    called = {"queued": False}
    shift._append_to_pending_manifest = lambda *_args, **_kwargs: called.update({"queued": True})

    result = shift.run()

    assert result["status"] == "COMPLETED"
    assert result["reason"] == "tier2_gate_rejected"
    assert called["queued"] is False
    assert shift.lesson_writeback_path.exists()


def test_cleanup_worktree_remove_called_when_not_keep(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir(parents=True, exist_ok=True)
    work = tmp_path / "worktree"
    work.mkdir(parents=True, exist_ok=True)
    shift = AutoResearchNightShift("x.py", max_rounds=1, keep_worktree=False)
    shift.project_root = root

    calls = []

    class _Res:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _Res()

    monkeypatch.setattr(subprocess, "run", fake_run)
    shift._cleanup_worktree(work)
    assert calls
    assert calls[0][:4] == ["git", "worktree", "remove", "--force"]


def test_cleanup_worktree_skip_when_keep(tmp_path, monkeypatch):
    shift = AutoResearchNightShift("x.py", max_rounds=1, keep_worktree=True)
    shift.project_root = tmp_path
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        raise AssertionError("should not run")

    monkeypatch.setattr(subprocess, "run", fake_run)
    shift._cleanup_worktree(tmp_path / "other")
    assert calls == []


def test_cleanup_stale_swarm_locks(tmp_path):
    stale_dir = tmp_path / ".nexus-swarm-001"
    fresh_dir = tmp_path / ".nexus-swarm-002"
    stale_dir.mkdir(parents=True, exist_ok=True)
    fresh_dir.mkdir(parents=True, exist_ok=True)
    stale = stale_dir / ".swarm_lock"
    fresh = fresh_dir / ".swarm_lock"
    stale.write_text("x", encoding="utf-8")
    fresh.write_text("x", encoding="utf-8")
    old = time.time() - (4 * 60 * 60)
    now = time.time()
    stale.touch()
    fresh.touch()
    # set stale lock old enough for ttl=180 min; fresh stays recent
    import os
    os.utime(stale, (old, old))
    os.utime(fresh, (now, now))

    removed = _cleanup_stale_swarm_locks(tmp_path, ttl_minutes=180)

    assert removed == 1
    assert not stale.exists()
    assert fresh.exists()
