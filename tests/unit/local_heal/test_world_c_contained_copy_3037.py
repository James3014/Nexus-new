"""Copies of a task's repo into World C and the apply workspace never read through a link.

Follow-up of #3037 (#3023): the PR contained the executor's own reads of the target, but the same
pre-existing link (symlink at the target or a parent, or a hard link to a file outside repo_root)
still reached a model prompt through the World C copy (pipeline_isolation), the verifier input
files and the source anchor. Every file here lives under tmp_path; the "outside" file holds
``MARK`` and must never show up in a prompt, a copy or an anchor hash.
"""

from __future__ import annotations

import hashlib
import os
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from nexus.core.contained_write import (
    PathContainmentError,
    copy_file_in_root,
    copy_tree_in_root,
)
from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
from nexus.services.local_heal.isolated_workspace_apply import (
    IsolatedApplyReceipt,
    IsolatedApplyRequest,
    run_isolated_workspace_apply,
)
from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
)
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider
from nexus.services.local_heal.local_model_source_anchor import build_local_model_source_anchor
from nexus.services.local_heal.pipeline_isolation import (
    WorldCCopyRefused,
    prepare_world_c_workspace,
    verifier_input_files,
)

TARGET = "toy/math_util.py"
ORIGINAL = "def add(a, b):\n    return a - b\n"
MARK = "OUTSIDE-SECRET-3037"
SECRET = f"def add(a, b):\n    return '{MARK}'\n"
DIFF = (
    "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n"
    "-    return a - b\n+    return a + b\n"
)


@pytest.fixture(autouse=True)
def _allow_tmp_world_c(monkeypatch):
    monkeypatch.setenv("NEXUS_ARMOR_ALLOW_EPHEMERAL", "1")


@pytest.fixture
def world(tmp_path):
    repo = tmp_path / "repo"
    (repo / "toy").mkdir(parents=True)
    (repo / TARGET).write_text(ORIGINAL)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text(SECRET)
    (outside / "math_util.py").write_text(SECRET)
    yield repo, outside
    assert (outside / "secret.txt").read_text() == SECRET


def _symlink(repo: Path, outside: Path, rel: str = TARGET) -> None:
    (repo / rel).unlink()
    (repo / rel).symlink_to(outside / "secret.txt")


def _parent_symlink(repo: Path, outside: Path, rel: str = TARGET) -> None:
    (repo / rel).unlink()
    (repo / "toy").rmdir()
    (repo / "toy").symlink_to(outside, target_is_directory=True)


def _hardlink(repo: Path, outside: Path, rel: str = TARGET) -> None:
    (repo / rel).unlink()
    os.link(outside / "secret.txt", repo / rel)


PLANT = {"symlink": _symlink, "parent_symlink": _parent_symlink, "hardlink": _hardlink}


def _tree_text(root: Path) -> str:
    text = []
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            text.append(path.read_text(errors="replace"))
    return "\n".join(text)


# --- the shared contained copy --------------------------------------------------------------


@pytest.mark.parametrize("plant", sorted(PLANT))
def test_copy_file_in_root_refuses_links(world, tmp_path, plant):
    repo, outside = world
    PLANT[plant](repo, outside)
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(PathContainmentError):
        copy_file_in_root(repo, TARGET, dest)
    assert MARK not in _tree_text(dest)


def test_copy_file_in_root_refuses_a_fifo_without_blocking(world, tmp_path):
    repo, _ = world
    (repo / TARGET).unlink()
    os.mkfifo(repo / TARGET)
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(PathContainmentError, match="not_a_regular_file"):
        copy_file_in_root(repo, TARGET, dest)


def test_copy_file_in_root_copies_a_regular_file_and_reports_a_missing_one(world, tmp_path):
    repo, _ = world
    os.chmod(repo / TARGET, 0o640)
    dest = tmp_path / "dest"
    dest.mkdir()
    assert copy_file_in_root(repo, TARGET, dest) is True
    assert (dest / TARGET).read_text() == ORIGINAL
    assert (dest / TARGET).stat().st_mode & 0o777 == 0o640
    assert copy_file_in_root(repo, "toy/missing.py", dest) is False
    assert copy_file_in_root(repo, "nodir/missing.py", dest) is False


def test_copy_tree_in_root_keeps_inside_links_and_drops_outside_ones(world, tmp_path):
    repo, outside = world
    (repo / "docs").mkdir()
    (repo / "docs" / "readme.txt").write_text("inside\n")
    (repo / "inside_link").symlink_to("docs/readme.txt")
    (repo / "outside_abs").symlink_to(outside / "secret.txt")
    (repo / "outside_rel").symlink_to("../outside/secret.txt")
    (repo / "outside_dir").symlink_to(outside, target_is_directory=True)
    # Lexically inside, but climbs out through an inside link to the root.
    (repo / "docs" / "up").symlink_to("..")
    (repo / "climb").symlink_to("docs/up/..")
    (repo / ".git").mkdir()
    (repo / ".git" / "config").write_text("ignored\n")
    dest = tmp_path / "dest"
    dest.mkdir()
    dropped = copy_tree_in_root(repo, dest, ignore_names={".git"})
    assert set(dropped) == {"outside_abs", "outside_rel", "outside_dir", "climb"}
    assert (dest / "inside_link").is_symlink()
    assert (dest / "inside_link").read_text() == "inside\n"
    assert (dest / "docs" / "up").is_symlink()
    assert not (dest / ".git").exists()
    assert (dest / TARGET).read_text() == ORIGINAL
    assert MARK not in _tree_text(dest)


@pytest.mark.parametrize("kind", ["hardlink", "fifo"])
def test_copy_tree_in_root_refuses_a_hard_link_or_special_file(world, tmp_path, kind):
    repo, outside = world
    if kind == "hardlink":
        _hardlink(repo, outside)
    else:
        (repo / TARGET).unlink()
        os.mkfifo(repo / TARGET)
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(PathContainmentError):
        copy_tree_in_root(repo, dest)
    assert MARK not in _tree_text(dest)


# --- World C copy (pipeline_isolation) ------------------------------------------------------


@pytest.mark.parametrize(
    "plant,gitlike",
    [
        ("symlink", False),
        ("parent_symlink", False),
        ("hardlink", False),
        ("hardlink", True),
    ],
)
def test_world_c_copy_refuses_a_linked_target(world, plant, gitlike):
    repo, outside = world
    if gitlike:
        (repo / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    PLANT[plant](repo, outside)
    with pytest.raises(WorldCCopyRefused, match="world_c_copy_refused"):
        prepare_world_c_workspace(repo, "wc-link", target_file=TARGET)


def test_world_c_copy_refuses_a_hard_linked_helper(world):
    # The verifier imports a non-target helper; its traceback would echo the outside text.
    repo, outside = world
    (repo / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    os.link(outside / "secret.txt", repo / "toy" / "fixtures.py")
    with pytest.raises(WorldCCopyRefused, match="file_has_other_links"):
        prepare_world_c_workspace(repo, "wc-helper", target_file=TARGET)


def test_world_c_full_copy_leaves_out_a_link_to_outside(world):
    repo, outside = world
    (repo / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    (repo / "toy" / "data.txt").symlink_to(outside / "secret.txt")
    (repo / "toy" / "alias.py").symlink_to("math_util.py")
    workspace = prepare_world_c_workspace(repo, "wc-abs", target_file=TARGET)
    assert not (workspace / "toy" / "data.txt").exists()
    assert not (workspace / "toy" / "data.txt").is_symlink()
    assert (workspace / "toy" / "alias.py").read_text() == ORIGINAL
    assert MARK not in _tree_text(workspace)


def test_world_c_synthetic_copy_of_regular_files_is_unchanged(world):
    repo, _ = world
    (repo / "repro.py").write_text("print('x')\n")
    workspace = prepare_world_c_workspace(
        repo, "wc-ok", target_file=TARGET, verifier_files=("repro.py", "missing.py")
    )
    assert (workspace / TARGET).read_text() == ORIGINAL
    assert (workspace / "repro.py").read_text() == "print('x')\n"
    assert not (workspace / "missing.py").exists()


@pytest.mark.parametrize("twice", ["repro_and_verifier", "target_and_verifier"])
def test_world_c_synthetic_copy_names_the_same_file_twice(world, twice):
    repo, _ = world
    (repo / "repro.py").write_text("print('x')\n")
    if twice == "repro_and_verifier":
        kwargs = {"repro_script": "repro.py", "verifier_files": ("repro.py",)}
    else:
        kwargs = {"verifier_files": (TARGET, "./" + TARGET)}
    workspace = prepare_world_c_workspace(repo, "wc-twice", target_file=TARGET, **kwargs)
    assert (workspace / TARGET).read_text() == ORIGINAL


def test_world_c_synthetic_copy_treats_repro_script_text_as_no_file(world):
    # route_context["repro_script"] can be the script itself, longer than any file name.
    repo, _ = world
    text = "import sys\n" + "x" * 300 + "\nprint('/Users/a/b')\n"
    workspace = prepare_world_c_workspace(repo, "wc-text", target_file=TARGET, repro_script=text)
    assert (workspace / TARGET).read_text() == ORIGINAL
    workspace = prepare_world_c_workspace(
        repo, "wc-longname", target_file=TARGET, verifier_files=("y" * 300,)
    )
    assert (workspace / TARGET).read_text() == ORIGINAL


@pytest.mark.parametrize("failure", ["refused", "other"])
def test_world_c_copy_removes_its_workspace_on_any_failure(world, tmp_path, monkeypatch, failure):
    import nexus.services.local_heal.pipeline_isolation as isolation

    repo, outside = world
    made = tmp_path / "made"
    monkeypatch.setattr(isolation, "make_isolated_workspace", lambda prefix: made.mkdir() or made)
    if failure == "refused":
        _hardlink(repo, outside)
        expected = WorldCCopyRefused
    else:

        def broken(*_a, **_kw):
            raise OSError("disk full")

        monkeypatch.setattr(isolation, "copy_file_in_root", broken)
        expected = OSError
    with pytest.raises(expected):
        prepare_world_c_workspace(repo, "wc-cleanup", target_file=TARGET)
    assert not made.exists()


def test_verifier_input_files_skips_a_hard_link(world):
    repo, outside = world
    os.link(outside / "secret.txt", repo / "repro.py")
    assert verifier_input_files(repo, ("python", "repro.py")) == ()


# --- the executor: no outside text reaches a prompt -----------------------------------------


def _pipeline_request(repo: Path, task_id: str, verifier_command=None, candidate_models=()):
    snap = {
        "execution_topology": "localheal_pipeline",
        "model_call_allowed": True,
        "selected_executor": "local_model",
        "executor_model": "qwen2.5-coder:7b-instruct",
        "protocol_mode": "anchored_edit",
        "mutation_allowed": True,
        "verifier_allowed": True,
    }
    if candidate_models:
        snap["delegated_retry_candidate_models"] = list(candidate_models)
    return LocalModelExecutorRequest(
        task_id=task_id,
        problem_statement="fix add in toy/math_util.py",
        repo_root=str(repo),
        target_file=TARGET,
        selected_capabilities=("local_model_executor",),
        evidence_refs=(),
        dry_run=False,
        route_context={
            "verifier_command": list(verifier_command or ["python3", "-c", "pass"]),
            "python_executable": sys.executable,
            "signal_snapshot": snap,
            "target_symbol": "add",
        },
    )


def _pipeline_result(*_a, **_kw):
    return CapabilityExecutionResult(
        name="repair_loop",
        selected=True,
        invoked=True,
        gate_passed=True,
        outcome_contributed=True,
        evidence_present=True,
        failure_reason="",
        telemetries={
            "pipeline_final_patch": DIFF,
            "pipeline_solve_eligible": True,
            "pipeline_failure_reason": "",
            "patch_synthesis_output_len": len(DIFF),
            "patch_synthesis_model_name": "q",
            "patch_synthesis_model_called": True,
            "provider_invoked": True,
            "model_called": True,
            "localheal_pipeline_run_called": True,
            "localheal_pipeline_run_success": True,
            "localheal_pipeline_invoked": True,
            "localheal_pipeline_actual_execution": True,
            "orchestrator_run_reachable": True,
            "path_a_actual_execution": True,
        },
    )


def _apply_ok(r):
    return IsolatedApplyReceipt(
        task_id=r.task_id,
        patch_apply_status="applied",
        patch_apply_error="",
        target_file=r.target_file,
        selected_candidate_hash=r.selected_candidate_hash,
        applied_patch_hash=r.selected_candidate_hash,
        selected_candidate_hash_matches_applied=True,
        candidate_output_isolated=True,
        workspace_path="/nonexistent/ws",
        mutation_allowed=True,
        applied_patch_hash_source="git_diff",
    )


def _verifier_fail(r):
    return IsolatedVerifierReceipt(
        task_id=r.task_id,
        verifier_status="fail",
        exit_code=1,
        stdout_tail="AssertionError",
        stderr_tail="",
        verifier_error="",
        verifier_allowed=True,
    )


def _run(req, *, mock_pipeline=False, mock_apply=True):
    prompts: list[str] = []

    def gen(preq):
        prompts.append(preq.prompt or "")
        return DIFF

    patches = []
    if mock_apply:
        patches += [
            patch(
                "nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply",
                side_effect=_apply_ok,
            ),
            patch(
                "nexus.services.local_heal.local_model_executor.run_isolated_verifier",
                side_effect=_verifier_fail,
            ),
        ]
    if mock_pipeline:
        patches.append(
            patch(
                "nexus.services.local_heal.local_model_capability_executors."
                "LocalHealPipelineCapabilityExecutor.execute",
                side_effect=_pipeline_result,
            )
        )
    for p in patches:
        p.start()
    try:
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(gen))
    finally:
        for p in reversed(patches):
            p.stop()
    return prompts, resp


@pytest.mark.parametrize(
    "plant,gitlike",
    [
        ("symlink", False),
        ("parent_symlink", False),
        ("hardlink", False),
        ("hardlink", True),
    ],
)
def test_main_pipeline_keeps_a_linked_target_out_of_every_prompt(world, plant, gitlike):
    # Before: the executor refused its own snapshot read, then ran the real pipeline on a World C
    # copy that followed (or dereferenced) the same link, and localization put it in the prompt.
    repo, outside = world
    if gitlike:
        (repo / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    PLANT[plant](repo, outside)
    prompts, resp = _run(_pipeline_request(repo, f"wc-{plant}-{gitlike}"))
    meta = resp.raw_model_metadata
    assert meta["original_target_read_refused"]
    assert all(MARK not in p for p in prompts)
    assert "world_c_copy_refused" in str(meta.get("path_a_failure_reason", ""))
    assert MARK not in resp.candidate_patch


def test_hard_linked_verifier_input_stays_out_of_the_committee_prompt(world):
    # Before: verifier_input_files passed the hard link, the apply workspace got its content and
    # the verifier's SyntaxError echoed it into the delegated-retry committee prompt.
    repo, outside = world
    (repo / ".git").mkdir()
    (outside / "repro.txt").write_text(f"{MARK} private host line\n")
    os.link(outside / "repro.txt", repo / "repro.py")
    req = _pipeline_request(
        repo,
        "wc-verifier-input",
        verifier_command=[sys.executable, "repro.py"],
        candidate_models=("qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct"),
    )
    prompts, resp = _run(req, mock_pipeline=True, mock_apply=False)
    meta = resp.raw_model_metadata
    assert MARK not in str(meta.get("verifier_stderr_excerpt", ""))
    assert all(MARK not in p for p in prompts)


def test_restore_refused_candidate_is_not_handed_back(world):
    # The executor applies nothing when it cannot restore the original; its caller must not get
    # the candidate to apply from the same repo_root either.
    repo, outside = world
    _symlink(repo, outside)
    _prompts, resp = _run(_pipeline_request(repo, "wc-restore-refused"), mock_pipeline=True)
    assert resp.raw_model_metadata["isolated_apply_status"] == "restore_refused"
    assert resp.candidate_patch == ""


# --- isolated apply workspace ---------------------------------------------------------------


@pytest.mark.parametrize("plant", sorted(PLANT))
def test_isolated_apply_refuses_a_linked_target(world, plant):
    repo, outside = world
    PLANT[plant](repo, outside)
    receipt = run_isolated_workspace_apply(
        IsolatedApplyRequest(
            task_id="apply-link",
            source_root=str(repo),
            target_file=TARGET,
            unified_diff=DIFF,
            selected_candidate_hash="h",
            work_dir="",
            mutation_allowed=True,
        )
    )
    assert receipt.patch_apply_status == "failed"
    assert not receipt.candidate_output_isolated
    if receipt.workspace_path and Path(receipt.workspace_path).is_dir():
        assert MARK not in _tree_text(Path(receipt.workspace_path))


def test_isolated_apply_of_a_regular_target_still_applies(world):
    repo, _ = world
    receipt = run_isolated_workspace_apply(
        IsolatedApplyRequest(
            task_id="apply-ok",
            source_root=str(repo),
            target_file=TARGET,
            unified_diff=DIFF,
            selected_candidate_hash="h",
            work_dir="",
            mutation_allowed=True,
        )
    )
    assert receipt.patch_apply_status == "applied", receipt.patch_apply_error
    assert "a + b" in (Path(receipt.workspace_path) / TARGET).read_text()


# --- source anchor --------------------------------------------------------------------------


@pytest.mark.parametrize("plant", sorted(PLANT))
def test_source_anchor_does_not_hash_a_linked_target(world, plant):
    repo, outside = world
    PLANT[plant](repo, outside)
    anchor = build_local_model_source_anchor(str(repo), TARGET, "add")
    outside_hash = hashlib.sha256(SECRET.strip().encode()).hexdigest()
    assert anchor.span_hash != outside_hash
    assert "source_anchor_missing" in anchor.blockers
    assert anchor.telemetry["source_anchor_read_refused"]


def test_source_anchor_of_a_regular_target_is_unchanged(world):
    repo, _ = world
    anchor = build_local_model_source_anchor(str(repo), TARGET, "add")
    assert anchor.blockers == ()
    assert anchor.span_hash == hashlib.sha256(ORIGINAL.strip().encode()).hexdigest()


def test_source_anchor_does_not_block_on_a_fifo(world):
    repo, _ = world
    fifo = repo / TARGET
    fifo.unlink()
    os.mkfifo(fifo)
    done = threading.Event()
    result = []

    def call():
        try:
            result.append(build_local_model_source_anchor(str(repo), TARGET, "add"))
        finally:
            done.set()

    thread = threading.Thread(target=call, daemon=True)
    thread.start()
    finished = done.wait(5)
    if not finished:  # release the blocked reader so the thread ends
        fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        os.close(fd)
        done.wait(5)
    assert finished, "build_local_model_source_anchor blocked on a FIFO target"
    assert "source_anchor_missing" in result[0].blockers


# --- disposable scratch copies (eval gate, repro run, micro verify) -------------------------


def test_scratch_copy_refuses_a_hard_linked_file(world, tmp_path):
    from nexus.services.local_heal.scratch_copy import copy_repo_entries

    repo, outside = world
    os.link(outside / "secret.txt", repo / "toy" / "helper.py")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(PathContainmentError, match="file_has_other_links"):
        copy_repo_entries(repo, scratch)
    assert MARK not in _tree_text(scratch)


@pytest.mark.parametrize("nested", ["pkg/.venv/h.py", "pkg/.git/h"])
def test_scratch_copy_walks_nested_git_and_venv(world, tmp_path, nested):
    # The model sandbox keeps only the top-level .git/.venv read-only.
    from nexus.services.local_heal.scratch_copy import copy_repo_entries

    repo, outside = world
    (repo / nested).parent.mkdir(parents=True)
    os.link(outside / "secret.txt", repo / nested)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(PathContainmentError, match="file_has_other_links"):
        copy_repo_entries(repo, scratch)
    assert MARK not in _tree_text(scratch)


def test_scratch_copy_still_copies_links_as_links_and_skips_host_run_subtrees(world, tmp_path):
    from nexus.services.local_heal.scratch_copy import copy_repo_entries

    repo, outside = world
    (repo / ".venv" / "lib").mkdir(parents=True)
    os.link(outside / "math_util.py", repo / ".venv" / "lib" / "dep.py")  # uv may hard-link
    (repo / "toy" / "link.py").symlink_to("math_util.py")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    copy_repo_entries(repo, scratch)
    assert (scratch / TARGET).read_text() == ORIGINAL
    assert (scratch / "toy" / "link.py").is_symlink()


def test_micro_verify_keeps_a_hard_linked_helper_out_of_its_details(tmp_path):
    from nexus.services.local_heal.micro_verifier import micro_verify_in_scratch_copy

    outside = tmp_path / "outside"
    repo = tmp_path / "repo"
    outside.mkdir()
    (repo / "toy").mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\nname='toy'\n")
    (repo / "toy" / "__init__.py").write_text("")
    (outside / "secret.py").write_text(MARK.replace("-", "_") + "\n")
    os.link(outside / "secret.py", repo / "toy" / "helper.py")
    (repo / "toy" / "x.py").write_text("from toy import helper\n\ndef f():\n    return 2\n")
    result = micro_verify_in_scratch_copy(
        "--- a/toy/x.py\n+++ b/toy/x.py\n",
        str(repo),
        ["toy/x.py"],
        verifier_env_metadata={"interpreter": sys.executable},
        env_taxonomy={"interpreter": sys.executable},
    )
    assert not result.passed
    assert MARK.replace("-", "_") not in f"{result.error_message}:{result.details}"
