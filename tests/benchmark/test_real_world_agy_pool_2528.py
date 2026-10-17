"""#2528: the real-world bench agy arm leases a pool account and fails closed.

On the Mac mini the bench ran agy in a run HOME materialized from the default
HOME, which has no agy credentials: agy printed its login prompt and exited 1
after ~61 s, and the row was a generic error.  The agy arm now runs through the
production Agy worker adapter on the installed pool (the #2405/#2413 route):
cross-process claims, rotation on quota/auth, structured failure signals.
When nothing is leasable the row carries an explicit status and is never a
verified solve.

The pool is the in-memory fake from the #2413 tests; nothing here needs agy.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from nexus.executors import worker_registry
from nexus.executors.cli_worker import CliWorkerResult, CliWorkerStatus
from scripts.bench import real_world_task_runner as runner
from tests.nexus.executors.test_agy_worker_claim_rotation_2403 import (  # noqa: F401 (fixture)
    TOKEN,
    _envelope,
    _fake_agy,
    _hash,
    _install_pool,
    pool_env,
)

FIXED_FLAGS = "def normalize_flag(value: str) -> str:\n    return value.strip().lower()\n"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def bench_pool(pool_env, monkeypatch):  # noqa: F811 (fixture from #2413 tests)
    """pool_env plus a tmp canonical checkout and an agy binary for the bench."""
    canonical = pool_env.tmp_path / "canonical"
    canonical.mkdir()
    _git(canonical, "init", "-q")
    (canonical / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(canonical, "add", ".")
    _git(canonical, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    monkeypatch.setattr(
        "nexus.orchestrator.canonical_source_root.CANONICAL_SOURCE_ROOT", canonical.resolve()
    )
    monkeypatch.setattr(runner, "_resolve_gemini_bin", lambda: "/opt/homebrew/bin/agy")
    pool_env.canonical = canonical.resolve()
    return pool_env


def _task() -> runner.RealWorldTask:
    return runner.load_tasks("scripts/bench/real_world_tasks_v1.json")[0]


def _run(env, *, root: Path | None = None) -> dict:
    return runner.run_task(
        _task(),
        mode="with_nexus",
        root=root or (env.tmp_path / "cases"),
        timeout_sec=60,
        index=0,
        executor="gemini",
    )


def _solving_agy(env, seen: list[dict]):
    """A fake agy that answers with the bench JSON (and edits the target directly)."""

    def fake_worker(request, on_process_group=None):
        home = Path(request.env["HOME"])
        seen.append({"token": (home / TOKEN).read_text(encoding="utf-8"), "cwd": request.cwd})
        (Path(request.cwd) / "AGY_TOUCHED.txt").write_text("agy edit\n", encoding="utf-8")
        answer = {
            "files": [{"path": "app/flags.py", "content": FIXED_FLAGS}],
            "root_cause": "flag normalization misses strip/lower conversion",
            "added_regression_test": False,
        }
        stdout = json.dumps({
            "conversation_id": "c",
            "status": "SUCCESS",
            "response": json.dumps(answer),
            "num_turns": 1,
            "usage": {
                "input_tokens": 900,
                "output_tokens": 120,
                "thinking_tokens": 30,
                "total_tokens": 1050,
            },
        }).encode()
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=stdout,
            stderr=b"",
            wall_time_ms=3,
            process_group_id=None,
            timed_out=False,
            descendants_swept=True,
        )

    env.monkeypatch.setattr(worker_registry, "run_cli_worker", fake_worker)


def _no_spawn(env):
    env.monkeypatch.setattr(
        worker_registry, "run_cli_worker", lambda *a, **k: pytest.fail("must not start agy")
    )


def test_agy_arm_leases_a_pool_account_and_records_real_tokens(bench_pool):
    # The default HOME has a token that would need a login; the pool account works.
    default_cli = Path(bench_pool.tmp_path / "gateway-home") / TOKEN
    default_cli.parent.mkdir(parents=True)
    default_cli.write_text("default-home", encoding="utf-8")
    _install_pool(bench_pool, {"acc-ok": "ok"})
    seen: list[dict] = []
    _solving_agy(bench_pool, seen)

    row = _run(bench_pool)

    assert [entry["token"] for entry in seen] == ["ok"]
    assert row["agy_status"] == runner.AGY_STATUS_OK
    assert row["agy_account_alias_hash"] == _hash("acc-ok")
    assert row["total_tokens"] == 1050
    assert row["token_capture_status"] == "measured"
    assert row["written_files"] == ["app/flags.py"]
    assert row["root_cause_accurate"] is True
    assert row["verified_solve"] is True
    assert row["error"] == ""


def test_agy_arm_rotates_past_a_quota_account(bench_pool):
    _install_pool(bench_pool, {"acc-quota": "quota", "acc-ok": "ok"})
    bench_pool.monkeypatch.setenv("NEXUS_AGY_PREFERRED_ACCOUNTS", "acc-quota,acc-ok")
    seen: list[str] = []
    _fake_agy(bench_pool, seen)

    row = _run(bench_pool)

    assert seen == ["quota", "ok"]
    assert row["agy_status"] == runner.AGY_STATUS_OK
    assert row["agy_account_alias_hash"] == _hash("acc-ok")
    assert row["agy_rotation_attempts"] == 1
    # OK_STDOUT reports 12 output tokens and no total: the parts are summed.
    assert row["total_tokens"] == 12


def test_no_installed_pool_is_not_authenticated_and_never_uses_the_default_home(bench_pool):
    bench_pool.monkeypatch.setenv(
        "NEXUS_AGY_ACCOUNT_POOL_MANAGER_PATH", str(bench_pool.tmp_path / "missing-manager")
    )
    _no_spawn(bench_pool)

    row = _run(bench_pool)

    assert row["agy_status"] == runner.AGY_NOT_AUTHENTICATED
    assert row["error"].startswith("AGY_NOT_AUTHENTICATED: ")
    assert row["model_calls"] == 0
    assert row["verified_solve"] is False


def test_pool_switched_off_is_not_authenticated(bench_pool):
    _install_pool(bench_pool, {"acc-ok": "ok"})
    bench_pool.monkeypatch.setenv("NEXUS_AGY_ACCOUNT_POOL_ENABLED", "0")
    _no_spawn(bench_pool)

    row = _run(bench_pool)

    assert row["agy_status"] == runner.AGY_NOT_AUTHENTICATED
    assert row["verified_solve"] is False


def test_no_account_with_a_token_is_not_authenticated(bench_pool):
    _install_pool(bench_pool, {"t1": None, "t2": None})
    _no_spawn(bench_pool)

    row = _run(bench_pool)

    assert row["agy_status"] == runner.AGY_NOT_AUTHENTICATED
    assert row["agy_failure_reason"] == worker_registry.AGY_CREDENTIALS_UNAVAILABLE
    assert row["model_calls"] == 0
    assert row["verified_solve"] is False


def test_every_account_cooling_down_is_pool_exhausted_with_earliest_reset(bench_pool, monkeypatch):
    _install_pool(bench_pool, {"q1": "quota", "q2": "quota"})
    seen: list[str] = []
    _fake_agy(bench_pool, seen)
    # Fail closed even if the fixture tests happened to pass.
    monkeypatch.setattr(runner, "_run_tests", lambda case_dir, timeout_sec: True)

    row = _run(bench_pool)

    assert seen == ["quota", "quota"]
    assert row["agy_status"] == runner.POOL_EXHAUSTED
    assert row["agy_earliest_reset"] == "1h00m00s"
    assert row["error"].startswith("POOL_EXHAUSTED: ")
    assert row["verified_solve"] is False
    assert row["semantic_verified"] is False


def test_login_prompt_is_not_authenticated(bench_pool):
    _install_pool(bench_pool, {"l1": "login", "l2": "login"})
    seen: list[str] = []
    _fake_agy(bench_pool, seen)

    row = _run(bench_pool)

    assert seen == ["login", "login"]
    assert row["agy_status"] == runner.AGY_NOT_AUTHENTICATED
    assert row["agy_failure_reason"].startswith(worker_registry.AGY_AUTHENTICATION_REQUIRED)
    assert row["verified_solve"] is False


def test_runtime_not_authorized_is_an_explicit_status(bench_pool):
    _install_pool(bench_pool, {"acc-ok": "ok"})
    bench_pool.monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    bench_pool.monkeypatch.delenv("NEXUS_AGY_RUNTIME_AUTHORIZED", raising=False)
    _no_spawn(bench_pool)

    row = _run(bench_pool)

    assert row["agy_status"] == runner.AGY_RUNTIME_NOT_AUTHORIZED
    assert row["verified_solve"] is False


def test_non_rotatable_failure_is_agy_failed_not_a_solve(bench_pool, monkeypatch):
    _install_pool(bench_pool, {"acc-crash": "crash"})
    seen: list[str] = []
    _fake_agy(bench_pool, seen)
    monkeypatch.setattr(runner, "_run_tests", lambda case_dir, timeout_sec: True)

    row = _run(bench_pool)

    assert seen == ["crash"]
    assert row["agy_status"] == runner.AGY_FAILED
    assert row["verified_solve"] is False


def test_case_dir_inside_the_canonical_checkout_runs_on_a_staged_copy(bench_pool):
    _install_pool(bench_pool, {"acc-ok": "ok"})
    seen: list[dict] = []
    _solving_agy(bench_pool, seen)
    root = bench_pool.canonical / ".nexus" / "reports" / "cases"

    row = _run(bench_pool, root=root)

    case_dir = Path(row["case_dir"])
    assert row["agy_status"] == runner.AGY_STATUS_OK
    assert not Path(seen[0]["cwd"]).is_relative_to(bench_pool.canonical)
    # agy's direct edit in the staged copy is mirrored back into the case dir.
    assert (case_dir / "AGY_TOUCHED.txt").read_text(encoding="utf-8") == "agy edit\n"
    assert (case_dir / "app" / "flags.py").read_text(encoding="utf-8") == FIXED_FLAGS
    assert row["verified_solve"] is True


def test_result_observer_sees_the_raw_result_behind_the_receipt(bench_pool):
    _install_pool(bench_pool, {"acc-ok": "ok"})
    seen: list[str] = []
    _fake_agy(bench_pool, seen)
    observed: list[CliWorkerResult] = []
    adapter = worker_registry.AgyWorkerAdapter(
        use_installed_account_pool=True,
        canonical_root=bench_pool.canonical,
        result_observer=observed.append,
    )
    target = (bench_pool.tmp_path / "target").resolve()
    target.mkdir()
    from types import SimpleNamespace

    receipt = adapter.invoke(
        SimpleNamespace(task_id="observer", maximum_provider_calls=1),
        SimpleNamespace(target_worktree=str(target)),
        prompt="p",
        worker_role="implementation",
        timeout_seconds=60,
    )

    assert [result.stdout_sha256 for result in observed] == [receipt.stdout_sha256]
    assert observed[0].stdout == _envelope("SUCCESS", output_tokens=12)


@pytest.mark.parametrize(
    ("reason", "login", "expected"),
    [
        ("agy_credentials_unavailable", False, (runner.AGY_NOT_AUTHENTICATED, "")),
        ("agy_authentication_required", False, (runner.AGY_NOT_AUTHENTICATED, "")),
        (
            "agy_authentication_required: agy_pool_exhausted: earliest reset in 2h05m00s",
            False,
            (runner.AGY_NOT_AUTHENTICATED, "2h05m00s"),
        ),
        (
            "agy_pool_exhausted: earliest reset in 0h10m03s",
            False,
            (runner.POOL_EXHAUSTED, "0h10m03s"),
        ),
        ("agy_pool_exhausted", False, (runner.POOL_EXHAUSTED, "")),
        (
            "agy_pool_busy: after quota exhaustion on 2 account(s)",
            False,
            (runner.AGY_POOL_BUSY, ""),
        ),
        ("agy execution did not complete successfully", True, (runner.AGY_NOT_AUTHENTICATED, "")),
        ("agy execution did not complete successfully", False, (runner.AGY_FAILED, "")),
        (None, False, (runner.AGY_FAILED, "")),
    ],
)
def test_agy_bench_status_maps_worker_reasons(reason, login, expected):
    assert runner.agy_bench_status(reason, login_prompt_seen=login) == expected


# --- Codex review r1 on #2540 -------------------------------------------------


def test_required_pool_never_falls_back_to_the_process_home(bench_pool):
    # The default HOME has a usable token, but the pool vanished after the
    # bench's own check: the adapter itself must refuse.
    token = bench_pool.tmp_path / "gateway-home" / TOKEN
    token.parent.mkdir(parents=True)
    token.write_text("ok", encoding="utf-8")
    (token.parent / "installation_id").write_text("home", encoding="utf-8")
    bench_pool.monkeypatch.setenv(
        "NEXUS_AGY_ACCOUNT_POOL_MANAGER_PATH", str(bench_pool.tmp_path / "missing-manager")
    )
    _no_spawn(bench_pool)
    target = (bench_pool.tmp_path / "target").resolve()
    target.mkdir()
    from types import SimpleNamespace

    receipt = worker_registry.AgyWorkerAdapter(
        use_installed_account_pool=True,
        canonical_root=bench_pool.canonical,
        require_account_pool=True,
    ).invoke(
        SimpleNamespace(task_id="no-pool", maximum_provider_calls=1),
        SimpleNamespace(target_worktree=str(target)),
        prompt="p",
        worker_role="implementation",
        timeout_seconds=60,
    )

    assert receipt.failure_reason == worker_registry.AGY_CREDENTIALS_UNAVAILABLE
    assert receipt.provider_attempt_count == 0


def test_failed_staged_run_does_not_write_back(bench_pool):
    _install_pool(bench_pool, {"acc-crash": "crash"})

    def crashing_worker(request, on_process_group=None):
        (Path(request.cwd) / "AGY_TOUCHED.txt").write_text("partial\n", encoding="utf-8")
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=1,
            stdout=b"",
            stderr=b"segmentation fault",
            wall_time_ms=3,
            process_group_id=None,
            timed_out=False,
            descendants_swept=True,
        )

    bench_pool.monkeypatch.setattr(worker_registry, "run_cli_worker", crashing_worker)
    root = bench_pool.canonical / ".nexus" / "reports" / "cases"

    row = _run(bench_pool, root=root)

    assert row["agy_status"] == runner.AGY_FAILED
    assert not (Path(row["case_dir"]) / "AGY_TOUCHED.txt").exists()
    assert row["verified_solve"] is False


def test_sync_never_follows_a_case_dir_symlink(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("keep\n", encoding="utf-8")
    outside_dir = tmp_path / "outside-dir"
    outside_dir.mkdir()
    (outside_dir / "f.txt").write_text("keep\n", encoding="utf-8")
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "link.txt").symlink_to(outside)
    (case_dir / "linkdir").symlink_to(outside_dir, target_is_directory=True)
    staged = tmp_path / "staged"
    (staged / "linkdir").mkdir(parents=True)
    (staged / "link.txt").write_text("overwrite\n", encoding="utf-8")
    (staged / "linkdir" / "f.txt").write_text("overwrite\n", encoding="utf-8")
    (staged / "new.txt").write_text("new\n", encoding="utf-8")

    assert runner._sync_staged_case(staged, case_dir) == runner.AGY_STAGED_SYMLINK_REFUSED

    assert outside.read_text(encoding="utf-8") == "keep\n"
    assert (outside_dir / "f.txt").read_text(encoding="utf-8") == "keep\n"
    assert (case_dir / "link.txt").is_symlink()
    assert not (case_dir / "new.txt").exists()


def test_staged_symlink_cannot_hide_a_deleted_case_file(tmp_path):
    # Codex r2: agy replaces notes/user_draft.md with a symlink to another
    # staged file; the original note must not be deleted.
    case_dir = tmp_path / "case"
    (case_dir / "notes").mkdir(parents=True)
    (case_dir / "notes" / "user_draft.md").write_text("draft\n", encoding="utf-8")
    (case_dir / "app.py").write_text("x = 1\n", encoding="utf-8")
    staged = tmp_path / "staged"
    (staged / "notes").mkdir(parents=True)
    (staged / "app.py").write_text("x = 2\n", encoding="utf-8")
    (staged / "notes" / "user_draft.md").symlink_to(staged / "app.py")

    assert runner._sync_staged_case(staged, case_dir) == runner.AGY_STAGED_SYMLINK_REFUSED

    assert (case_dir / "notes" / "user_draft.md").read_text(encoding="utf-8") == "draft\n"
    assert (case_dir / "app.py").read_text(encoding="utf-8") == "x = 1\n"


def test_sync_mirrors_edits_creations_and_deletions(tmp_path):
    case_dir = tmp_path / "case"
    (case_dir / "pkg").mkdir(parents=True)
    (case_dir / "pkg" / "a.py").write_text("old\n", encoding="utf-8")
    (case_dir / "gone.py").write_text("bye\n", encoding="utf-8")
    staged = tmp_path / "staged"
    (staged / "pkg").mkdir(parents=True)
    (staged / "pkg" / "a.py").write_text("new\n", encoding="utf-8")
    (staged / "tests").mkdir()
    (staged / "tests" / "test_a.py").write_text("t\n", encoding="utf-8")

    assert runner._sync_staged_case(staged, case_dir) is None

    assert (case_dir / "pkg" / "a.py").read_text(encoding="utf-8") == "new\n"
    assert (case_dir / "tests" / "test_a.py").read_text(encoding="utf-8") == "t\n"
    assert not (case_dir / "gone.py").exists()


def test_result_observer_cannot_alter_the_receipt(bench_pool):
    _install_pool(bench_pool, {"acc-crash": "crash"})
    seen: list[str] = []
    _fake_agy(bench_pool, seen)

    def tamper(result):
        result.exit_code = 0
        result.stderr = b""

    target = (bench_pool.tmp_path / "target").resolve()
    target.mkdir()
    from types import SimpleNamespace

    receipt = worker_registry.AgyWorkerAdapter(
        use_installed_account_pool=True,
        canonical_root=bench_pool.canonical,
        result_observer=tamper,
    ).invoke(
        SimpleNamespace(task_id="tamper", maximum_provider_calls=1),
        SimpleNamespace(target_worktree=str(target)),
        prompt="p",
        worker_role="implementation",
        timeout_seconds=60,
    )

    assert receipt.exit_code == 1
    assert receipt.outcome != "EXECUTION_COMPLETED"


def test_unreadable_staged_dir_refuses_instead_of_deleting(tmp_path):
    # Codex r3: an unreadable staged directory must not make its files look deleted.
    case_dir = tmp_path / "case"
    (case_dir / "notes").mkdir(parents=True)
    (case_dir / "notes" / "user_draft.md").write_text("draft\n", encoding="utf-8")
    staged = tmp_path / "staged"
    (staged / "notes").mkdir(parents=True)
    (staged / "notes" / "user_draft.md").write_text("draft\n", encoding="utf-8")
    real_walk = runner.os.walk

    def walk(top, onerror=None, **kwargs):
        if Path(top) == staged and onerror is not None:
            onerror(PermissionError(13, "Permission denied", str(staged / "notes")))
        yield from real_walk(top, onerror=onerror, **kwargs)

    import unittest.mock

    with unittest.mock.patch.object(runner.os, "walk", walk):
        assert runner._sync_staged_case(staged, case_dir) == runner.AGY_STAGED_SYMLINK_REFUSED

    assert (case_dir / "notes" / "user_draft.md").read_text(encoding="utf-8") == "draft\n"


def test_file_dir_type_change_refuses_before_touching_the_case(tmp_path):
    # Claude review at c51abf9ed: case dir x/ with x/f, staged regular file x.
    case_dir = tmp_path / "case"
    (case_dir / "x").mkdir(parents=True)
    (case_dir / "x" / "f").write_text("keep\n", encoding="utf-8")
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "x").write_text("file\n", encoding="utf-8")

    assert runner._sync_staged_case(staged, case_dir) == runner.AGY_STAGED_SYMLINK_REFUSED
    assert (case_dir / "x" / "f").read_text(encoding="utf-8") == "keep\n"


@pytest.mark.parametrize("staged_is_file", [True, False])
def test_empty_dir_file_type_change_refuses(tmp_path, staged_is_file):
    # Codex confirmation at 10f73748e: an *empty* directory on either side.
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "keep.py").write_text("keep\n", encoding="utf-8")
    staged = tmp_path / "staged"
    staged.mkdir()
    if staged_is_file:
        (case_dir / "x").mkdir()
        (staged / "x").write_text("file\n", encoding="utf-8")
    else:
        (case_dir / "x").write_text("file\n", encoding="utf-8")
        (staged / "x").mkdir()

    assert runner._sync_staged_case(staged, case_dir) == runner.AGY_STAGED_SYMLINK_REFUSED
    assert (case_dir / "keep.py").read_text(encoding="utf-8") == "keep\n"
    assert (case_dir / "x").is_dir() is staged_is_file
