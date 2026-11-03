"""Cleanup sites outside the executors that remove a tree an untrusted command wrote to
(#3281, third slice): each removes a deep tree with a locked leaf, and records (never raises,
never hides) a tree it cannot remove. Host-side only, so these run on every platform."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

_DEPTH = 1100  # deeper than the default recursion limit: plain shutil.rmtree cannot finish
_STUCK = "tree_not_removed:stuck"


def _deep_locked_tree(top: Path, depth: int = _DEPTH) -> Path:
    top.mkdir(parents=True, exist_ok=True)
    fd = os.open(top, os.O_RDONLY)
    try:
        for _ in range(depth):
            os.mkdir("d", dir_fd=fd)
            nxt = os.open("d", os.O_RDONLY, dir_fd=fd)
            os.close(fd)
            fd = nxt
        os.chmod(fd, 0)
    finally:
        os.close(fd)
    return top


def test_micro_verify_scratch_copy_removes_deep_locked_tree(tmp_path, monkeypatch):
    import nexus.services.local_heal.micro_verifier as mv

    scratch = tmp_path / "scratch"
    seen = {}

    def verify(**kwargs):
        _deep_locked_tree(Path(kwargs["repo_dir"]) / "t")
        seen["dir"] = Path(kwargs["repo_dir"])
        return mv.MicroVerifyResult(passed=True, syntax_ok=True)

    monkeypatch.setattr(
        mv, "make_isolated_workspace", lambda prefix: str(scratch.mkdir() or scratch)
    )
    monkeypatch.setattr(mv, "copy_repo_entries", lambda *_a: None)
    monkeypatch.setattr(mv.MicroVerifier, "verify", staticmethod(verify))
    result = mv.micro_verify_in_scratch_copy("", tmp_path, [])
    assert result.passed and "scratch_cleanup_failed" not in result.classifications
    assert not seen["dir"].exists()


def test_micro_verify_records_a_scratch_copy_that_cannot_be_removed(tmp_path, monkeypatch):
    import nexus.services.local_heal.micro_verifier as mv

    scratch = tmp_path / "scratch"
    monkeypatch.setattr(
        mv, "make_isolated_workspace", lambda prefix: str(scratch.mkdir() or scratch)
    )
    monkeypatch.setattr(mv, "copy_repo_entries", lambda *_a: None)
    monkeypatch.setattr(
        mv.MicroVerifier, "verify", staticmethod(lambda **_k: mv.MicroVerifyResult(passed=True))
    )
    monkeypatch.setattr(mv, "remove_untrusted_tree_quietly", lambda _p: _STUCK)
    result = mv.micro_verify_in_scratch_copy("", tmp_path, [])
    assert result.passed
    assert "scratch_cleanup_failed" in result.classifications
    assert _STUCK in result.details


def _closure_run(tmp_path, monkeypatch, *, stuck: bool):
    import nexus.services.external_intelligence_closure as closure

    root = tmp_path / "repo"
    root.mkdir()
    made = {}

    def run(argv, cwd, env, timeout):
        sandbox = Path(env["HOME"]).parent
        made["sandbox"] = sandbox
        _deep_locked_tree(sandbox / "t")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(closure, "run_reaping_process_group", run)
    if stuck:
        monkeypatch.setattr(closure, "remove_untrusted_tree_quietly", lambda _p: _STUCK)
    row = closure._run_one_verifier(
        closure.VerifierSpec(verifier_id="v1", argv=("true",), timeout=5.0),
        root=root,
        base_sha="0" * 40,
        candidate_commit="1" * 40,
        changed_paths=None,
        shadow_error="",
        refused_shadow=(),
        authorized_shadow=(),
        base_state=(None, None, ""),
    )
    return row, made["sandbox"]


def test_closure_verifier_sandbox_removes_deep_locked_tree(tmp_path, monkeypatch):
    row, sandbox = _closure_run(tmp_path, monkeypatch, stuck=False)
    assert not sandbox.exists()
    assert "cleanup_error" not in row["sandbox"]


def test_closure_verifier_records_a_sandbox_that_cannot_be_removed(tmp_path, monkeypatch):
    row, sandbox = _closure_run(tmp_path, monkeypatch, stuck=True)
    assert row["sandbox"]["cleanup_error"] == _STUCK
    os.chmod(sandbox, 0o700)


def _probe(tmp_path, *, stuck: bool, monkeypatch):
    import nexus.learning.zero_trust_v2_physical_sandbox as ztv2

    seen = {}

    def run(cmd, cwd, **_k):
        seen["root"] = Path(cwd).parent
        _deep_locked_tree(Path(cwd) / "t")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    if stuck:
        monkeypatch.setattr(ztv2, "remove_untrusted_tree_quietly", lambda _p: _STUCK)
    out = ztv2.run_macos_sandbox_probe(
        ["true"],
        signing_secret="s",
        sandbox_exec_path=None,
        subprocess_run=run,
        base_tmp_dir=tmp_path,
    )
    return out, seen["root"]


def _teardown(out) -> str:
    return out["sandbox_attestation"]["teardown_status"]


def test_ztv2_probe_root_removes_deep_locked_tree(tmp_path, monkeypatch):
    out, root = _probe(tmp_path, stuck=False, monkeypatch=monkeypatch)
    assert not root.exists()
    assert _teardown(out) == "PASS"


def test_ztv2_probe_reports_teardown_fail_when_root_cannot_be_removed(tmp_path, monkeypatch):
    out, root = _probe(tmp_path, stuck=True, monkeypatch=monkeypatch)
    assert _teardown(out) == "FAIL"
    os.chmod(root / "workspace" / "t", 0o700)


def test_ztv2_probe_teardown_fails_when_root_is_set_aside_but_an_error_is_reported(
    tmp_path, monkeypatch
):
    import nexus.learning.zero_trust_v2_physical_sandbox as ztv2

    seen = {}

    def run(cmd, cwd, **_k):
        seen["root"] = Path(cwd).parent
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def set_aside(path):  # moved away (root no longer exists) yet reported as not removed
        os.rename(path, f"{path}.stale-1")
        return _STUCK

    monkeypatch.setattr(ztv2, "remove_untrusted_tree_quietly", set_aside)
    out = ztv2.run_macos_sandbox_probe(
        ["true"],
        signing_secret="s",
        sandbox_exec_path=None,
        subprocess_run=run,
        base_tmp_dir=tmp_path,
    )
    assert not seen["root"].exists()
    assert _teardown(out) == "FAIL"
    assert out["promotion_eligible"] is False


def test_disposable_repo_copy_removes_deep_locked_tree(tmp_path):
    from nexus.services.local_heal.scratch_copy import disposable_repo_copy

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("x = 1\n")
    with disposable_repo_copy(repo, prefix="c-") as work:
        _deep_locked_tree(work / "t")
    assert not work.exists()


def test_disposable_repo_copy_logs_a_copy_that_cannot_be_removed(tmp_path, monkeypatch, caplog):
    import nexus.services.local_heal.scratch_copy as sc

    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(sc, "remove_untrusted_tree_quietly", lambda _p: _STUCK)
    with caplog.at_level("WARNING"):
        with sc.disposable_repo_copy(repo, prefix="c-") as work:
            pass
    assert _STUCK in caplog.text
    assert work.exists()


def test_candidate_scratch_cleanup_removes_deep_locked_tree(tmp_path):
    from nexus.services.post_candidate_seam import CandidateScratch

    top = _deep_locked_tree(tmp_path / "scratch")
    scratch = CandidateScratch(
        root=top, target_rel="t.py", visible_rel="v.py", candidate_sha256="", cleanup_dir=top
    )
    scratch.cleanup()
    assert not top.exists() and scratch.cleanup_error is None


def test_candidate_scratch_cleanup_records_a_tree_that_cannot_be_removed(tmp_path, monkeypatch):
    import nexus.services.post_candidate_seam as seam

    top = tmp_path / "scratch"
    top.mkdir()
    monkeypatch.setattr(seam, "remove_untrusted_tree_quietly", lambda _p: _STUCK)
    scratch = seam.CandidateScratch(
        root=top, target_rel="t.py", visible_rel="v.py", candidate_sha256="", cleanup_dir=top
    )
    scratch.cleanup()
    assert scratch.cleanup_error == _STUCK


def _swarm(tmp_path, monkeypatch):
    import nexus.engine.battle_swarm as bs

    swarm = bs.BattleSwarm(str(tmp_path), run_dir=str(tmp_path / "runs"))
    monkeypatch.setattr(bs, "repository_config_can_start_a_program", lambda _r: False)
    monkeypatch.setattr(swarm, "_git_quietly", lambda *_a: None)
    monkeypatch.setattr(
        bs, "run_hardened_git", lambda *_a: SimpleNamespace(check_returncode=lambda: None)
    )
    return bs, swarm


def test_battle_swarm_old_worktree_with_deep_locked_tree_is_removed(tmp_path, monkeypatch):
    _bs, swarm = _swarm(tmp_path, monkeypatch)
    old = _deep_locked_tree(tmp_path / "runs" / "worktree_s1")
    assert swarm._create_worktree("s1", "b1") == old
    assert not (old / "d").exists()


def test_battle_swarm_logs_an_old_worktree_that_cannot_be_removed(tmp_path, monkeypatch, caplog):
    bs, swarm = _swarm(tmp_path, monkeypatch)
    (tmp_path / "runs" / "worktree_s1").mkdir(parents=True)
    monkeypatch.setattr(bs, "remove_untrusted_tree_quietly", lambda _p: _STUCK)
    with caplog.at_level("ERROR"):
        swarm._create_worktree("s1", "b1")
    assert _STUCK in caplog.text


def _speculative(tmp_path):
    from nexus.health.sandbox import SpeculativeSandbox

    sandbox = SpeculativeSandbox(tmp_path, mode="tmpdir")
    temp_root = tmp_path / "temp-root"
    sandbox._temp_root = temp_root
    sandbox.sandbox_root = temp_root
    return sandbox, temp_root


def test_speculative_sandbox_cleanup_removes_deep_locked_tree(tmp_path):
    sandbox, temp_root = _speculative(tmp_path)
    _deep_locked_tree(temp_root)
    sandbox.cleanup()
    assert not temp_root.exists()


def test_speculative_sandbox_cleanup_logs_a_tree_that_cannot_be_removed(
    tmp_path, monkeypatch, caplog
):
    import nexus.health.sandbox as hs

    sandbox, temp_root = _speculative(tmp_path)
    temp_root.mkdir()
    monkeypatch.setattr(hs, "remove_untrusted_tree_quietly", lambda _p: _STUCK)
    with caplog.at_level("ERROR"):
        sandbox.cleanup()
    assert _STUCK in caplog.text


def _f2p(tmp_path, monkeypatch, *, stuck: bool):
    from nexus.executors.cli_worker import CliWorkerStatus
    from nexus.orchestrator import self_hosted_task_service as service_module
    from nexus.orchestrator.candidate_verifier import CandidateVerifier
    from nexus.orchestrator.self_hosted_task_service_parts import finalize_runtime as fr

    made = {}

    def run_verifiers(_contract, checkout, _x):
        made["scratch"] = Path(checkout).parent
        _deep_locked_tree(Path(checkout) / "t")
        evidence = (SimpleNamespace(status=CliWorkerStatus.COMPLETED.value, exit_code=1),)
        return False, evidence, ["verifier_failed:a"]

    monkeypatch.setattr(CandidateVerifier, "_run_verifiers", staticmethod(run_verifiers))
    monkeypatch.setattr(service_module, "_base_run_collected_nothing", lambda *_a: None)
    if stuck:
        monkeypatch.setattr(fr, "remove_untrusted_tree_quietly", lambda _p: _STUCK)

    def run_git(args, cwd=None):
        if args[:2] == ["worktree", "add"]:
            Path(args[-2]).mkdir(parents=True)
        return ""

    manager = SimpleNamespace(_run_git=run_git)
    contract = SimpleNamespace(
        target_base_revision="0" * 40,
        verifier_commands=["python -c 'raise SystemExit(1)'"],
        controller_repo_root=str(tmp_path),
    )
    probe = service_module.SelfHostedTaskService._run_fail_to_pass_probe(manager, contract)
    return probe, made["scratch"]


def test_fail_to_pass_probe_removes_deep_locked_base_checkout(tmp_path, monkeypatch):
    probe, scratch = _f2p(tmp_path, monkeypatch, stuck=False)
    assert probe["status"] == "VERIFIED"
    assert not scratch.exists()


def test_fail_to_pass_probe_records_a_checkout_that_cannot_be_removed(tmp_path, monkeypatch):
    probe, scratch = _f2p(tmp_path, monkeypatch, stuck=True)
    assert probe["status"] == "BASE_NOT_PHYSICAL_FAIL"
    assert probe["cleanup_error"] == _STUCK
    os.chmod(scratch / "base" / "t", 0o700)


def _fake_pytest_run():
    return SimpleNamespace(
        returncode=0,
        witness={"complete": True},
        sandbox={"sandboxed": True},
        skipped_names=[],
        selected_node_ids=[],
        option_arity={},
        error=None,
    )


def _base_run(tmp_path, monkeypatch, *, stuck: bool, which: str):
    import nexus.services.external_intelligence_closure as closure

    made = {}

    def fake_run(_inv, *, run_dir, **_k):
        made["run_dir"] = run_dir
        return _fake_pytest_run()

    monkeypatch.setattr(closure, "_run_pytest_verifier", fake_run)
    if stuck:
        monkeypatch.setattr(closure, "remove_untrusted_tree_quietly", lambda _p: _STUCK)
    invocation = closure._PytestInvocation(
        interpreter="python", interpreter_args=(), pytest_args=("tests",), declared_node_ids=()
    )
    common = {
        "root": tmp_path,
        "base_sha": "0" * 40,
        "base_config": {},
        "base_tree": tmp_path / "tree",
        "candidate_commit": "1" * 40,
        "timeout": 5.0,
    }
    if which == "skipped":
        _nodes, info = closure._base_skipped_nodes(invocation, **common)
    else:
        (tmp_path / "tree" / "tests").mkdir(parents=True)
        _nodes, info = closure._base_declared_nodes_missing(
            invocation, [], changed_paths=(), **common
        )
    return info, made["run_dir"]


def test_base_skipped_nodes_run_dir_is_removed_and_stuck_one_is_recorded(tmp_path, monkeypatch):
    info, run_dir = _base_run(tmp_path, monkeypatch, stuck=False, which="skipped")
    assert not run_dir.exists()
    assert "cleanup_error" not in info
    info, run_dir = _base_run(tmp_path / "b", monkeypatch, stuck=True, which="skipped")
    assert info["cleanup_error"] == _STUCK


def test_base_declared_nodes_run_dir_is_removed_and_stuck_one_is_logged(
    tmp_path, monkeypatch, caplog
):
    _info, run_dir = _base_run(tmp_path, monkeypatch, stuck=False, which="declared")
    assert not run_dir.exists()
    with caplog.at_level("WARNING"):
        _base_run(tmp_path / "b", monkeypatch, stuck=True, which="declared")
    assert _STUCK in caplog.text


def test_zt_v2_runner_marks_cleanup_attestation_fail_when_a_probe_root_stays(tmp_path, monkeypatch):
    import nexus.learning.zero_trust_v2_physical_sandbox as ztv2
    from nexus.learning.zero_trust_v2_physical_runner import run_zero_trust_v2_physical_row

    monkeypatch.setattr(ztv2, "remove_untrusted_tree_quietly", lambda _p: _STUCK)
    row = run_zero_trust_v2_physical_row(
        {"row_id": "r", "arm_type": "skill_v2"},
        command=["true"],
        signing_secret="s",
        run_id="run",
        sandbox_probe=lambda cmd, **k: ztv2.run_macos_sandbox_probe(
            cmd,
            sandbox_exec_path=None,
            subprocess_run=lambda c, **_k: subprocess.CompletedProcess(c, 0, "", ""),
            base_tmp_dir=tmp_path,
            **k,
        ),
    )
    assert row["cleanup_attestation"]["teardown_status"] == "FAIL"
    assert row["cleanup_attestation"]["runner_quarantine_status"] == "QUARANTINED"
    assert row["execution_status"] == "BLOCKED_BY_POLICY"


def test_quietly_turns_any_exception_into_text_but_not_base_exceptions(monkeypatch):
    import nexus.engine.untrusted_tree_cleanup as cleanup

    def boom(exc):
        def raiser(_p):
            raise exc

        return raiser

    monkeypatch.setattr(cleanup, "remove_untrusted_tree", boom(ValueError("embedded null byte")))
    assert cleanup.remove_untrusted_tree_quietly("x") == "tree_not_removed:ValueError"
    monkeypatch.setattr(cleanup, "remove_untrusted_tree", boom(TypeError("bad")))
    assert cleanup.remove_untrusted_tree_quietly("x") == "tree_not_removed:TypeError"
    for exc in (KeyboardInterrupt(), SystemExit(1)):
        monkeypatch.setattr(cleanup, "remove_untrusted_tree", boom(exc))
        try:
            cleanup.remove_untrusted_tree_quietly("x")
        except type(exc):
            pass
        else:
            raise AssertionError("BaseException must propagate")
