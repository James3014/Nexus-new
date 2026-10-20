"""Tests for the #2721 measurement harness (no network, no model, no Gateway)."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from scripts.bench.measure_2721 import (
    arms,
    blind,
    dryrun,
    leakage,
    materialize,
    nexus_driver,
    scope,
    task_text,
)
from scripts.bench.measure_2721.common import capture_diff, read_jsonl
from scripts.bench.measure_2721.fakes import FakeGateway
from scripts.bench.measure_2721.providers import FakeProvider

needs_sandbox = pytest.mark.skipif(not Path("/usr/bin/sandbox-exec").exists(), reason="macOS sandbox-exec required")

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@invalid", "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@invalid", "GIT_CONFIG_NOSYSTEM": "1",
}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env={**os.environ, **GIT_ENV}, check=True,
                          capture_output=True, text=True).stdout


@pytest.fixture(autouse=True)
def _no_held_gateway_env():
    from scripts.bench.measure_2721 import gateway_env

    gateway_env.reset()
    yield
    gateway_env.reset()


@pytest.fixture()
def bank(tmp_path: Path) -> dict:
    """A mirror with a base commit, then a later 'fix' commit, a tag and a branch."""
    mirror = tmp_path / "repos" / "sympy"
    (mirror / "sympy" / "core").mkdir(parents=True)
    (mirror / "sympy" / "core" / "tests").mkdir()
    _git(mirror, "init", "-q")
    (mirror / "sympy" / "core" / "add.py").write_text("def add(a, b):\n    return a - b\n")
    (mirror / "sympy" / "core" / "tests" / "test_old.py").write_text("def test_x():\n    pass\n")
    (mirror / "README.md").write_text("readme\n")
    _git(mirror, "add", "-A")
    _git(mirror, "commit", "-qm", "base")
    base = _git(mirror, "rev-parse", "HEAD").strip()
    (mirror / "sympy" / "core" / "add.py").write_text("def add(a, b):\n    return a + b\n")
    _git(mirror, "commit", "-qam", "GOLD FIX")
    _git(mirror, "tag", "v-fixed")
    _git(mirror, "branch", "fix-branch")
    test_patch = (
        "diff --git a/sympy/core/tests/test_add.py b/sympy/core/tests/test_add.py\n"
        "new file mode 100644\n--- /dev/null\n+++ b/sympy/core/tests/test_add.py\n@@ -0,0 +1,2 @@\n"
        "+def test_add():\n+    assert 1\n"
    )
    row = {"id": "sympy-1", "set": "M", "repo": "sympy/sympy", "base_commit": base,
           "problem_statement": "add() subtracts\n\nadd(1, 2) returns -1.",
           "gold_patch": "diff --git a/sympy/core/add.py b/sympy/core/add.py\n", "test_patch": test_patch}
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text(json.dumps(row) + "\n")
    return {"root": tmp_path, "mirror": mirror, "base": base, "row": row, "tasks": tasks}


@pytest.fixture()
def manifest(bank: dict, monkeypatch) -> Path:
    out = bank["root"] / "mat"
    # A per-task venv under an operator read root, as the measurement requires.
    venvs = bank["root"] / "venvs"
    venv = venvs / bank["row"]["id"]
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").symlink_to("/usr/bin/python3")
    (venv / "pyvenv.cfg").write_text("home = /usr/bin\n")
    monkeypatch.setenv("NEXUS_MEASUREMENT_READ_ROOTS", str(venvs.resolve()))
    assert materialize.main(["--tasks", str(bank["tasks"]), "--repos-root", str(bank["root"] / "repos"),
                             "--out", str(out), "--venv-root", str(venvs)]) == 0
    return out / "manifest.jsonl"


# -- task text ------------------------------------------------------------------

def test_short_statement_goes_verbatim_into_what():
    text = task_text.build_task_text("  Title\n\nBody  ", ["pkg/"])
    assert text.what == "Title\n\nBody"
    assert text.why == task_text.INSTRUCTION
    assert not text.truncated


def test_long_statement_is_split_over_what_and_why_without_loss():
    statement = "x" * 3000 + "y" * 3000
    text = task_text.build_task_text(statement, ["pkg/"])
    assert len(text.what) <= 4000 and len(text.why) <= 4000
    assert not text.truncated
    body = text.what.replace(task_text.CONTINUED_MARKER.strip(), "") + text.why
    assert body.count("x") + body.count("y") >= 6000


def test_overlong_statement_is_truncated_and_flagged():
    text = task_text.build_task_text("z" * 12000, ["pkg/"])
    assert text.truncated
    assert len(text.what) <= 4000 and len(text.why) <= 4000
    assert text.why.endswith(task_text.INSTRUCTION)


@pytest.mark.parametrize("allowed", [[], ["a", "b", "c", "d", "e"]])
def test_p1_allowed_files_limit(allowed):
    with pytest.raises(ValueError):
        task_text.build_task_text("t", allowed)


def test_harness_prompt_matches_gateway_worker_template():
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

    real = SelfHostedTaskService._prompt
    text = task_text.build_task_text("Issue\n\nbody with `code`", ["src/pkg/", "src/x.py"])
    from types import SimpleNamespace

    contract = SimpleNamespace(goal=SimpleNamespace(what=text.what, why=text.why),
                               allowed_files=list(text.allowed_files),
                               verifier_commands=list(text.verifier_commands))
    assert task_text.render_worker_prompt(text) == real(contract)


# -- scope ----------------------------------------------------------------------

def test_every_repo_scope_is_valid_for_p1():
    from nexus.orchestrator.task_card_scope import protected_path_reason
    from nexus.orchestrator.task_contract import _normalize_repository_path

    for repo, entries in scope.REPO_SCOPE.items():
        assert 1 <= len(entries) <= scope.MAX_SCOPE_ENTRIES, repo
        for entry in entries:
            assert protected_path_reason(entry) is None, entry
            assert _normalize_repository_path(entry) == entry
            assert not scope.is_test_path(entry.rstrip("/") + "/x.py"), entry


def test_scope_boundary_rule():
    assert scope.in_scope("sympy/core/add.py", ["sympy/"])
    assert not scope.in_scope("sympyx/a.py", ["sympy/"])
    assert scope.in_scope("src/py.py", ["src/py.py"])
    assert scope.out_of_scope(["doc/a.rst", "sympy/a.py"], ["sympy/"]) == ["doc/a.rst"]
    assert scope.is_test_path("sympy/core/tests/test_add.py")
    assert scope.is_test_path("testing/test_terminal.py")
    assert not scope.is_test_path("sympy/core/add.py")


# -- materializer ---------------------------------------------------------------

def test_materialized_checkout_holds_only_the_base_commit(bank, manifest):
    (task,) = list(read_jsonl(manifest))
    checkout = Path(task["base_checkout"])
    assert _git(checkout, "rev-parse", "HEAD").strip() == bank["base"]
    assert _git(checkout, "rev-list", "--all").split() == [bank["base"]]
    assert _git(checkout, "for-each-ref").strip() == ""
    assert "GOLD FIX" not in _git(checkout, "log", "--all", "--format=%s")
    assert "a - b" in (checkout / "sympy/core/add.py").read_text()
    assert not (checkout / "sympy/core/tests/test_add.py").exists()
    assert task["test_patch_withheld"] is True and task["scope"] == ["sympy/"]
    saved = json.dumps(task)
    assert "GOLD" not in saved and "test_add" not in saved and "gold_patch" not in saved
    prompt = (checkout.parent / "TASK_PROMPT.txt").read_text()
    assert task_text.render_worker_prompt(task["text"]) == prompt


def test_materializer_leaves_the_mirror_untouched(bank, manifest):
    assert _git(bank["mirror"], "status", "--porcelain").strip() == ""
    assert _git(bank["mirror"], "worktree", "list").count("\n") == 1


def test_materializer_rejects_unknown_repo(bank, tmp_path):
    row = dict(bank["row"], repo="someone/unknown")
    with pytest.raises(KeyError):
        materialize.materialize_task(row, bank["root"] / "repos", tmp_path / "o")


# -- arms -----------------------------------------------------------------------

def _edit(workdir: Path, _prompt: str) -> None:
    (workdir / "sympy/core/add.py").write_text("def add(a, b):\n    return a + b\n")
    (workdir / "sympy/core/new_helper.py").write_text("X = 1\n")
    (workdir / "README.md").write_text("changed\n")


def test_bare_arm_captures_full_diff_and_scope_facts(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    provider = FakeProvider(edit=_edit)
    row = arms.run_bare(task, 1, tmp_path / "run", provider, timeout_seconds=5)
    diff = Path(row["diff_path"]).read_text()
    assert "+    return a + b" in diff and "new_helper.py" in diff
    assert row["out_of_scope_paths"] == ["README.md"]
    assert row["model_calls"] == 0 and row["outcome"] == "OK"
    assert provider.prompts[0]["prompt"] == task_text.render_worker_prompt(task["text"])
    assert not (tmp_path / "run" / "work" / row["run_id"]).exists()


def test_capture_diff_does_not_touch_the_worktree_index(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    work = tmp_path / "w"
    materialize.checkout_base(Path(task["base_checkout"]), task["base_commit"], work)
    (work / "untracked.py").write_text("u = 1\n")
    assert "untracked.py" in capture_diff(work, task["base_commit"])
    assert _git(work, "diff", "--cached", "--name-only").strip() == ""


def test_noop_arm_is_empty(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    row = arms.run_noop(task, 1, tmp_path / "run")
    assert row["empty"] and row["model_calls"] == 0 and Path(row["diff_path"]).read_text() == ""


# -- NEXUS driver ---------------------------------------------------------------

@pytest.mark.parametrize("url", ["http://127.0.0.1:8766", "http://localhost:8766/", "https://m4.example:8766"])
def test_live_gateway_is_refused(url):
    with pytest.raises(nexus_driver.LiveGatewayRefused):
        nexus_driver.GatewayClient(url, "t", transport=FakeGateway())


def test_token_file_must_be_private(tmp_path):
    path = tmp_path / "tok"
    path.write_text("NEXUS_MCP_GATEWAY_TOKEN=secret-xyz\n")
    os.chmod(path, 0o644)
    with pytest.raises(PermissionError):
        nexus_driver.read_token(path)
    os.chmod(path, 0o600)
    assert nexus_driver.read_token(path) == "secret-xyz"


def _driver(gateway: FakeGateway, token: str = "tok-123") -> nexus_driver.NexusArmDriver:
    client = nexus_driver.GatewayClient("http://127.0.0.1:18766", token, transport=gateway)
    return nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s", sleep=lambda _s: None)


def test_external_task_is_blocked_until_gateway_supports_it(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    gateway = FakeGateway(external_target=False)
    row = _driver(gateway).run(task, 1, tmp_path / "run", timeout_seconds=5)
    assert row["outcome"] == nexus_driver.OUTCOME_BLOCKED_EXTERNAL
    assert gateway.calls == []  # no card, no worker
    assert row["empty"]


def test_driver_runs_the_p1_sequence_and_always_cancels(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    gateway = FakeGateway(external_target=True)
    row = _driver(gateway).run(task, 1, tmp_path / "run", timeout_seconds=5)
    tools = [call["tool"] for call in gateway.calls]
    assert tools == ["nexus_task_card_create", "nexus_task_card_commit", "nexus_worker_candidate",
                     "nexus_task_wait", "nexus_task_status", "nexus_task_cancel", "nexus_task_status"]
    worker = gateway.calls[2]["arguments"]
    assert worker["what"] == task["text"]["what"] and worker["why"] == task["text"]["why"]
    controller = Path(worker["external_target"]["repo_root"])
    # A fresh Controller per (task, repeat): never the shared materialized checkout (gap F6).
    assert controller != Path(task["base_checkout"]).resolve()
    assert controller.parent.name == row["run_id"] and worker["external_target"]["base_revision"] == task["base_commit"]
    assert _git(controller, "rev-list", "--all").split() == [task["base_commit"]]
    assert row["outcome"] == "OK" and row["empty"]


def test_driver_cancels_after_a_worker_error_and_redacts_the_token(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    gateway = FakeGateway(worker_error={"error": "agy_pool_busy for tok-123"})
    row = _driver(gateway, token="tok-123").run(task, 1, tmp_path / "run", timeout_seconds=5)
    assert [c["tool"] for c in gateway.calls][-2:] == ["nexus_task_cancel", "nexus_task_status"]
    assert row["infra"] is True and row["outcome"] == "INFRA"
    for path in (tmp_path / "run").rglob("*"):
        if path.is_file():
            assert "tok-123" not in path.read_text(errors="ignore"), path


# -- blinding -------------------------------------------------------------------

def test_blinding_separates_the_arm_map(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    run = tmp_path / "run"
    arms.run_bare(task, 1, run, FakeProvider(edit=_edit), timeout_seconds=5)
    arms.run_noop(task, 1, run)
    _driver(FakeGateway(worker_error={"error": "agy_pool_busy"})).run(task, 1, run, timeout_seconds=5)
    out, arm_map = tmp_path / "blind", tmp_path / "b6" / "arm_map.json"
    assert blind.main(["--run-roots", str(run), "--out", str(out), "--arm-map", str(arm_map),
                       "--manifest", str(manifest)]) == 0
    candidates = list(read_jsonl(out / "candidates.jsonl"))
    assert len(candidates) == 2
    for item in candidates:
        assert set(item) == {"opaque_id", "task_id", "repeat", "diff_sha256", "scoring_flags"}
        assert set(item["scoring_flags"]) <= blind.SCORER_VISIBLE_FLAGS and item["repeat"] == 1
        assert (out / "candidates" / f"{item['opaque_id']}.diff").is_file()
    text = (out / "candidates.jsonl").read_text()
    assert "BARE" not in text and "NOOP" not in text and "m2721-" not in text
    mapping = json.loads(arm_map.read_text())
    assert stat.S_IMODE(arm_map.stat().st_mode) == 0o600
    assert sorted(v["arm"] for v in mapping["map"].values()) == ["BARE", "NOOP"]
    assert [e["arm"] for e in mapping["excluded"]] == ["NEXUS"]


def test_blinding_refuses_arm_map_inside_scorer_dir(tmp_path):
    with pytest.raises(SystemExit):
        blind.main(["--run-roots", str(tmp_path), "--out", str(tmp_path / "o"),
                    "--arm-map", str(tmp_path / "o" / "m.json")])


# -- dry run --------------------------------------------------------------------

@needs_sandbox
def test_claude_dry_run_proves_identical_invocations(manifest, tmp_path):
    report = dryrun.dry_run(manifest, tmp_path / "dry", file_scope=True)
    assert report["status"] == "PASS", json.dumps(report, indent=1)
    assert report["model_calls"] == 0 and report["zero_model_edits"] == []
    (task_id,) = report["per_task"]
    traces = tmp_path / "dry" / "traces"
    bare_id = next(p.name for p in traces.iterdir() if p.name.startswith("m2721-bare-"))
    nexus_id = next(p.name for p in traces.iterdir() if p.name.startswith("m2721-nexus-"))
    bare, nexus = dryrun._trace_for(traces, bare_id), dryrun._trace_for(traces, nexus_id)
    prompt = bare["observed"]["argv"][-1]
    assert dryrun.compare_invocations(bare, nexus, prompt, prompt) == []
    # Tampering is caught: an extra env value, a different flag, a prompt hint.
    env_tamper = json.loads(json.dumps(nexus))
    env_tamper["observed"]["env"]["LANG"] = "xx"
    assert "env LANG differs" in dryrun.compare_invocations(bare, env_tamper, prompt, prompt)
    flag_tamper = json.loads(json.dumps(nexus))
    flag_tamper["observed"]["argv"][1] = "--safe-mode"
    assert "argv flags differ between arms" in dryrun.compare_invocations(bare, flag_tamper, prompt, prompt)
    hint = json.loads(json.dumps(bare))
    hint["observed"]["argv"][-1] = prompt + " hint"
    assert dryrun.compare_invocations(hint, nexus, prompt, prompt)


def test_agy_provider_fails_closed_without_the_pool(monkeypatch, tmp_path):
    """No pool -> INFRA before any agy process starts (the call is never made)."""
    from scripts.bench.measure_2721.providers import STATUS_INFRA, AgyPoolProvider

    monkeypatch.setenv("NEXUS_AGY_ACCOUNT_POOL_ENABLED", "0")
    monkeypatch.setenv("NEXUS_AGY_WORKER_MODEL", "gemini-3.8-flash-medium")
    result = AgyPoolProvider().run(prompt="p", workdir=tmp_path, timeout_seconds=1, run_id="r")
    assert result.status == STATUS_INFRA and result.model_calls == 0
    assert result.model == "gemini-3.8-flash-medium"


# -- prereg v0.2 §8: test-hunk stripping, timeout flag, UPSTREAM_LOOKUP -----------


_MIXED_DIFF = (
    "diff --git a/sympy/core/add.py b/sympy/core/add.py\n--- a/sympy/core/add.py\n+++ b/sympy/core/add.py\n"
    "@@ -1 +1 @@\n-a\n+b\n"
    "diff --git a/sympy/core/tests/test_add.py b/sympy/core/tests/test_add.py\nnew file mode 100644\n"
    "--- /dev/null\n+++ b/sympy/core/tests/test_add.py\n@@ -0,0 +1 @@\n+x\n"
    "diff --git a/sympy/conftest.py b/sympy/conftest.py\n--- a/sympy/conftest.py\n+++ b/sympy/conftest.py\n"
    "@@ -1 +1 @@\n-c\n+d\n"
)


def test_strip_test_hunks_keeps_only_source_blocks():
    kept, removed = leakage.strip_test_hunks(_MIXED_DIFF)
    assert removed == ["sympy/core/tests/test_add.py", "sympy/conftest.py"]
    assert "sympy/core/add.py" in kept and "test_add" not in kept and "conftest" not in kept
    assert kept.startswith("diff --git a/sympy/core/add.py") and kept.endswith("+b\n")
    assert leakage.strip_test_hunks("") == ("", [])


def test_strip_test_hunks_catches_a_rename_out_of_a_test_dir():
    diff = ("diff --git a/pkg/tests/helper.py b/pkg/helper.py\nsimilarity index 100%\n"
            "rename from pkg/tests/helper.py\nrename to pkg/helper.py\n")
    assert leakage.strip_test_hunks(diff) == ("", ["pkg/helper.py"])


def test_lookup_signals_flags_web_tools_denials_and_upstream_urls():
    clean = leakage.lookup_signals(["I edited sympy/core/add.py."], repo="sympy/sympy")
    assert clean["flag"] is None
    used = leakage.lookup_signals(["| `search_web` | Succeeded |"], repo="sympy/sympy")
    assert used["flag"] == leakage.FLAG_UPSTREAM_LOOKUP and used["web_tools_seen"] == ["search_web"]
    denied = leakage.lookup_signals([""], denied_actions=[{"action": "read_url", "display_name": "ReadUrlContent"}])
    assert denied["flag"] == leakage.FLAG_UPSTREAM_LOOKUP and denied["web_actions_denied"] == ["read_url"]
    url = leakage.lookup_signals(["see https://github.com/sympy/sympy/pull/30748"], repo="sympy/sympy")
    assert url["flag"] and url["upstream_urls_seen"] == ["github.com/sympy/sympy/pull/30748"]


def test_task_text_tells_both_arms_not_to_touch_tests():
    assert "Do not add or modify test files" in task_text.INSTRUCTION
    assert not leakage.lookup_signals([task_text.INSTRUCTION])["flag"]


def test_bare_row_flags_timeout_and_lookup_and_keeps_the_diff(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    provider = FakeProvider(edit=_edit, status="TIMEOUT",
                            extra={"response_text": "used search_web", "denied_actions": [], "stderr_tail": ""})
    row = arms.run_bare(task, 1, tmp_path / "run", provider, timeout_seconds=5)
    assert row["outcome"] == "TIMEOUT" and not row["empty"]  # the worktree diff at the cap is kept
    assert row["flags"] == [leakage.FLAG_TIMEOUT, leakage.FLAG_UPSTREAM_LOOKUP]


def test_nexus_row_scans_worker_evidence_for_lookup(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    gateway = FakeGateway()
    original = gateway._answer

    def answer(name, args):
        payload = original(name, args)
        if name == "nexus_task_status":
            payload["execution"] = {"stdout_tail": "tool read_url_content denied"}
        return payload

    gateway._answer = answer
    row = _driver(gateway).run(task, 1, tmp_path / "run", timeout_seconds=5)
    assert leakage.FLAG_UPSTREAM_LOOKUP in row["flags"]


def test_blinding_strips_test_blocks_and_records_it_only_in_the_arm_map(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)

    def edit_with_test(workdir: Path, prompt: str) -> None:
        _edit(workdir, prompt)
        (workdir / "sympy/core/tests/test_mine.py").write_text("def test_mine():\n    assert True\n")

    run = tmp_path / "run"
    arms.run_bare(task, 1, run, FakeProvider(edit=edit_with_test), timeout_seconds=5)
    out, arm_map = tmp_path / "blind", tmp_path / "b6" / "arm_map.json"
    blind.main(["--run-roots", str(run), "--out", str(out), "--arm-map", str(arm_map), "--manifest", str(manifest)])
    (item,) = list(read_jsonl(out / "candidates.jsonl"))
    scored = (out / "candidates" / f"{item['opaque_id']}.diff").read_text()
    assert "test_mine" not in scored and "+    return a + b" in scored
    entry = json.loads(arm_map.read_text())["map"][item["opaque_id"]]
    assert entry["stripped_test_paths"] == ["sympy/core/tests/test_mine.py"]
    assert leakage.FLAG_TEST_HUNKS_STRIPPED in entry["flags"]
    assert entry["scored_diff_sha256"] == item["diff_sha256"] != entry["raw_diff_sha256"]
    assert "TEST_HUNKS" not in (out / "candidates.jsonl").read_text()



# -- gap review: filter order, stuck Gateway, Claude BARE -------------------------

def test_filter_order_is_tamper_then_tests_then_scope():
    diff = (
        "diff --git a/sympy/conftest.py b/sympy/conftest.py\n--- a/sympy/conftest.py\n+++ b/sympy/conftest.py\n"
        "@@ -1 +1 @@\n-a\n+b\n"
        "diff --git a/setup.cfg b/setup.cfg\n--- a/setup.cfg\n+++ b/setup.cfg\n@@ -1 +1 @@\n-c\n+d\n"
        "diff --git a/sympy/core/add.py b/sympy/core/add.py\n--- a/sympy/core/add.py\n+++ b/sympy/core/add.py\n"
        "@@ -1 +1 @@\n-e\n+f\n"
    )
    result = leakage.filter_candidate(diff, ["sympy/"])
    # conftest is a tamper even though the test strip would remove it.
    assert result["tamper_paths"] == ["sympy/conftest.py", "setup.cfg"]
    assert result["stripped_test_paths"] == ["sympy/conftest.py"]
    assert result["stripped_out_of_scope_paths"] == ["setup.cfg"]
    assert result["flags"] == [leakage.FLAG_HARNESS_TAMPER, leakage.FLAG_TEST_HUNKS_STRIPPED,
                               leakage.FLAG_OUT_OF_SCOPE_STRIPPED]
    assert leakage.split_file_blocks(result["scored_diff"])[0][0] == "sympy/core/add.py"
    assert len(leakage.split_file_blocks(result["scored_diff"])) == 1


def test_blinding_flags_a_scored_diff_that_does_not_apply(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    run = tmp_path / "run"
    row = arms.run_bare(task, 1, run, FakeProvider(edit=_edit), timeout_seconds=5)
    Path(row["diff_path"]).write_text(
        "diff --git a/sympy/core/add.py b/sympy/core/add.py\n--- a/sympy/core/add.py\n+++ b/sympy/core/add.py\n"
        "@@ -1 +1 @@\n-no such line\n+x\n")
    rows = list(read_jsonl(run / "rows.jsonl"))
    rows[0]["diff_sha256"] = __import__("hashlib").sha256(Path(row["diff_path"]).read_bytes()).hexdigest()
    result = blind.blind(rows, tmp_path / "o", tmp_path / "b6" / "m.json", {task["task_id"]: task})
    entry = next(iter(json.loads((tmp_path / "b6" / "m.json").read_text())["map"].values()))
    assert result["candidates"] == 1 and leakage.FLAG_PATCH_DOES_NOT_APPLY in entry["flags"]


def test_driver_stops_the_batch_when_a_task_does_not_terminate(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    gateway = FakeGateway()
    original = gateway._answer

    def answer(name, args):
        payload = original(name, args)
        if name == "nexus_task_status":
            payload["status"] = "PENDING_HUMAN_APPROVAL"
        return payload

    gateway._answer = answer
    with pytest.raises(nexus_driver.GatewayStuck):
        _driver(gateway).run(task, 1, tmp_path / "run", timeout_seconds=5)
    (row,) = list(read_jsonl(tmp_path / "run" / "rows.jsonl"))
    # PREREG §3.3 / v0.9.2: a stuck Gateway is INFRA even after acceptance (both arms re-run).
    assert row["infra"] is True and row["gateway_stuck"] == "PENDING_HUMAN_APPROVAL"
    assert blind.exclusion_reason(row) == ("SYMMETRIC_INFRA", "GATEWAY_STUCK")


@needs_sandbox
def test_bare_claude_arm_runs_through_the_nexus_adapter(manifest, tmp_path, monkeypatch):
    from scripts.bench.measure_2721.fake_claude import write_fake_claude
    from scripts.bench.measure_2721.providers import ClaudeProvider, claude_identity

    (task,) = arms.load_manifest(manifest)
    fake = write_fake_claude(tmp_path / "bin" / "claude", "edit")
    token = tmp_path / "anthropic.env"
    fake_key = "-".join(("sk", "ant", "test", "NOT", "A", "REAL", "KEY", "000000000000"))
    token.write_text(f"ANTHROPIC_API_KEY={fake_key}\n")
    token.chmod(0o600)
    monkeypatch.setenv("NEXUS_MEASUREMENT_READ_ROOTS", str(tmp_path))
    provider = ClaudeProvider(str(fake), tmp_path / "run" / "traces", str(token),
                              identity=claude_identity(str(fake), str(token)))
    (task_root := Path(task["base_checkout"])).joinpath("README.md").exists()
    row = arms.run_bare(task, 1, tmp_path / "run", provider, timeout_seconds=60)
    # The fake CLI names only its own label, so the adapter never takes it for the
    # measured model: the run is MODEL_FAILED, not OK (33).
    assert row["outcome"] == "MODEL_FAILED", row
    assert row["claude_version"].startswith("0.0.0") and row["models_seen"] == ["fake-edit"]
    assert row["served_models"] == []
    assert row["cache_read_input_tokens"] == 0 and row["cache_creation_input_tokens"] == 0
    assert row["seatbelt_sha256"] and row["proxy_denied"] == []
    assert row["account"]["auth"] == "api_key" and len(row["account"]["api_key_sha256_12"]) == 12
    trace = Path(row["diff_path"]).parent.parent / "traces"
    assert all(b"NOT-A-REAL-KEY" not in f.read_bytes() for f in trace.rglob("*") if f.is_file())
    assert "README.md" in row["changed_paths"]
    del task_root


# -- coordinator round 3: snapshot, state restore, leaks, watchdog, tamper ---------


def test_snapshot_is_accepted_only_for_the_current_attempt():
    good = {"attempt_id": "a1", "measurement_worktree_diff": "diff --git a/x b/x\n",
            "measurement_worktree_diff_attempt_id": "a1"}
    assert nexus_driver.measurement_snapshot(good)["present"] is True
    stale = dict(good, measurement_worktree_diff_attempt_id="a0")
    assert nexus_driver.measurement_snapshot(stale)["invalid_reason"] == "SNAPSHOT_ATTEMPT_MISMATCH"
    truncated = dict(good, measurement_worktree_diff_truncated=True)
    assert nexus_driver.measurement_snapshot(truncated)["invalid_reason"] == "SNAPSHOT_TRUNCATED"
    errored = {"attempt_id": "a1", "measurement_worktree_diff_error": "git_timeout",
               "measurement_worktree_diff_attempt_id": "a1"}
    assert nexus_driver.measurement_snapshot(errored)["invalid_reason"] == "SNAPSHOT_ERROR:git_timeout"
    import base64

    raw = b"diff --git a/b b/b\n+\xff\n"
    lossy = dict(good, measurement_worktree_diff="lossy text", measurement_worktree_diff_lossy=True,
                 measurement_worktree_diff_b64=base64.b64encode(raw).decode())
    snap = nexus_driver.measurement_snapshot(lossy)
    assert snap["present"] and snap["diff"].encode("utf-8", errors="surrogateescape") == raw
    assert nexus_driver.measurement_snapshot({"attempt_id": "a1"})["present"] is False


def test_state_root_is_restored_and_verified(tmp_path):
    snap = tmp_path / "snap"
    (snap / ".nexus" / "memory").mkdir(parents=True)
    (snap / ".nexus" / "memory" / "m.json").write_text("{}")
    state = tmp_path / "state"
    (state / ".nexus").mkdir(parents=True)
    (state / ".nexus" / "learned.json").write_text("leftover from a previous row")
    (state / "gateway.lock").write_text("held")
    result = nexus_driver.restore_state_root(state, snap)
    assert result["ok"] and not (state / ".nexus" / "learned.json").exists()
    assert (state / "gateway.lock").exists()  # lock files are left alone and not hashed
    assert nexus_driver.dir_sha256(state) == nexus_driver.dir_sha256(snap)


def test_new_candidate_refs_stash_or_worktrees_are_leaks(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "f").write_text("x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "c")
    before = nexus_driver.leak_surfaces(repo)
    head = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "update-ref", "refs/nexus-candidates/other-task/1", head)
    _git(repo, "update-ref", "refs/nexus-candidates/own-task/1", head)
    leaks = nexus_driver.new_leaks(before, nexus_driver.leak_surfaces(repo), "own-task")
    assert list(leaks) == ["candidate_refs"] and "other-task" in leaks["candidate_refs"][0]


def test_watchdog_files_and_infra_events(manifest, tmp_path):
    from scripts.bench.measure_2721 import watchdog

    (task,) = arms.load_manifest(manifest)
    run = tmp_path / "run"
    row = arms.run_bare(task, 1, run, FakeProvider(), timeout_seconds=5)
    current = json.loads((run / "run" / "current_row.json").read_text())
    assert current["row_id"] == row["run_id"] and current["snapshot_taken"] is True
    assert (run / "run" / "rows_done").read_text().strip() == "1"
    (run / "run" / "infra_events.jsonl").write_text(json.dumps({"row_id": "next-row", "reason": "oom"}) + "\n")
    assert watchdog.infra_event_for(run, "next-row")["reason"] == "oom"
    assert watchdog.infra_event_for(run, row["run_id"]) is None


def test_bare_git_metadata_tamper_skips_capture(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)

    def tamper(workdir: Path, _prompt: str) -> None:
        _edit(workdir, _prompt)
        controller = Path(_git(workdir, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
        (controller / "config").write_text((controller / "config").read_text() + "[core]\n\tfsmonitor = evil\n")

    row = arms.run_bare(task, 1, tmp_path / "run", FakeProvider(edit=tamper), timeout_seconds=5)
    assert row["outcome"] == "TAMPERED" and arms.FLAG_GIT_TAMPERED in row["flags"] and row["empty"]


def test_bare_target_is_a_p1_shaped_worktree(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    controller, target = arms.bare_worktree(task, tmp_path / "w", "rid")
    assert (target / ".git").is_file()
    assert _git(target, "rev-parse", "HEAD").strip() == task["base_commit"]
    assert _git(controller, "for-each-ref").strip() == ""


def test_served_model_flag_and_diff_redaction(tmp_path):
    assert arms.served_model_flag(["claude-haiku-5-5"]) is None
    assert arms.served_model_flag(["claude-haiku-5-5", "claude-x"]) == arms.FLAG_SERVED_MODEL_MISMATCH
    assert arms.served_model_flag([]) == arms.FLAG_SERVED_MODEL_MISMATCH
    shaped = "-".join(("sk", "ant", "api03", "SOMETHINGLONGENOUGH1234"))
    diff = f"diff --git a/e b/e\n+KEY={shaped}\n"
    cleaned, redacted = arms.redact_diff(diff)
    assert redacted and shaped not in cleaned


def test_driver_uses_a_fresh_controller_under_the_targets_root(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    gateway = FakeGateway()
    client = nexus_driver.GatewayClient("http://127.0.0.1:18766", "tok-123", transport=gateway)
    driver = nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s",
                                         sleep=lambda _s: None, targets_root=tmp_path / "targets")
    driver.run(task, 1, tmp_path / "run", timeout_seconds=5)
    worker = next(c for c in gateway.calls if c["tool"] == "nexus_worker_candidate")["arguments"]
    repo_root = Path(worker["external_target"]["repo_root"])
    assert repo_root.parent.parent == (tmp_path / "targets").resolve()
    assert repo_root.parent.name.startswith(f"{task['task_id']}-r1-")


def test_driver_refuses_nexus_new_tasks(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    gateway = FakeGateway()
    with pytest.raises(ValueError, match="NEXUS_NEW_TASKS_NOT_MEASURED"):
        _driver(gateway).run(dict(task, repo="James3014/Nexus-new"), 1, tmp_path / "run", timeout_seconds=5)
    assert gateway.calls == []


def test_nexus_row_without_a_snapshot_is_void(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    gateway = FakeGateway()
    original = gateway._answer

    def answer(name, args):
        payload = original(name, args)
        for key in ("measurement_worktree_diff", "measurement_worktree_diff_attempt_id"):
            payload.pop(key, None)
        return payload

    gateway._answer = answer
    row = _driver(gateway).run(task, 1, tmp_path / "run", timeout_seconds=5)
    assert row["infra"] is False and row["void_reason"] == "SNAPSHOT_MISSING"  # amendment 10: not solved


def test_cli_timeout_mismatch_makes_the_bare_row_infra(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    provider = FakeProvider(extra={"cli_timeout_seconds": 123.0})
    row = arms.run_bare(task, 1, tmp_path / "run", provider, timeout_seconds=900)
    assert row["infra"] is True and "CLI_TIMEOUT_MISMATCH" in row["flags"]
    assert arms.expected_cli_timeout(900) == 870


def test_portable_rows_are_written_for_every_row(manifest, tmp_path):
    from scripts.bench.measure_2721.portable import PORTABLE_ROW_SCHEMA

    (task,) = arms.load_manifest(manifest)
    run = tmp_path / "run"
    arms.run_bare(task, 1, run, FakeProvider(), timeout_seconds=5)
    _driver(FakeGateway()).run(task, 1, run, timeout_seconds=5)
    rows = list(read_jsonl(run / "rows.portable.jsonl"))
    assert [r["arm"] for r in rows] == ["BARE", "NEXUS"] and all(r["schema"] == PORTABLE_ROW_SCHEMA for r in rows)
    assert set(rows[0]) >= {"task_id", "arm", "attempt_id", "candidate_commit", "outcome", "cost_tokens",
                            "wall_seconds", "verdict"}



def test_a_row_without_a_usable_venv_never_reaches_the_gateway(manifest, tmp_path, monkeypatch):
    (task,) = arms.load_manifest(manifest)
    monkeypatch.setenv("NEXUS_MEASUREMENT_READ_ROOTS", str(tmp_path / "elsewhere"))
    gateway = FakeGateway()
    row = _driver(gateway).run(task, 1, tmp_path / "run", timeout_seconds=5)
    assert row["infra"] is True and row["void_reason"] == "VENV_OUTSIDE_READ_ROOTS" and gateway.calls == []
    assert arms.venv_problem(dict(task, venv=None)) == "VENV_MISSING"
    monkeypatch.setenv("NEXUS_MEASUREMENT_READ_ROOTS", str(Path(task["venv"]).parent))
    assert arms.venv_problem(task) is None
    assert arms.venv_problem(task, "/other/venv", check_observed=True) == "VENV_MISMATCH"
    assert arms.venv_problem(task, os.path.realpath(task["venv"]), check_observed=True) is None


def test_spend_ledger_stops_before_the_cap(tmp_path):
    from scripts.bench.measure_2721.budget import BudgetExhausted, SpendLedger

    ledger = SpendLedger(tmp_path / "spend.json", cap_usd=1.0, max_row_usd=0.5)
    ledger.finish_row(ledger.begin_row(), 0.3)
    ledger.finish_row(ledger.begin_row(), 0.4)  # 0.3 + max(0.3, 0.5) <= 1.0
    with pytest.raises(BudgetExhausted):
        ledger.begin_row()  # 0.7 + 0.5 > 1.0
    assert SpendLedger(tmp_path / "spend.json", 1.0, 0.5).state()["rows"] == 2


def test_spend_ledger_reserves_stores_the_cap_and_estimates_unknown_cost(tmp_path):
    from scripts.bench.measure_2721.budget import BudgetConfigError, BudgetExhausted, SpendLedger

    path = tmp_path / "spend.json"
    ledger = SpendLedger(path, cap_usd=1.2, max_row_usd=0.5)
    first = ledger.begin_row()
    second = ledger.begin_row()  # 0 + 0.5 reserved + 0.5 <= 1.2
    with pytest.raises(BudgetExhausted):
        ledger.begin_row()  # in-flight reservations count (parallel arms, review L1)
    # A killed row (cost never reported) is charged the per-attempt ceiling (review H1).
    assert ledger.finish_row(first, None) == {"charged_usd": 0.5, "estimated": True}
    # One ceiling per unknown attempt (review H-a).
    assert ledger.finish_row(second, 0.1, unknown_attempts=2, estimate_usd=0.2)["charged_usd"] == pytest.approx(1.1)
    state = ledger.state()
    assert state["spent_usd"] == pytest.approx(1.6) and state["estimated_rows"] == 2 and state["cap_usd"] == 1.2
    assert state["worst_row_usd"] == pytest.approx(1.1)  # estimated rows teach the reservation too (H-b)
    with pytest.raises(BudgetConfigError):
        SpendLedger(path, cap_usd=60.0, max_row_usd=0.5)  # one shared ledger, one cap (review H3)
    with pytest.raises(BudgetConfigError):
        SpendLedger(path, cap_usd=1.2, max_row_usd=3.0)
    big = SpendLedger(tmp_path / "big.json", cap_usd=60.0, max_row_usd=0.5)
    # A usage-priced estimate above the ceiling wins (review H-b).
    assert big.finish_row(big.begin_row(), None, estimate_usd=2.0)["charged_usd"] == pytest.approx(2.0)
    default = SpendLedger(tmp_path / "default.json")
    assert default.finish_row(default.begin_row(), None)["charged_usd"] == pytest.approx(3.0)


def test_usage_priced_estimate_follows_haiku_rates(tmp_path):
    from scripts.bench.measure_2721.providers import estimate_stream_usd, estimate_usage_usd

    assert estimate_usage_usd({"input_tokens": 1_000_000}) == pytest.approx(0.50)  # > 100K prompt: long rate
    assert estimate_usage_usd({"input_tokens": 50_000, "output_tokens": 1_000}) == pytest.approx(0.0055)
    assert estimate_usage_usd({"input_tokens": 10, "cache_read_input_tokens": 200_000,
                               "output_tokens": 0}) == pytest.approx((10 * 0.5 + 200_000 * 0.05) / 1e6)
    assert estimate_usage_usd({"cache_creation_input_tokens": 80_000}) == pytest.approx(80_000 * 0.125 / 1e6)
    stream = tmp_path / "s.stream.jsonl"
    usage = {"input_tokens": 1000, "output_tokens": 1000}
    stream.write_text("".join(json.dumps(e) + "\n" for e in (
        {"type": "assistant", "message": {"id": "m1", "usage": usage}},
        {"type": "assistant", "message": {"id": "m1", "usage": usage}},  # same message, counted once
        {"type": "assistant", "message": {"id": "m2", "usage": usage}},
    )))
    assert estimate_stream_usd(stream) == pytest.approx(2 * estimate_usage_usd(usage))
    assert estimate_stream_usd(tmp_path / "missing") == 0.0


def test_bare_row_is_charged_even_when_the_run_fails(manifest, tmp_path):
    from scripts.bench.measure_2721.budget import SpendLedger

    (task,) = arms.load_manifest(manifest)
    ledger = SpendLedger(tmp_path / "spend.json", cap_usd=60.0)

    def boom(_workdir: Path, _prompt: str) -> None:
        raise RuntimeError("killed")

    with pytest.raises(RuntimeError):
        arms.run_bare(task, 1, tmp_path / "run", FakeProvider(edit=boom), timeout_seconds=5, ledger=ledger)
    state = ledger.state()
    assert state["rows"] == 1 and state["spent_usd"] == pytest.approx(3.0) and state["reservations"] == {}
    arms.run_bare(task, 2, tmp_path / "run", FakeProvider(extra={"total_cost_usd": 0.02}), timeout_seconds=5,
                  ledger=ledger)
    assert ledger.state()["spent_usd"] == pytest.approx(3.02)


class _StubClaude:
    """Stands in for ClaudeProvider (no CLI needed) in the venv-check tests."""

    name = "claude"
    key_file = None

    def __init__(self, result):
        self.result = result

    def run(self, **_kw):
        return self.result()


def test_bare_claude_row_checks_the_venv_before_spending(manifest, tmp_path, monkeypatch):
    from scripts.bench.measure_2721.budget import SpendLedger

    (task,) = arms.load_manifest(manifest)
    monkeypatch.setenv("NEXUS_MEASUREMENT_READ_ROOTS", str(tmp_path / "elsewhere"))
    monkeypatch.setattr(arms, "_claude_provider_type", lambda: _StubClaude)
    provider = _StubClaude(lambda: pytest.fail("provider must not run without a usable venv"))
    ledger = SpendLedger(tmp_path / "spend.json")
    row = arms.run_bare(task, 1, tmp_path / "run", provider, timeout_seconds=5, ledger=ledger)
    assert row["infra"] is True and row["void_reason"] == "VENV_OUTSIDE_READ_ROOTS"
    assert ledger.state()["rows"] == 0
    # The void row is in the portable rows too, so every arm has the same row count (review M-a).
    assert [r["task_id"] for r in read_jsonl(tmp_path / "run" / "rows.portable.jsonl")] == [task["task_id"]]


def test_bare_claude_row_with_another_venv_after_the_run_is_infra(manifest, tmp_path, monkeypatch):
    from scripts.bench.measure_2721.providers import ProviderResult

    (task,) = arms.load_manifest(manifest)
    monkeypatch.setattr(arms, "_claude_provider_type", lambda: _StubClaude)
    provider = _StubClaude(lambda: ProviderResult(
        status="OK", provider="claude", model="claude-haiku-5-5",
        extra={"venv": "/other/venv", "cli_timeout_seconds": arms.expected_cli_timeout(5),
               "served_models": ["claude-haiku-5-5"], "total_cost_usd": 0.01}))
    row = arms.run_bare(task, 1, tmp_path / "run", provider, timeout_seconds=5)
    assert row["infra"] is True and row["venv_problem"] == "VENV_MISMATCH" and arms.FLAG_VENV in row["flags"]


def _trace(trace_dir: Path, gw_task: str, name: str, *, cost, venv: str, limit: float, output: int,
           timed_out: bool = False, infra=None, tools: int = 1, served: bool = True) -> None:
    base = trace_dir / gw_task
    base.mkdir(parents=True, exist_ok=True)
    content = [{"type": "tool_use", "name": "Edit", "input": {"file_path": "x"}} for _ in range(tools)]
    events = [{"type": "assistant", "message": {"model": "claude-haiku-5-5", "content": content}}] if served else []
    if cost is not None:
        events.append({"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": cost,
                       "num_turns": 1, "usage": {"input_tokens": 1, "output_tokens": output}})
    (base / f"{name}.stream.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    (base / f"{name}.run.json").write_text(json.dumps({"cli_timeout_seconds": limit, "venv": venv,
                                                       "timed_out": timed_out, "infra": infra}))


def _tracing_driver(gateway: FakeGateway, trace_dir: Path, attempts) -> nexus_driver.NexusArmDriver:
    original = gateway._answer

    def answer(name, args):
        if name == "nexus_worker_candidate":
            for index, attempt in enumerate(attempts):
                _trace(trace_dir, args["task_id"], f"{index:02d}{'a' * 62}", **attempt)
        return original(name, args)

    gateway._answer = answer
    client = nexus_driver.GatewayClient("http://127.0.0.1:18766", "tok-123", transport=gateway)
    return nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s",
                                       sleep=lambda _s: None, trace_dir=trace_dir)


def test_nexus_row_bills_every_attempt_and_checks_each(manifest, tmp_path):
    from scripts.bench.measure_2721.budget import SpendLedger

    (task,) = arms.load_manifest(manifest)
    venv = os.path.realpath(task["venv"])
    limit = arms.expected_cli_timeout(5)
    ledger = SpendLedger(tmp_path / "spend.json", max_row_usd=0.5)
    driver = _tracing_driver(FakeGateway(), tmp_path / "traces", [
        dict(cost=0.03, venv=venv, limit=limit, output=10),
        dict(cost=0.02, venv=venv, limit=limit, output=5),
    ])
    row = driver.run(task, 1, tmp_path / "run", timeout_seconds=5, ledger=ledger)
    assert row["claude_attempts"] == 2 and row["total_cost_usd"] == pytest.approx(0.05)
    assert row["output_tokens"] == 15 and row["outcome"] == "OK", row
    assert ledger.state()["spent_usd"] == pytest.approx(0.05)
    # A killed attempt (no result event) is estimated; another venv voids the row.
    ledger2 = SpendLedger(tmp_path / "spend2.json", max_row_usd=0.5)
    driver = _tracing_driver(FakeGateway(), tmp_path / "traces2", [
        dict(cost=0.03, venv=venv, limit=limit, output=10),
        dict(cost=None, venv="/other/venv", limit=limit, output=0),
    ])
    row = driver.run(task, 2, tmp_path / "run", timeout_seconds=5, ledger=ledger2)
    assert row["infra"] is True and row["void_reason"] == "VENV_MISMATCH" and row["cost_unknown_attempts"] == 1
    assert ledger2.state()["spent_usd"] == pytest.approx(0.53) and ledger2.state()["estimated_rows"] == 1


class _ProbeGateway(FakeGateway):
    """Asks for one model probe before accepting the worker."""

    def _is_error(self, name: str) -> bool:
        return name == "nexus_worker_candidate" and not any(c["tool"] == "nexus_model_probe" for c in self.calls)

    def _answer(self, name, args):
        if name == "nexus_worker_candidate" and self._is_error(name):
            return {"error": "MODEL_PROBE_REQUIRED"}
        if name == "nexus_model_probe_result":
            return {"status": "VERSION_VERIFIED", "probe_usage": {"output_tokens": 1_000_000}}
        return super()._answer(name, args)


def test_a_model_probe_the_driver_triggers_is_charged(manifest, tmp_path):
    from scripts.bench.measure_2721.budget import SpendLedger

    (task,) = arms.load_manifest(manifest)
    venv = os.path.realpath(task["venv"])
    driver = _tracing_driver(_ProbeGateway(), tmp_path / "traces",
                             [dict(cost=0.01, venv=venv, limit=arms.expected_cli_timeout(5), output=1)])
    ledger = SpendLedger(tmp_path / "spend.json")
    driver.run(task, 1, tmp_path / "run", timeout_seconds=5, ledger=ledger)
    assert ledger.state()["spent_usd"] == pytest.approx(0.51)  # 0.01 worker + 1M output tokens at $0.50


def test_nexus_row_without_a_trace_is_void(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    row = _tracing_driver(FakeGateway(), tmp_path / "traces", []).run(task, 1, tmp_path / "run", timeout_seconds=5)
    assert row["infra"] is False and row["void_reason"] == "TRACE_MISSING"  # amendment 10: not solved


def test_a_stuck_nexus_row_is_still_charged(manifest, tmp_path):
    from scripts.bench.measure_2721.budget import SpendLedger

    (task,) = arms.load_manifest(manifest)
    gateway = FakeGateway()
    venv = os.path.realpath(task["venv"])
    driver = _tracing_driver(gateway, tmp_path / "traces",
                             [dict(cost=0.04, venv=venv, limit=arms.expected_cli_timeout(5), output=1)])
    original = gateway._answer

    def answer(name, args):
        payload = original(name, args)
        if name == "nexus_task_status":
            payload["status"] = "PENDING_HUMAN_APPROVAL"
        return payload

    gateway._answer = answer
    ledger = SpendLedger(tmp_path / "spend.json")
    with pytest.raises(nexus_driver.GatewayStuck):
        driver.run(task, 1, tmp_path / "run", timeout_seconds=5, ledger=ledger)
    assert ledger.state()["spent_usd"] == pytest.approx(0.04) and ledger.state()["reservations"] == {}


def test_runners_require_one_shared_ledger_and_stop_with_75(manifest, tmp_path, capsys):
    from scripts.bench.measure_2721.budget import SpendLedger

    env_file = tmp_path / "gateway.env"
    env_file.write_text("NEXUS_MEASUREMENT_READ_ROOTS=/m/venvs\n")
    with pytest.raises(SystemExit):
        arms.main(["--manifest", str(manifest), "--run-root", str(tmp_path / "run"), "noop",
                   "--gateway-env", str(env_file)])
    with pytest.raises(SystemExit):  # --gateway-env is required for both arms (L2)
        arms.main(["--manifest", str(manifest), "--run-root", str(tmp_path / "run"), "noop",
                   "--spend-ledger", str(tmp_path / "x.json")])
    ledger = tmp_path / "spend.json"
    exhausted = SpendLedger(ledger, cap_usd=0.4)  # below one reservation
    del exhausted
    rc = arms.main(["bare", "--manifest", str(manifest), "--run-root", str(tmp_path / "run"),
                    "--provider", "fake", "--spend-ledger", str(ledger), "--budget-usd", "0.4",
                    "--gateway-env", str(env_file)])
    assert rc == 75 and "BUDGET_STOP" in capsys.readouterr().out


@needs_sandbox
@pytest.mark.parametrize("roots_from", ["process", "gateway_env"])
def test_venv_probe_runs_python_and_pytest_inside_the_sandbox(manifest, tmp_path, monkeypatch, roots_from):
    """8d witness item 3, zero-model: the task venv works under the adapter's sandbox.

    ``gateway_env``: READ_ROOTS only in the loaded Gateway env, never in the runner's
    os.environ -- the formal runner's case (35 gate 1, 2026-10-20: BARE was VENV_MISMATCH)."""
    import site
    import subprocess as sp
    import sys

    from scripts.bench.measure_2721 import gateway_env
    from scripts.bench.measure_2721.fake_claude import write_fake_claude
    from scripts.bench.measure_2721.providers import ClaudeProvider, claude_identity

    (task,) = arms.load_manifest(manifest)
    # A real venv (the fixture's /usr/bin/python3 link is an xcrun shim on macOS):
    # this interpreter's base install, plus this run's site-packages for pytest.
    venv = Path(os.path.realpath(task["venv"]))
    for child in venv.iterdir():
        child.unlink() if not child.is_dir() else None
    sp.run([sys.executable, "-m", "venv", "--without-pip", "--clear", str(venv)], check=True)
    site_dir = next(Path(p) for p in site.getsitepackages() if p.endswith("site-packages"))
    venv_site = next(venv.glob("lib/python*/site-packages"))
    import shutil

    # The task venv must be self-contained (only it is readable in the sandbox):
    # copy pytest and its runtime dependencies in.
    for name in ("pytest", "_pytest", "pluggy", "iniconfig", "packaging", "py.py", "pygments"):
        source = site_dir / name
        if source.is_dir():
            shutil.copytree(source, venv_site / name)
        elif source.is_file():
            shutil.copy(source, venv_site / name)
    base_prefix = Path(os.path.realpath(sys.base_prefix))
    roots = ":".join((str(venv.parent), str(base_prefix)))
    if roots_from == "process":
        monkeypatch.setenv("NEXUS_MEASUREMENT_READ_ROOTS", roots)
    else:
        monkeypatch.delenv("NEXUS_MEASUREMENT_READ_ROOTS", raising=False)
        env_file = tmp_path / "gateway.env"
        env_file.write_text(f"NEXUS_MEASUREMENT_READ_ROOTS={roots}\n")
        gateway_env.use_gateway_env(env_file)
        monkeypatch.setattr(gateway_env, "_LOADED", dict(gateway_env._LOADED))
    fake = write_fake_claude(tmp_path / "bin" / "claude", "venvprobe")
    key = tmp_path / "anthropic.env"
    key.write_text("ANTHROPIC_API_KEY=" + "-".join(("sk", "ant", "test", "NOTAREALKEY000000000000")) + "\n")
    key.chmod(0o600)
    provider = ClaudeProvider(str(fake), tmp_path / "run" / "traces", str(key),
                              identity=claude_identity(str(fake), str(key)))
    row = arms.run_bare(task, 1, tmp_path / "run", provider, timeout_seconds=900)
    assert row["venv"] == os.path.realpath(task["venv"]) and row["venv_problem"] is None, row
    trace = Path(row["provider"]["extra"]["trace_path"]).read_text().splitlines()
    probe = next(json.loads(line)["venv_probe"] for line in trace if '"venv_probe"' in line)
    assert probe["import_encodings"]["rc"] == 0, probe
    # The interpreter that ran is the task venv itself (review L2).
    assert probe["import_encodings"]["tail"].strip().splitlines()[-1] == str(venv), probe
    assert probe["pytest_collect"]["rc"] == 0, probe
    # The runner's own environment is left as it was.
    assert ("NEXUS_MEASUREMENT_READ_ROOTS" in os.environ) == (roots_from == "process")


# -- 35 smoke findings: Controller pin, cancel retry, Gateway env ----------------


def _measure_layout(tmp_path: Path) -> dict:
    """B1 layout: a measurement repo (main worktree ``src``, branch ``feature-x``),
    another linked worktree ``other``, and the Controller as a linked worktree."""
    measure = tmp_path / "measure"
    src = measure / "src"
    src.mkdir(parents=True)
    _git(src, "init", "-q", "-b", "main")
    (src / "tasks").mkdir()
    (src / "tasks" / "index.md").write_text("pin\n")
    _git(src, "add", "-A")
    _git(src, "commit", "-qm", "pin")
    pin = _git(src, "rev-parse", "HEAD").strip()
    _git(src, "branch", "feature-x")
    _git(src, "tag", "v1")
    _git(src, "worktree", "add", "-q", "-b", "other", str(measure / "other"), pin)
    _git(src, "worktree", "add", "-q", "-b", "ctl", str(measure / "controller"), pin)
    live = tmp_path / "live.env"
    live.write_text("export NEXUS_CANONICAL_SOURCE_ROOT=/nonexistent/live/controller\n")
    return {"measure": measure, "src": src, "other": measure / "other", "controller": measure / "controller",
            "pin": pin, "live": [live]}


class _CardCommitGateway(FakeGateway):
    """Commits a Task Card to the Controller like P1 does, checks expected_head, and
    leaves measurement refs, a non-measurement branch, a tag, a new worktree and
    untracked files behind."""

    def __init__(self, repo: Path, **kw):
        super().__init__(**kw)
        self.repo = repo
        self.expected: list[str] = []

    def _answer(self, name, args):
        if name == "nexus_task_card_commit":
            self.expected.append(args["expected_head"])
            if args["expected_head"] != _git(self.repo, "rev-parse", "HEAD").strip():
                return {"status": "BLOCKED", "error": "TASK_CARD_COMMIT_HEAD_MISMATCH"}
            task = args["task_id"]
            (self.repo / "tasks" / f"{task}.md").write_text("card\n")
            _git(self.repo, "add", "-A")
            _git(self.repo, "commit", "-qm", f"card {task}")
            _git(self.repo, "update-ref", f"refs/nexus-candidates/{task}", "HEAD")
            _git(self.repo, "update-ref", f"refs/heads/nexus/task/{task}", "HEAD")
            _git(self.repo, "branch", f"keep-{task}"[:60])  # not a measurement ref: stays
            _git(self.repo, "update-ref", "refs/stash", "HEAD")
            _git(self.repo, "worktree", "add", "-q", "--detach", str(self.repo.parent / f"wt-{task}"), "HEAD")
            (self.repo / "scratch.tmp").write_text("left behind\n")
            (self.repo / ".gitignore").write_text("ignored/\n")
            (self.repo / "ignored").mkdir(exist_ok=True)
            (self.repo / "ignored" / "x").write_text("x\n")
        return super()._answer(name, args)


def _controller_driver(gateway, layout, **kw) -> nexus_driver.NexusArmDriver:
    client = nexus_driver.GatewayClient("http://127.0.0.1:18766", "tok-123", transport=gateway)
    return nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s", sleep=lambda _s: None,
                                       controller_repo=layout["controller"], measurement_root=layout["measure"],
                                       live_configs=layout["live"], **{"controller_pin": layout["pin"], **kw})


def test_controller_reset_touches_only_the_controller_and_measurement_refs(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    layout = _measure_layout(tmp_path)
    repo, pin = layout["controller"], layout["pin"]
    gateway = _CardCommitGateway(repo)
    driver = _controller_driver(gateway, layout)
    rows = [driver.run(task, repeat, tmp_path / "run", timeout_seconds=5) for repeat in (1, 2)]
    assert gateway.expected == [pin, pin]  # read from the Controller itself, not /health
    assert all(r["controller_reset"]["ok"] and r["outcome"] == "OK" for r in rows), rows
    # r2 inherits nothing from r1, and what r1 left is flagged on r2.
    assert "CONTROLLER_LEFTOVERS" not in (rows[0].get("flags") or [])
    assert "CONTROLLER_LEFTOVERS" in rows[1]["flags"]
    left = rows[1]["controller_leftovers"]
    assert any(r.startswith("refs/nexus-candidates/") for r in left) and "refs/stash" in left
    assert any(r.startswith("refs/heads/nexus/task/") for r in left) and any(r.startswith("worktree ") for r in left)
    driver.reset_controller()
    refs = _git(layout["src"], "for-each-ref", "--format=%(refname)").split()
    # B1: the repository's other branches, tags and worktrees survive.
    assert {"refs/heads/main", "refs/heads/feature-x", "refs/heads/other", "refs/heads/ctl", "refs/tags/v1"} <= set(refs)
    assert sum(r.startswith("refs/heads/keep-") for r in refs) == 2
    assert not [r for r in refs if r.startswith(("refs/heads/nexus/task/", "refs/nexus-candidates/", "refs/stash"))]
    worktrees = _git(layout["src"], "worktree", "list", "--porcelain")
    assert str(os.path.realpath(layout["other"])) in worktrees and layout["other"].is_dir()
    assert "wt-" not in worktrees
    assert _git(layout["src"], "rev-parse", "HEAD").strip() == pin  # main worktree untouched
    assert _git(repo, "status", "--porcelain", "--untracked-files=all", "--ignored").strip() == ""
    assert _git(repo, "rev-parse", "HEAD").strip() == pin


def test_controller_reset_failure_voids_the_row(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    layout = _measure_layout(tmp_path)
    gateway = FakeGateway()
    driver = _controller_driver(gateway, layout, controller_pin="0" * 40)
    row = driver.run(task, 1, tmp_path / "run", timeout_seconds=5)
    assert row["infra"] is True and row["void_reason"] == "CONTROLLER_RESET_MISMATCH" and gateway.calls == []


def test_controller_guard_rules(tmp_path, monkeypatch):
    from scripts.bench.measure_2721 import controller_guard as cg

    home = tmp_path / "home"
    (home / "workspace").mkdir(parents=True)
    (home / "Workspace").mkdir(parents=True, exist_ok=True)  # the same dir on a case-insensitive disk
    monkeypatch.setenv("HOME", str(home))
    # H1: roots that are too broad.
    for broad in ("/", home, home / "workspace", home / "Workspace", tmp_path):
        with pytest.raises(cg.ControllerGuardError, match="TOO_BROAD"):
            cg.check_measurement_root(broad)
    assert cg.check_measurement_root(home / "Workspace" / "nexus-measure-2721") == Path(
        os.path.realpath(home / "Workspace" / "nexus-measure-2721"))
    # M2: the given roots must nest; the outermost wins.
    measure = home / "Workspace" / "m"
    (measure / "targets").mkdir(parents=True)
    assert cg.measurement_root({"a": measure, "b": measure / "targets", "c": None}) == Path(os.path.realpath(measure))
    (home / "Workspace" / "n").mkdir()
    with pytest.raises(cg.ControllerGuardError, match="DISAGREE"):
        cg.measurement_root({"a": measure, "b": home / "Workspace" / "n"})
    # B1: a linked worktree of a main clone is refused even when placed under the root.
    main = home / "workspace" / "Nexus-new"
    main.mkdir()
    _git(main, "init", "-q", "-b", "main")
    (main / "f").write_text("x\n")
    _git(main, "add", "-A")
    _git(main, "commit", "-qm", "c")
    _git(main, "worktree", "add", "-q", "-b", "ctl", str(measure / "ctl"), "HEAD")
    live = tmp_path / "live.env"
    live.write_text("NEXUS_CANONICAL_SOURCE_ROOT=/nonexistent/live\n")
    with pytest.raises(cg.ControllerGuardError, match="IN_MAIN_CLONE"):
        cg.guard_controller(measure / "ctl", measure, cg.live_locations([live]))
    with pytest.raises(cg.ControllerGuardError, match="IN_MAIN_CLONE"):
        cg.guard_controller(main, main, [])
    # A linked worktree of a repository outside the root: its common dir is outside.
    outside = tmp_path / "elsewhere" / "repo"
    outside.mkdir(parents=True)
    _git(outside, "init", "-q", "-b", "main")
    (outside / "f").write_text("x\n")
    _git(outside, "add", "-A")
    _git(outside, "commit", "-qm", "c")
    _git(outside, "worktree", "add", "-q", "-b", "ctl", str(measure / "ctl2"), "HEAD")
    with pytest.raises(cg.ControllerGuardError, match="COMMON_DIR_OUTSIDE"):
        cg.guard_controller(measure / "ctl2", measure, [])
    # Paths compare case-insensitively (macOS realpath keeps the case given).
    assert cg.same_path(str(measure).swapcase(), measure)
    assert cg.is_within(measure / "targets", str(measure).swapcase())


def test_live_configuration_is_required_and_blocks_overlaps(tmp_path):
    import plistlib

    from scripts.bench.measure_2721 import controller_guard as cg

    with pytest.raises(cg.ControllerGuardError, match="LIVE_CONFIG_UNREADABLE"):
        cg.live_locations([tmp_path / "missing.plist"])
    layout = _measure_layout(tmp_path)
    plist = tmp_path / "com.nexus.mcp.gateway.direct.plist"
    plist.write_bytes(plistlib.dumps({"WorkingDirectory": "/x/deployments/a1", "ProgramArguments": [
        "/bin/zsh", "-c", f'cd "{layout["controller"]}" ; exec python -m gateway']}))
    live = cg.live_locations([plist])
    assert Path("/x/deployments/a1") in live and Path(str(layout["controller"])) in live
    with pytest.raises(cg.ControllerGuardError, match="OVERLAPS_LIVE"):
        cg.guard_controller(layout["controller"], layout["measure"], live)
    client = nexus_driver.GatewayClient("http://127.0.0.1:18766", "t", transport=FakeGateway())
    with pytest.raises(cg.ControllerGuardError, match="LIVE_CONFIG_UNREADABLE"):
        nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s",
                                    controller_repo=layout["controller"], controller_pin=layout["pin"],
                                    measurement_root=layout["measure"], live_configs=[tmp_path / "none"])


class _FinishingGateway(FakeGateway):
    """Refuses cancel while the worker finishes; the task waits for approval meanwhile."""

    def __init__(self, refusals: int, **kw):
        super().__init__(**kw)
        self.refusals = refusals
        self.cancelled = False

    def _is_error(self, name: str) -> bool:
        if name == "nexus_task_cancel" and self.refusals > 0:
            return True
        return super()._is_error(name)

    def _answer(self, name, args):
        if name == "nexus_task_cancel":
            if self.refusals > 0:
                self.refusals -= 1
                return {"error": "CANDIDATE_REF_PROTECTED"}
            self.cancelled = True
        payload = super()._answer(name, args)
        if name == "nexus_task_status" and any(c["tool"] == "nexus_task_cancel" for c in self.calls):
            payload["status"] = "CANCELLED" if self.cancelled else "PENDING_HUMAN_APPROVAL"
        return payload


def test_refused_cancel_is_retried_with_backoff(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    gateway = _FinishingGateway(refusals=2)
    sleeps: list[float] = []
    client = nexus_driver.GatewayClient("http://127.0.0.1:18766", "tok-123", transport=gateway)
    driver = nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s", sleep=sleeps.append)
    row = driver.run(task, 1, tmp_path / "run", timeout_seconds=5)
    assert not row.get("gateway_stuck") and row["outcome"] == "OK", row
    assert [c["tool"] for c in gateway.calls].count("nexus_task_cancel") == 3
    assert sleeps[:2] == [10.0, 20.0]  # backoff grows between retries


def test_cancel_that_is_never_accepted_is_stuck_after_a_bounded_number_of_tries(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    gateway = _FinishingGateway(refusals=10_000)
    with pytest.raises(nexus_driver.GatewayStuck):
        _driver(gateway).run(task, 1, tmp_path / "run", timeout_seconds=5)
    assert [c["tool"] for c in gateway.calls].count("nexus_task_cancel") <= 13


def test_gateway_env_is_read_without_running_start_sh(tmp_path, monkeypatch):
    from scripts.bench.measure_2721 import gateway_env

    marker = tmp_path / "ran"
    start = tmp_path / "start.sh"
    start.write_text(
        "#!/bin/bash\nset -euo pipefail\nROOT=/m/nexus-measure-2721\n"
        "export NEXUS_MEASUREMENT_READ_ROOTS=\"${ROOT}/venvs:${ROOT}/py\"\n"
        f"touch {marker}\n"
        "export NEXUS_MEASUREMENT_CLAUDE_WORKER=1 NEXUS_MEASURE_DIR_SCOPE=1\n"
        "exec python -m gateway --port 18766\nexport AFTER_EXEC=1\n")
    start.write_text(start.read_text().replace(
        "set -euo pipefail\n", "set -euo pipefail\nexport PATH=/evil/bin GIT_DIR=/evil ANTHROPIC_API_KEY=nope\n"))
    monkeypatch.delenv("NEXUS_MEASUREMENT_READ_ROOTS", raising=False)
    before = dict(os.environ)
    names = gateway_env.use_gateway_env(start)
    env = gateway_env.measurement_env()
    assert dict(os.environ) == before  # the harness's own env (and its git) is untouched (M2)
    assert names == ["NEXUS_MEASUREMENT_CLAUDE_WORKER", "NEXUS_MEASUREMENT_READ_ROOTS", "NEXUS_MEASURE_DIR_SCOPE"]
    assert env["NEXUS_MEASUREMENT_READ_ROOTS"] == "/m/nexus-measure-2721/venvs:/m/nexus-measure-2721/py"
    assert "PATH" not in env and "GIT_DIR" not in env and "ANTHROPIC_API_KEY" not in env and not marker.exists()
    assert gateway_env.require_read_roots(env) == ["/m/nexus-measure-2721/venvs", "/m/nexus-measure-2721/py"]
    with pytest.raises(gateway_env.GatewayEnvError):
        gateway_env.require_read_roots({"NEXUS_MEASUREMENT_READ_ROOTS": ""})


def test_driver_refuses_to_start_without_read_roots(manifest, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("NEXUS_MEASUREMENT_READ_ROOTS", raising=False)
    monkeypatch.setenv("NEXUS_MEASUREMENT_CLAUDE_WORKER", "0")  # restored after the test
    env_file = tmp_path / "gateway.env"
    env_file.write_text("NEXUS_MEASUREMENT_CLAUDE_WORKER=1\n")
    token = tmp_path / "tok"
    token.write_text("NEXUS_MCP_GATEWAY_TOKEN=t\n")
    token.chmod(0o600)
    rc = nexus_driver.main(["--manifest", str(manifest), "--run-root", str(tmp_path / "run"),
                            "--gateway-url", "http://127.0.0.1:18766", "--token-file", str(token),
                            "--scope-id", "s", "--trace-dir", str(tmp_path / "t"),
                            "--spend-ledger", str(tmp_path / "spend.json"), "--gateway-env", str(env_file)])
    assert rc == 2 and "READ_ROOTS_EMPTY" in capsys.readouterr().out


def test_controller_repo_and_pin_go_together(tmp_path):
    client = nexus_driver.GatewayClient("http://127.0.0.1:18766", "t", transport=FakeGateway())
    with pytest.raises(ValueError, match="go together"):
        nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s", controller_repo=tmp_path)
    with pytest.raises(ValueError, match="go together"):
        nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s", controller_pin="a" * 40)
    with pytest.raises(nexus_driver.LiveGatewayRefused):
        nexus_driver.GatewayClient("http://127.0.0.1:8766", "t", transport=FakeGateway())


def test_rows_carry_the_read_roots_hash_and_arms_must_agree(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    run = tmp_path / "run"
    bare = arms.run_bare(task, 1, run, FakeProvider(), timeout_seconds=5)
    nexus = _driver(FakeGateway()).run(task, 1, run, timeout_seconds=5)
    assert bare["read_roots_sha256"] == nexus["read_roots_sha256"]
    tasks = {task["task_id"]: task}
    other = dict(nexus, read_roots_sha256="0" * 16)
    with pytest.raises(RuntimeError, match="READ_ROOTS_DIFFER_ACROSS_ARMS"):
        blind.blind([bare, other], tmp_path / "blind", tmp_path / "map.json", tasks)


@pytest.mark.parametrize("value", ["${ROOT:-/m}/venvs", "$(pwd)/venvs", "`pwd`/venvs"])
def test_gateway_env_fails_closed_on_unexpanded_values(tmp_path, value):
    from scripts.bench.measure_2721 import gateway_env

    env_file = tmp_path / "x.env"
    env_file.write_text(f"NEXUS_MEASUREMENT_READ_ROOTS='{value}'\n")
    with pytest.raises(gateway_env.GatewayEnvError, match="unexpanded"):
        gateway_env.use_gateway_env(env_file)
    assert gateway_env.measurement_env().get("NEXUS_MEASUREMENT_READ_ROOTS") != value


# -- round 6: state phases, duplicates, submitted, labels, schedule, preflight ----


def _state_driver(gateway: FakeGateway, tmp_path: Path, phase: str, **kw) -> nexus_driver.NexusArmDriver:
    state_root = tmp_path / "state"
    snapshot = tmp_path / "snapshot"
    (snapshot / "learning").mkdir(parents=True)
    (snapshot / "learning" / "episodes.jsonl").write_text("phase start\n")
    state_root.mkdir()
    client = nexus_driver.GatewayClient("http://127.0.0.1:18766", "tok-123", transport=gateway)
    return nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s", sleep=lambda _s: None,
                                       state_root=state_root, state_snapshot=snapshot,
                                       state_dir=state_root / "tasks", learning_phase=phase, **kw)


class _LearningGateway(FakeGateway):
    """Writes learning state (and the probe cache) while the worker runs."""

    def __init__(self, state_root: Path, **kw):
        super().__init__(**kw)
        self.state_root = state_root

    def _answer(self, name, args):
        if name == "nexus_worker_candidate":
            (self.state_root / "learning" / "episodes.jsonl").write_text(f"learned from {args['task_id']}\n")
            probe = self.state_root / "assisted_provider_jobs" / "probe_evidence"
            probe.mkdir(parents=True, exist_ok=True)
            (probe / f"{args['task_id']}.json").write_text("{}")
        return super()._answer(name, args)


def test_lb_restores_every_row_keeps_the_probe_cache_and_detects_writes(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    gateway = _LearningGateway(tmp_path / "state")
    driver = _state_driver(gateway, tmp_path, "LB")
    rows = [driver.run(task, r, tmp_path / "run", timeout_seconds=5) for r in (1, 2)]
    assert all(r["state_restore"]["ok"] and r["state_restore_policy"] == "per_row" for r in rows)
    # Q2: a learning write in the read-only phase voids the row.
    # Amendment 10: after acceptance this is Nexus-side, so not infra but not solved.
    assert all(not r["infra"] and r["void_reason"] == "LB_STATE_CHANGED" for r in rows), rows
    probe = tmp_path / "state" / "assisted_provider_jobs" / "probe_evidence"
    assert len(list(probe.iterdir())) == 2  # never restored away


def test_la_restores_once_per_phase_and_m_every_row(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    driver = _state_driver(_LearningGateway(tmp_path / "state"), tmp_path, "LA")
    rows = [driver.run(task, r, tmp_path / "run", timeout_seconds=5) for r in (1, 2)]
    assert "state_restore" in rows[0] and "state_restore" not in rows[1]
    assert rows[1]["outcome"] == "OK" and (tmp_path / "state" / "learning" / "episodes.jsonl").read_text() \
        .startswith("learned from")
    assert nexus_driver.state_phase.restore_policy("M") == "per_row"


def test_state_is_restored_only_when_the_instance_is_quiet(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    gateway = FakeGateway()
    driver = _state_driver(gateway, tmp_path, "M")
    tasks_dir = tmp_path / "state" / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "other.json").write_text(json.dumps({"status": "IN_PROGRESS"}))
    row = driver.run(task, 1, tmp_path / "run", timeout_seconds=5)
    assert row["infra"] and row["void_reason"].startswith("STATE_RESTORE_BUSY:TASK_IN_FLIGHT") and not gateway.calls
    target = tmp_path / "left-target"
    target.mkdir()
    (tasks_dir / "other.json").write_text(json.dumps({"status": "CANCELLED", "lease": {"target_worktree": str(target)}}))
    assert nexus_driver.state_phase.quiescence_problem(tasks_dir).startswith("TARGET_NOT_CLEANED")


def test_invalid_state_records_refuse_the_driver(manifest, tmp_path, monkeypatch):
    states = tmp_path / "states"
    states.mkdir()
    (states / "t.json").write_text(json.dumps({"state_valid": False}))
    env_file = tmp_path / "g.env"
    env_file.write_text(f"NEXUS_MEASUREMENT_READ_ROOTS={os.path.realpath(tmp_path)}\n")
    token = tmp_path / "tok"
    token.write_text("NEXUS_MCP_GATEWAY_TOKEN=t\n")
    token.chmod(0o600)
    import io
    from contextlib import redirect_stdout

    out = io.StringIO()
    with redirect_stdout(out):
        rc = nexus_driver.main(["--manifest", str(manifest), "--run-root", str(tmp_path / "run"),
                                "--gateway-url", "http://127.0.0.1:18766", "--token-file", str(token),
                                "--scope-id", "s", "--trace-dir", str(tmp_path / "t"), "--state-dir", str(states),
                                "--spend-ledger", str(tmp_path / "spend.json"), "--gateway-env", str(env_file)])
    assert rc == 2 and "STATE_INVALID_RECORDS" in out.getvalue()


def test_router_log_outside_the_state_root_is_restored_every_row(tmp_path):
    from scripts.bench.measure_2721.state_phase import ExtraStateFiles

    root = tmp_path / "project"
    root.mkdir()
    files = ExtraStateFiles.router_logs([root])
    (root / "router_decisions.jsonl").write_text('{"decision": 1}\n')
    result = files.restore()
    assert result["ok"] and result["restored"] and not (root / "router_decisions.jsonl").exists()


def test_each_repeat_has_its_own_card_and_duplicates_are_infra(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    driver = _driver(FakeGateway())
    one, two = driver.card_args(task, "t-r1", 1), driver.card_args(task, "t-r2", 2)
    assert one["objective"] != two["objective"] and "repeat 2" in two["objective"]
    gateway = FakeGateway()
    original = gateway._answer

    def answer(name, args):
        if name == "nexus_worker_candidate":
            return {"status": "SUBMITTED", "duplicate": {"code": "DUPLICATE_LOGICAL_TASK", "existing_task_id": "x"}}
        return original(name, args)

    gateway._answer = answer
    row = _driver(gateway).run(task, 1, tmp_path / "run", timeout_seconds=5)
    assert row["infra"] and row["void_reason"] == "DUPLICATE_TASK" and row["submitted"] is True


def test_failures_before_submit_are_infra_and_after_submit_are_not_solved(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)

    class CommitFails(FakeGateway):
        def _is_error(self, name):
            return name == "nexus_task_card_commit"

        def _answer(self, name, args):
            if name == "nexus_task_card_commit":
                return {"error": "TASK_CARD_COMMIT_HEAD_MISMATCH"}
            return super()._answer(name, args)

    row = _driver(CommitFails()).run(task, 1, tmp_path / "run", timeout_seconds=5)
    assert row["infra"] and row["submitted"] is False
    assert row["void_reason"] == "PRE_SUBMIT_FAILURE:nexus_task_card_commit"
    row = _driver(FakeGateway(worker_error={"error": "WORKER_REFUSED_SCOPE"})).run(
        task, 2, tmp_path / "run", timeout_seconds=5)
    # Amendment 10: the Gateway refused the worker request -> infra, never a candidate.
    assert row["infra"] is True and row["worker_accepted"] is False and row["submitted"] is True
    assert row["void_reason"] == "WORKER_NOT_ACCEPTED:nexus_worker_candidate"
    assert blind.exclusion_reason(row)[0] == "NEXUS_NOT_ACCEPTED"


def test_a_hung_run_is_labelled_the_same_in_both_arms(manifest, tmp_path, monkeypatch):
    from scripts.bench.measure_2721.providers import ProviderResult

    (task,) = arms.load_manifest(manifest)
    venv = os.path.realpath(task["venv"])
    limit = arms.expected_cli_timeout(5)
    nexus = _tracing_driver(FakeGateway(), tmp_path / "traces", [
        dict(cost=None, venv=venv, limit=limit, output=0, timed_out=True, served=False)])
    nexus_row = nexus.run(task, 1, tmp_path / "run", timeout_seconds=5)
    monkeypatch.setattr(arms, "_claude_provider_type", lambda: _StubClaude)
    bare_row = arms.run_bare(task, 1, tmp_path / "run", _StubClaude(lambda: ProviderResult(
        status="TIMEOUT", provider="claude", model="claude-haiku-5-5", timed_out=True,
        extra={"venv": venv, "cli_timeout_seconds": limit, "served_models": []})), timeout_seconds=5)
    assert nexus_row["outcome"] == bare_row["outcome"] == "TIMEOUT", (nexus_row, bare_row)
    for row in (nexus_row, bare_row):
        assert arms.FLAG_SERVED_MODEL_MISMATCH not in row["flags"] and arms.FLAG_TIMEOUT in row["flags"]


def test_a_rate_limited_run_with_a_partial_diff_is_infra_in_both_arms(manifest, tmp_path, monkeypatch):
    from scripts.bench.measure_2721.providers import ProviderResult

    (task,) = arms.load_manifest(manifest)
    venv = os.path.realpath(task["venv"])
    limit = arms.expected_cli_timeout(5)
    gateway = FakeGateway()
    original = gateway._answer

    def answer(name, args):
        payload = original(name, args)
        if name in ("nexus_task_wait", "nexus_task_status"):
            payload["measurement_worktree_diff"] = "diff --git a/x.py b/x.py\n"
        return payload

    gateway._answer = answer
    nexus = _tracing_driver(gateway, tmp_path / "traces", [
        dict(cost=None, venv=venv, limit=limit, output=0, infra="rate_limited")])
    nexus_row = nexus.run(task, 1, tmp_path / "run", timeout_seconds=5)
    monkeypatch.setattr(arms, "_claude_provider_type", lambda: _StubClaude)
    bare_row = arms.run_bare(task, 1, tmp_path / "run", _StubClaude(lambda: ProviderResult(
        status="INFRA", provider="claude", model="claude-haiku-5-5", infra_reason="RATE_LIMITED",
        extra={"venv": venv, "cli_timeout_seconds": limit, "served_models": []})), timeout_seconds=5)
    assert nexus_row["infra"] and bare_row["infra"] and nexus_row["outcome"] == bare_row["outcome"] == "INFRA"


def test_a_diff_without_any_model_tool_call_is_a_non_model_solve(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    venv = os.path.realpath(task["venv"])
    gateway = FakeGateway()
    original = gateway._answer

    def answer(name, args):
        payload = original(name, args)
        if name in ("nexus_task_wait", "nexus_task_status"):
            payload["measurement_worktree_diff"] = "diff --git a/x.py b/x.py\n+fixed\n"
        return payload

    gateway._answer = answer
    driver = _tracing_driver(gateway, tmp_path / "traces", [
        dict(cost=0.01, venv=venv, limit=arms.expected_cli_timeout(5), output=1, tools=0)])
    row = driver.run(task, 1, tmp_path / "run", timeout_seconds=5)
    assert row["non_model_solve_path"] is True and arms.FLAG_NON_MODEL_SOLVE in row["flags"]
    assert blind.run_invalid_reason(row) == "NON_MODEL_SOLVE_PATH"
    assert arms.non_model_solve("diff", {"tool_call_count": 3}) is False
    assert arms.non_model_solve("diff", {}) is False  # no Claude run recorded


def test_schedule_interleaves_the_arms_with_a_recorded_seed(tmp_path):
    from scripts.bench.measure_2721 import runner

    ids = [f"t{i}" for i in range(6)]
    first = runner.build_schedule(ids, [1, 2])
    assert first == runner.build_schedule(ids, [1, 2])  # same seed, same order
    assert first != runner.build_schedule(ids, [1, 2], seed=1)
    assert len(first) == 36 and {e["arm"] for e in first} == set(runner.ARMS)
    assert [e["arm"] for e in first[:3]] != ["BARE", "NEXUS", "NOOP"] or \
        [e["arm"] for e in first[3:6]] != ["BARE", "NEXUS", "NOOP"]
    record = runner.write_schedule(tmp_path, first, runner.DEFAULT_SEED)
    saved = json.loads((tmp_path / "schedule.json").read_text())
    assert saved["seed"] == 20261020 and saved["order_sha256"] == record["order_sha256"]


def test_preflight_excludes_unfair_tasks_for_every_arm(manifest, tmp_path, bank):
    from scripts.bench.measure_2721 import preflight

    (task,) = arms.load_manifest(manifest)
    assert preflight.exclusion_reasons(task) == []
    assert preflight.exclusion_reasons(dict(task, venv=None)) == [preflight.REASON_NO_VENV]
    repo = tmp_path / "gitrules"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / ".gitattributes").write_text("*.bin filter=lfs diff=lfs merge=lfs -text\n")
    (repo / "a.txt").write_text("a\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "c")
    head = _git(repo, "rev-parse", "HEAD").strip()
    assert preflight.git_problems(repo, head) == [preflight.REASON_LFS]
    (repo / ".gitattributes").write_text("*.txt filter=crlf\n")
    (repo / ".gitmodules").write_text('[submodule "x"]\n\tpath = x\n\turl = ../x\n')
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "c2")
    head = _git(repo, "rev-parse", "HEAD").strip()
    assert preflight.git_problems(repo, head) == [preflight.REASON_FILTER, preflight.REASON_SUBMODULE]
    _git(repo, "config", "diff.pdf.textconv", "cat")
    (repo / ".gitattributes").write_text("")
    _git(repo, "rm", "-q", ".gitmodules")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "c3")
    head = _git(repo, "rev-parse", "HEAD").strip()
    assert preflight.git_problems(repo, head) == [preflight.REASON_FILTER]


def test_runners_write_the_same_preflight_and_skip_excluded_tasks(manifest, tmp_path):
    rows_path = tmp_path / "run"
    manifest_rows = [json.loads(line) for line in manifest.read_text().splitlines()]
    no_venv = tmp_path / "manifest-novenv.jsonl"
    no_venv.write_text(json.dumps(dict(manifest_rows[0], venv=None)) + "\n")
    env_file = tmp_path / "g.env"
    env_file.write_text("NEXUS_MEASUREMENT_READ_ROOTS=/m\n")
    rc = arms.main(["bare", "--manifest", str(no_venv), "--run-root", str(rows_path), "--provider", "fake",
                    "--spend-ledger", str(tmp_path / "spend.json"), "--gateway-env", str(env_file)])
    report = json.loads((rows_path / "preflight.json").read_text())
    assert rc == 0 and report["measured"] == [] and report["excluded"][0]["reasons"] == ["NO_TASK_VENV"]
    assert not (rows_path / "rows.jsonl").exists()


def test_the_measured_model_comes_from_the_adapter():
    from nexus.executors.claude_measurement_worker import CLAUDE_MEASUREMENT_MODEL

    assert arms.MEASUREMENT_MODEL == CLAUDE_MEASUREMENT_MODEL
    client = nexus_driver.GatewayClient("http://127.0.0.1:18766", "t", transport=FakeGateway())
    assert nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s").probe_model == \
        CLAUDE_MEASUREMENT_MODEL


def test_noop_rows_carry_the_fake_label_and_real_rows_the_measured_model(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    venv = os.path.realpath(task["venv"])
    limit = arms.expected_cli_timeout(5)

    def noop_driver(trace_dir, model):
        gateway = FakeGateway()
        original = gateway._answer

        def answer(name, args):
            if name == "nexus_worker_candidate":
                base = trace_dir / args["task_id"]
                base.mkdir(parents=True, exist_ok=True)
                events = [{"type": "system", "subtype": "init", "model": model},
                          {"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.0,
                           "num_turns": 1, "modelUsage": {model: {}}}]
                (base / f"{'b' * 64}.stream.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
                (base / f"{'b' * 64}.run.json").write_text(json.dumps({"cli_timeout_seconds": limit, "venv": venv}))
            return original(name, args)

        gateway._answer = answer
        client = nexus_driver.GatewayClient("http://127.0.0.1:18766", "tok-123", transport=gateway)
        return nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s", sleep=lambda _s: None,
                                           trace_dir=trace_dir, arm_label="NEXUS_NOOP")

    row = noop_driver(tmp_path / "t1", "fake-noop").run(task, 1, tmp_path / "run", timeout_seconds=5)
    # Read from the events only: modelUsage does not count as served.
    assert row["models_seen"] == ["fake-noop"] and row["served_models"] == []
    assert arms.FLAG_SERVED_MODEL_MISMATCH not in row["flags"], row
    row = noop_driver(tmp_path / "t2", "claude-haiku-5-5").run(task, 2, tmp_path / "run", timeout_seconds=5)
    assert arms.FLAG_SERVED_MODEL_MISMATCH in row["flags"]  # a NOOP row naming a real model
    # A real completed row must show exactly the measured model, never nothing.
    assert arms.outcome_flags("OK", []) == [arms.FLAG_SERVED_MODEL_MISMATCH]
    assert arms.outcome_flags("OK", ["claude-haiku-5-5"]) == []
    assert arms.fake_model_flag([]) == arms.FLAG_SERVED_MODEL_MISMATCH


# -- 33 review of 84ae047ba: M1 schedule, M2 quiescence, M3 L-A marker, state paths --


def test_schedule_is_block_randomized_and_balanced_for_the_default_seed(tmp_path):
    from scripts.bench.measure_2721 import runner

    ids = [f"t{i}" for i in range(12)]
    schedule = runner.build_schedule(ids, [1, 2, 3])
    assert schedule == runner.build_schedule(ids, [1, 2, 3])
    size = len(runner.ARMS)
    assert len(schedule) == 12 * 3 * size
    orders = set()
    for start in range(0, len(schedule), size):
        block = schedule[start : start + size]
        # One (task, repeat) per block, every arm exactly once, back to back.
        assert (
            len({(e["task_id"], e["repeat"]) for e in block}) == 1
            and len({e["block"] for e in block}) == 1
        )
        assert sorted(e["arm"] for e in block) == sorted(runner.ARMS)
        orders.add(tuple(e["arm"] for e in block))
    assert len(orders) > 1  # the arm order inside a block varies
    stats = runner.schedule_stats(schedule)
    means = stats["mean_slot"].values()
    assert max(means) - min(means) < size  # within one block length
    assert set(stats["first_third"].values()) == {12}
    record = runner.write_schedule(tmp_path, schedule, runner.DEFAULT_SEED)
    saved = json.loads((tmp_path / "schedule.json").read_text())
    assert saved["scheme"] == "block_randomized_v1" and saved["block_size"] == size
    assert saved["order_sha256"] == record["order_sha256"] and saved["stats"] == stats
    # A subset of arms keeps the block structure.
    two = runner.build_schedule(ids, [1], ["BARE", "NEXUS"])
    assert all(
        {two[i]["arm"], two[i + 1]["arm"]} == {"BARE", "NEXUS"} for i in range(0, len(two), 2)
    )


def test_single_arm_entrypoints_refuse_a_paid_run(manifest, tmp_path, capsys):
    import argparse

    from scripts.bench.measure_2721 import runner

    env_file = tmp_path / "g.env"
    env_file.write_text(f"NEXUS_MEASUREMENT_READ_ROOTS={os.path.realpath(tmp_path)}\n")
    rc = arms.main([
        "bare",
        "--manifest",
        str(manifest),
        "--run-root",
        str(tmp_path / "run-b"),
        "--provider",
        "claude",
        "--spend-ledger",
        str(tmp_path / "spend.json"),
        "--gateway-env",
        str(env_file),
    ])
    assert rc == 2 and runner.SINGLE_ARM_REFUSED in capsys.readouterr().out
    assert not (tmp_path / "run-b").exists()  # refused before anything ran
    token = tmp_path / "tok"
    token.write_text("NEXUS_MCP_GATEWAY_TOKEN=t\n")
    token.chmod(0o600)
    rc = nexus_driver.main([
        "--manifest",
        str(manifest),
        "--run-root",
        str(tmp_path / "run-n"),
        "--gateway-url",
        "http://127.0.0.1:18766",
        "--token-file",
        str(token),
        "--scope-id",
        "s",
        "--trace-dir",
        str(tmp_path / "t"),
        "--spend-ledger",
        str(tmp_path / "spend.json"),
        "--gateway-env",
        str(env_file),
    ])
    assert rc == 2 and runner.SINGLE_ARM_REFUSED in capsys.readouterr().out
    assert not (tmp_path / "run-n" / "rows.jsonl").exists()
    # The fake provider and the explicit debug flag still run (with a warning).
    assert runner.single_arm_refusal(argparse.Namespace(single_arm_debug=False), paid=False) is None
    assert runner.single_arm_refusal(argparse.Namespace(single_arm_debug=True), paid=True) is None
    assert "WARNING" in capsys.readouterr().err


def test_controller_is_not_reset_while_the_instance_is_busy(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    layout = _measure_layout(tmp_path)
    repo = layout["controller"]
    state_dir = tmp_path / "self-hosted"
    state_dir.mkdir()
    (state_dir / "previous.json").write_text(json.dumps({"status": "IN_PROGRESS"}))
    # What a live previous task has in the Controller: a commit and untracked work.
    (repo / "tasks" / "live.md").write_text("card\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "live card")
    head = _git(repo, "rev-parse", "HEAD").strip()
    (repo / "in-use.txt").write_text("worker output\n")
    gateway = FakeGateway()
    driver = _controller_driver(gateway, layout, state_dir=state_dir)  # no state restore configured
    row = driver.run(task, 1, tmp_path / "run", timeout_seconds=5)
    assert row["infra"] and row["void_reason"].startswith("INSTANCE_BUSY:TASK_IN_FLIGHT"), row
    assert row["controller_reset_skipped"] and "controller_reset" not in row and not gateway.calls
    assert row["submitted"] is False and row["worker_accepted"] is False
    assert (repo / "in-use.txt").read_text() == "worker output\n"
    assert _git(repo, "rev-parse", "HEAD").strip() == head != layout["pin"]
    # Once the previous task is terminal the reset runs.
    (state_dir / "previous.json").write_text(json.dumps({"status": "CANCELLED"}))
    row = driver.run(task, 2, tmp_path / "run", timeout_seconds=5)
    assert row["controller_reset"]["ok"] and not (repo / "in-use.txt").exists()
    assert _git(repo, "rev-parse", "HEAD").strip() == layout["pin"]


def test_la_phase_marker_survives_a_resume_and_refuses_other_snapshots(manifest, tmp_path):
    from scripts.bench.measure_2721 import state_phase

    (task,) = arms.load_manifest(manifest)
    run_root = tmp_path / "run"
    first = _state_driver(_LearningGateway(tmp_path / "state"), tmp_path, "LA")
    row = first.run(task, 1, run_root, timeout_seconds=5)
    marker = run_root / "state_phase_LA.restored.json"
    assert (
        row["state_restore"]["ok"] and row["state_phase_marker"] == marker.name and marker.is_file()
    )
    saved = json.loads(marker.read_text())
    assert saved["snapshot_sha256"] == {
        "state_root": state_phase.state_sha256(tmp_path / "snapshot")
    }
    assert saved["restored_at"]
    learned = (tmp_path / "state" / "learning" / "episodes.jsonl").read_text()
    assert learned.startswith("learned from")
    # Resume after exit 75: a NEW driver (new process) must not restore the phase start again.
    client = nexus_driver.GatewayClient(
        "http://127.0.0.1:18766", "tok-123", transport=FakeGateway()
    )
    resumed = nexus_driver.NexusArmDriver(
        client,
        campaign_id="c",
        goal_id="g",
        scope_id="s",
        sleep=lambda _s: None,
        state_root=tmp_path / "state",
        state_snapshot=tmp_path / "snapshot",
        state_dir=tmp_path / "state" / "tasks",
        learning_phase="LA",
    )
    row = resumed.run(task, 2, run_root, timeout_seconds=5)
    assert "state_restore" not in row and row["state_phase_marker"] == "resumed", row
    assert (tmp_path / "state" / "learning" / "episodes.jsonl").read_text() == learned
    # A marker written for another phase start refuses before any row.
    (tmp_path / "snapshot" / "learning" / "episodes.jsonl").write_text("another phase start\n")
    other = nexus_driver.NexusArmDriver(
        client,
        campaign_id="c",
        goal_id="g",
        scope_id="s",
        sleep=lambda _s: None,
        state_root=tmp_path / "state",
        state_snapshot=tmp_path / "snapshot",
        state_dir=tmp_path / "state" / "tasks",
        learning_phase="LA",
    )
    rows_before = len(list(read_jsonl(run_root / "rows.jsonl")))
    with pytest.raises(state_phase.PhaseMarkerMismatch, match="STATE_PHASE_MARKER_MISMATCH"):
        other.run(task, 3, run_root, timeout_seconds=5)
    assert len(list(read_jsonl(run_root / "rows.jsonl"))) == rows_before
    assert (tmp_path / "state" / "learning" / "episodes.jsonl").read_text() == learned


def test_state_inside_the_controller_refuses_to_start(tmp_path, monkeypatch):
    from scripts.bench.measure_2721 import controller_guard, gateway_env

    layout = _measure_layout(tmp_path)
    inside = layout["controller"] / ".nexus" / "state"
    env_file = tmp_path / "start.sh"
    env_file.write_text(
        f'export NEXUS_STATE_ROOT="{inside}"\nexport OTHER=1\nexec python gateway.py\n'
        "export NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR=/after/exec\n"
    )
    paths = gateway_env.gateway_state_paths(env_file)
    assert paths == {"NEXUS_STATE_ROOT": str(inside)}  # nothing after exec, nothing else
    with pytest.raises(
        controller_guard.ControllerGuardError, match="STATE_INSIDE_CONTROLLER: NEXUS_STATE_ROOT"
    ):
        _controller_driver(FakeGateway(), layout, gateway_state_paths=paths)
    with pytest.raises(
        controller_guard.ControllerGuardError, match="STATE_INSIDE_CONTROLLER: --state-dir"
    ):
        _controller_driver(FakeGateway(), layout, state_dir=layout["controller"] / "tasks")
    outside = tmp_path / "state"
    with pytest.raises(
        controller_guard.ControllerGuardError, match="STATE_PATH_DISAGREES_WITH_GATEWAY"
    ):
        _controller_driver(
            FakeGateway(),
            layout,
            state_root=tmp_path / "elsewhere",
            gateway_state_paths={"NEXUS_STATE_ROOT": str(outside)},
        )
    # A Gateway state path without a learning phase and its snapshot fails closed.
    with pytest.raises(ValueError, match="LEARNING_PHASE_REQUIRED"):
        _controller_driver(FakeGateway(), layout, state_root=outside, state_dir=outside / "tasks",
                           gateway_state_paths={"NEXUS_STATE_ROOT": str(outside)})
    (tmp_path / "snap").mkdir()
    _controller_driver(FakeGateway(), layout, state_root=outside, state_dir=outside / "tasks",
                       state_snapshot=tmp_path / "snap", learning_phase="M",
                       gateway_state_paths={"NEXUS_STATE_ROOT": str(outside)})


def test_self_hosted_state_dir_is_restored_per_row_and_keeps_probe_evidence(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    state_root, snapshot = tmp_path / "state", tmp_path / "snapshot"
    (snapshot / "learning").mkdir(parents=True)
    (snapshot / "learning" / "episodes.jsonl").write_text("phase start\n")
    state_root.mkdir()
    hosted, hosted_snap = tmp_path / "self-hosted", tmp_path / "self-hosted-snap"
    (hosted_snap / "assisted_provider_jobs").mkdir(parents=True)
    (hosted_snap / "memory.json").write_text('{"phase": "start"}')
    (hosted_snap / "assisted_provider_jobs" / "old-job.json").write_text("{}")
    hosted.mkdir()

    class Writes(FakeGateway):
        def _answer(self, name, args):
            if name == "nexus_worker_candidate":
                (hosted / "memory.json").write_text(f'{{"learned": "{args["task_id"]}"}}')
                (hosted / "assisted_provider_jobs").mkdir(exist_ok=True)
                (hosted / "assisted_provider_jobs" / f"{args['task_id']}.json").write_text("{}")
                probe = hosted / "assisted_provider_jobs" / "probe_evidence"
                probe.mkdir(exist_ok=True)
                (probe / f"{args['task_id']}.json").write_text("{}")
            return super()._answer(name, args)

    client = nexus_driver.GatewayClient("http://127.0.0.1:18766", "tok-123", transport=Writes())
    with pytest.raises(ValueError, match="SELF_HOSTED_STATE_NOT_RESTORED"):
        nexus_driver.NexusArmDriver(
            client,
            campaign_id="c",
            goal_id="g",
            scope_id="s",
            state_root=state_root,
            state_snapshot=snapshot,
            state_dir=hosted,
            learning_phase="M",
        )
    driver = nexus_driver.NexusArmDriver(
        client,
        campaign_id="c",
        goal_id="g",
        scope_id="s",
        sleep=lambda _s: None,
        state_root=state_root,
        state_snapshot=snapshot,
        state_dir=hosted,
        state_dir_snapshot=hosted_snap,
        learning_phase="M",
    )
    rows = [driver.run(task, r, tmp_path / "run", timeout_seconds=5) for r in (1, 2)]
    assert all(r["self_hosted_state_restore"]["ok"] and r["state_restore"]["ok"] for r in rows), (
        rows
    )
    # Row 2 started from the phase start: row 1's learning was restored away ...
    assert (hosted / "memory.json").read_text().endswith(f'{rows[1]["gateway_task_id"]}"}}')
    # ... but the whole probe cache (PREREG §5: jobs and probe evidence) is kept, never hashed.
    jobs = sorted(p.name for p in (hosted / "assisted_provider_jobs").glob("*.json"))
    assert jobs == sorted(f"{r['gateway_task_id']}.json" for r in rows)
    assert len(list((hosted / "assisted_provider_jobs" / "probe_evidence").iterdir())) == 2
    from scripts.bench.measure_2721 import state_phase

    assert (
        state_phase.state_sha256(hosted_snap)
        == rows[0]["self_hosted_state_restore"]["restored_sha256"]
    )


def test_every_nexus_row_records_submitted_and_worker_accepted(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    blocked = _driver(FakeGateway(external_target=False)).run(
        task, 1, tmp_path / "run", timeout_seconds=5
    )
    assert blocked["submitted"] is False and blocked["worker_accepted"] is False
    ok = _driver(FakeGateway()).run(task, 2, tmp_path / "run", timeout_seconds=5)
    assert ok["submitted"] is True and ok["worker_accepted"] is True
    refused = _driver(FakeGateway(worker_error={"error": "WORKER_REFUSED_SCOPE"})).run(
        task, 3, tmp_path / "run", timeout_seconds=5
    )
    assert refused["submitted"] is True and refused["worker_accepted"] is False
    rows = list(read_jsonl(tmp_path / "run" / "rows.jsonl"))
    assert len(rows) == 3 and all("submitted" in r and "worker_accepted" in r for r in rows)


# -- amendment 10 split (layer1-rie clarification, #2721 2026-10-20) ---------------


def _blind_rows(rows, tmp_path, task):
    out, arm_map = tmp_path / "blind-a10", tmp_path / "custody" / "arm_map.json"
    blind.blind(rows, out, arm_map, {task["task_id"]: task})
    return list(read_jsonl(out / "candidates.jsonl")), json.loads(arm_map.read_text())


def _nexus_row(repeat, **fields):
    return {"arm": "NEXUS", "run_id": f"n-r{repeat}", "task_id": "", "repeat": repeat, "submitted": True,
            "worker_accepted": True, "infra": False, "outcome": "OK", "flags": [], **fields}


def test_a10_nexus_rejected_before_acceptance_is_excluded_infra(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)

    class CommitFails(FakeGateway):
        def _is_error(self, name):
            return name == "nexus_task_card_commit"

        def _answer(self, name, args):
            if name == "nexus_task_card_commit":
                return {"error": "TASK_CARD_COMMIT_HEAD_MISMATCH"}
            return super()._answer(name, args)

    card = _driver(CommitFails()).run(task, 1, tmp_path / "run", timeout_seconds=5)
    refused = _driver(FakeGateway(worker_error={"error": "WORKER_REFUSED_SCOPE"})).run(
        task, 2, tmp_path / "run", timeout_seconds=5)
    assert card["worker_accepted"] is False and refused["worker_accepted"] is False
    assert refused["infra"] is True and refused["infra_rule"] == "NEXUS_NOT_ACCEPTED"
    candidates, amap = _blind_rows([card, refused], tmp_path, task)
    assert candidates == []
    assert [(e["repeat"], e["infra"], e["rule"], e["nexus_reliability"]) for e in amap["excluded"]] == [
        (1, True, "NEXUS_NOT_ACCEPTED", True), (2, True, "NEXUS_NOT_ACCEPTED", True)]


@pytest.mark.parametrize("fields, reason", [
    ({"outcome": "GATEWAY_ERROR", "error": "TASK_STATUS_UNREADABLE"}, "OUTCOME:GATEWAY_ERROR"),
    ({"flags": ["STATE_LEAK"]}, "STATE_LEAK"),
    ({"outcome": "INFRA", "infra": True, "void_reason": "LB_STATE_CHANGED", "flags": ["LB_STATE_CHANGED"]},
     "VOID:LB_STATE_CHANGED"),
    ({"outcome": "INFRA", "infra": True, "void_reason": "TRACE_MISSING", "flags": ["SNAPSHOT_INVALID"]},
     "VOID:TRACE_MISSING"),
    # A stuck Gateway is now INFRA (PREREG v0.9.2), see test_driver_stops_the_batch_...;
    # an accepted row the driver marked INFRA for a Nexus-side cause stays a candidate.
    ({"outcome": "INFRA", "infra": True}, "OUTCOME:INFRA"),
])
def test_a10_nexus_failure_after_acceptance_is_a_not_solved_candidate(manifest, tmp_path, fields, reason):
    (task,) = arms.load_manifest(manifest)
    row = {**_nexus_row(1, task_id=task["task_id"]), **fields}
    assert blind.exclusion_reason(row) is None
    (candidate,), amap = _blind_rows([row], tmp_path, task)
    assert candidate["scoring_flags"] == ["RUN_INVALID_NOT_SOLVED"] and amap["excluded"] == []
    assert amap["map"][candidate["opaque_id"]]["run_invalid_reason"] == reason


def test_a10_nexus_rate_limit_after_acceptance_stays_infra_like_bare(manifest, tmp_path, monkeypatch):
    from scripts.bench.measure_2721.providers import ProviderResult

    (task,) = arms.load_manifest(manifest)
    venv = os.path.realpath(task["venv"])
    limit = arms.expected_cli_timeout(5)
    gateway = FakeGateway()
    original = gateway._answer

    def answer(name, args):
        payload = original(name, args)
        if name in ("nexus_task_wait", "nexus_task_status"):
            payload["measurement_worktree_diff"] = "diff --git a/x.py b/x.py\n"
        return payload

    gateway._answer = answer
    nexus = _tracing_driver(gateway, tmp_path / "traces", [
        dict(cost=None, venv=venv, limit=limit, output=0, infra="rate_limited")])
    nexus_row = nexus.run(task, 1, tmp_path / "run", timeout_seconds=5)
    monkeypatch.setattr(arms, "_claude_provider_type", lambda: _StubClaude)
    bare_row = arms.run_bare(task, 1, tmp_path / "run", _StubClaude(lambda: ProviderResult(
        status="INFRA", provider="claude", model="claude-haiku-5-5", infra_reason="RATE_LIMITED",
        extra={"venv": venv, "cli_timeout_seconds": limit, "served_models": []})), timeout_seconds=5)
    assert nexus_row["worker_accepted"] is True and nexus_row["symmetric_infra_reasons"] == ["MODEL_ATTEMPT_INFRA"]
    assert blind.exclusion_reason(nexus_row) == ("SYMMETRIC_INFRA", "MODEL_ATTEMPT_INFRA")
    assert blind.exclusion_reason(bare_row) == ("ROW_INFRA", "INFRA")
    # The other symmetric causes, each one alone.
    for extra in ({"error": "claude_infra:provider_unavailable"}, {"watchdog_event": {"kind": "host"}},
                  {"flags": ["CLI_TIMEOUT_MISMATCH"]}, {"flags": ["VENV_NOT_USABLE"]}):
        assert blind.exclusion_reason({**_nexus_row(1), "infra": True, "outcome": "INFRA", **extra})[0] == \
            "SYMMETRIC_INFRA", extra


def test_a10_bare_and_noop_rows_are_unchanged(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    run = tmp_path / "run"
    ok = arms.run_bare(task, 1, run, FakeProvider(edit=_edit), timeout_seconds=5)
    noop = arms.run_noop(task, 1, run)
    assert "worker_accepted" not in ok and "worker_accepted" not in noop
    infra = dict(ok, run_id="b-infra", repeat=2, infra=True, outcome="INFRA", void_reason="NO_TASK_VENV")
    gateway_like = dict(ok, run_id="b-gw", repeat=3, outcome="GATEWAY_ERROR", diff_path=None)
    candidates, amap = _blind_rows([ok, noop, infra, gateway_like], tmp_path, task)
    # The BARE excluded entry keeps its exact previous shape.
    assert amap["excluded"] == [{"arm": "BARE", "run_id": "b-infra", "task_id": task["task_id"], "repeat": 2,
                                 "outcome": "INFRA", "infra": True, "reason": "NO_TASK_VENV"}]
    flags = {amap["map"][c["opaque_id"]]["run_id"]: c["scoring_flags"] for c in candidates}
    assert "RUN_INVALID_NOT_SOLVED" not in flags[ok["run_id"]] + flags[noop["run_id"]]
    assert "RUN_INVALID_NOT_SOLVED" in flags["b-gw"]


def test_a10_duplicate_task_counts_as_not_accepted(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    gateway = FakeGateway()
    original = gateway._answer

    def answer(name, args):
        if name == "nexus_worker_candidate":
            return {"status": "SUBMITTED", "duplicate": {"code": "DUPLICATE_LOGICAL_TASK", "existing_task_id": "x"}}
        return original(name, args)

    gateway._answer = answer
    row = _driver(gateway).run(task, 1, tmp_path / "run", timeout_seconds=5)
    assert row["submitted"] is True and row["worker_accepted"] is False
    assert blind.exclusion_reason(row)[0] == "NEXUS_NOT_ACCEPTED"


def test_a10_driver_infra_follows_acceptance(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    refused = _driver(FakeGateway(worker_error={"error": "WORKER_REFUSED_SCOPE"})).run(
        task, 1, tmp_path / "run", timeout_seconds=5)
    assert refused["infra"] is True and refused["worker_accepted"] is False
    class WaitFails(FakeGateway):
        def _is_error(self, name):
            return name == "nexus_task_wait"

        def _answer(self, name, args):
            if name == "nexus_task_wait":
                return {"error": "TASK_WAIT_FAILED"}
            return super()._answer(name, args)

    accepted = _driver(WaitFails()).run(task, 2, tmp_path / "run", timeout_seconds=5)
    assert accepted["worker_accepted"] is True and accepted["infra"] is False
    assert accepted["outcome"] == "GATEWAY_ERROR"
    candidates, amap = _blind_rows([refused, accepted], tmp_path, task)
    assert [e["run_id"] for e in amap["excluded"]] == [refused["run_id"]]
    (candidate,) = candidates
    assert "RUN_INVALID_NOT_SOLVED" in candidate["scoring_flags"]


# -- review of 3b6b2b894 + PREREG v0.9/v0.9.2: runner blocks, budget, resume, GATE 6 ----


def _runner_env(tmp_path: Path, extra: str = "") -> Path:
    env_file = tmp_path / "gw.env"
    env_file.write_text(f"NEXUS_MEASUREMENT_READ_ROOTS={os.path.realpath(tmp_path)}\n{extra}")
    return env_file


def _fake_build(monkeypatch, gateways: dict):
    """runner.main builds its drivers with FakeGateway transports (per arm label)."""

    def build(args, parser):
        gateway = gateways[args.arm_label]
        client = nexus_driver.GatewayClient("http://127.0.0.1:18766", "tok-123", transport=gateway)
        return nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s",
                                           sleep=lambda _s: None, arm_label=args.arm_label)

    monkeypatch.setattr(nexus_driver, "build_driver", build)


def _runner_main(manifest, tmp_path, run, *extra, repeats=("1",), arms_=("BARE", "NEXUS", "NOOP"),
                 cap="100", max_row="1.0", ledger="spend.json"):
    from scripts.bench.measure_2721 import runner

    env_file = _runner_env(tmp_path)
    noop_args = (f"--gateway-url http://127.0.0.1:18767 --token-file {tmp_path / 'tok'} --scope-id s "
                 f"--trace-dir {tmp_path / 'tn'} --gateway-env {env_file}")
    return runner.main(["--manifest", str(manifest), "--run-root", str(run), "--repeats", *repeats,
                        "--spend-ledger", str(tmp_path / ledger), "--cap-usd", cap, "--max-row-usd", max_row,
                        "--gateway-env", str(env_file), "--gateway-url", "http://127.0.0.1:18766",
                        "--token-file", str(tmp_path / "tok"), "--scope-id", "s", "--trace-dir", str(tmp_path / "t"),
                        "--arms", *arms_, "--noop-gateway-args", noop_args, *extra])


def test_runner_schedules_both_noop_variants_and_both_make_no_edit(manifest, tmp_path, monkeypatch):
    from scripts.bench.measure_2721 import runner

    arms4 = ("BARE", "NEXUS", "NOOP", "NEXUS_NOOP")
    ids = [f"t{i}" for i in range(12)]
    schedule = runner.build_schedule(ids, [1, 2, 3], arms4)
    stats = runner.schedule_stats(schedule)
    assert set(stats["mean_slot"]) == set(arms4) and max(stats["mean_slot"].values()) - \
        min(stats["mean_slot"].values()) < 4 and set(stats["first_third"].values()) == {12}
    _fake_build(monkeypatch, {"NEXUS": FakeGateway(), "NEXUS_NOOP": FakeGateway()})
    run = tmp_path / "run"
    assert _runner_main(manifest, tmp_path, run, repeats=("1", "2"), arms_=arms4) == 0
    rows = list(read_jsonl(run / "rows.jsonl"))
    assert sorted(r["arm"] for r in rows) == sorted(["BARE", "NEXUS", "NOOP", "NEXUS_NOOP"] * 2)
    # Zero-model dry run: neither NOOP variant can resolve anything (empty diff).
    assert all(r["empty"] for r in rows if r["arm"] in ("NOOP", "NEXUS_NOOP"))
    assert json.loads((run / "stop.json").read_text())["reason"] == "DONE"
    blocks = list(read_jsonl(run / "blocks.jsonl"))
    assert [b["status"] for b in blocks] == ["COMPLETE", "COMPLETE"]
    assert all(sorted(b["arm_order"]) == sorted(arms4) for b in blocks)
    # The NEXUS_NOOP Gateway must be another Gateway than the NEXUS one.
    with pytest.raises(nexus_driver.DriverStartRefused, match="NOOP_GATEWAY_IS_THE_NEXUS_GATEWAY"):
        import argparse

        runner._noop_driver(argparse.Namespace(gateway_url="http://127.0.0.1:18767", key_file=None,
                                               noop_gateway_args="--gateway-url http://127.0.0.1:18767 "
                                               "--token-file t --scope-id s --trace-dir d --gateway-env e"),
                            nexus_driver)


def test_runner_admits_whole_blocks_and_stops_at_the_cap_with_75(manifest, tmp_path, monkeypatch):
    from scripts.bench.measure_2721.budget import DEFAULT_CAP_USD, SpendLedger

    assert DEFAULT_CAP_USD == 100.0
    _fake_build(monkeypatch, {"NEXUS": FakeGateway()})
    run = tmp_path / "run"
    rc = _runner_main(manifest, tmp_path, run, repeats=tuple(str(r) for r in range(1, 7)), cap="5", max_row="1.0")
    assert rc == 75
    stop = json.loads((run / "stop.json").read_text())
    blocks = list(read_jsonl(run / "blocks.jsonl"))
    # Every started block finished (all three arms), none was started without room for it.
    assert stop["reason"] == "BUDGET_CAP" and stop["last_completed_block"] == blocks[-1]["block"]
    assert all(b["status"] == "COMPLETE" and len(b["run_ids"]) == 3 for b in blocks)
    state = SpendLedger(tmp_path / "spend.json", 5.0, 1.0).state()
    assert len(blocks) == 2 and state["spent_usd"] == pytest.approx(4.0)  # 2 charged arms x 1.0 per block
    assert state["cap_usd"] == 5.0 and state["max_row_usd"] == 1.0
    # A different cap on the same ledger is refused.
    with pytest.raises(Exception, match="cap_usd"):
        _runner_main(manifest, tmp_path, run, repeats=tuple(str(r) for r in range(1, 7)), cap="6")
    # Mid-block, an admitted block finishes even past the cap (overshoot bounded by one block).
    ledger = SpendLedger(tmp_path / "s2.json", 1.0, 1.0)
    ledger.begin_block(1)
    admitted = ledger.admitted()
    for _ in range(3):
        admitted.finish_row(admitted.begin_row(), None)
    assert ledger.state()["spent_usd"] == pytest.approx(3.0)


class _StuckOnWorker(FakeGateway):
    """The n-th worker's task never terminates (cancel refused, PENDING_HUMAN_APPROVAL)."""

    def __init__(self, nth: int):
        super().__init__()
        self.nth, self.workers, self.stuck = nth, 0, None

    def _answer(self, name, args):
        if name == "nexus_worker_candidate":
            self.workers += 1
            if self.workers == self.nth:
                self.stuck = args["task_id"]
        payload = super()._answer(name, args)
        if name == "nexus_task_status" and args.get("task_id") == self.stuck:
            payload["status"] = "PENDING_HUMAN_APPROVAL"
        return payload


def test_runner_resumes_without_rerunning_completed_rows(manifest, tmp_path, monkeypatch):
    _fake_build(monkeypatch, {"NEXUS": _StuckOnWorker(2)})
    run = tmp_path / "run"
    repeats = tuple(str(r) for r in range(1, 4))
    assert _runner_main(manifest, tmp_path, run, repeats=repeats) == 75  # stuck in block 1
    assert json.loads((run / "stop.json").read_text())["reason"] == "GATEWAY_STUCK"
    first = list(read_jsonl(run / "blocks.jsonl"))
    assert [(b["block"], b["status"]) for b in first] == [(0, "COMPLETE")]
    schedule = (run / "schedule.json").read_text()
    # A resume with a new (or missing) ledger would reset the spend: refused.
    assert _runner_main(manifest, tmp_path, run, repeats=repeats, ledger="spend2.json") == 2
    # Same seed, schedule and ledger: block 0 is not re-run, block 1 re-runs WHOLE.
    _fake_build(monkeypatch, {"NEXUS": FakeGateway()})
    assert _runner_main(manifest, tmp_path, run, repeats=repeats) == 0
    assert (run / "schedule.json").read_text() == schedule
    blocks = list(read_jsonl(run / "blocks.jsonl"))
    assert [(b["block"], b["attempt"], b["status"]) for b in blocks] == [
        (0, 0, "COMPLETE"), (1, 0, "RERUN"), (1, 1, "COMPLETE"), (2, 0, "COMPLETE")]
    assert blocks[0]["run_ids"] == first[0]["run_ids"]
    assert blocks[1]["infra_why"]["NEXUS"] == "INFRA" and set(blocks[2]["run_ids"]) == {"BARE", "NEXUS", "NOOP"}
    assert not set(blocks[2]["run_ids"].values()) & set((blocks[1]["run_ids"] or {}).values())
    # Another seed (or task set) on the same run root is refused.
    assert _runner_main(manifest, tmp_path, run, "--seed", "1", repeats=repeats) == 2


def test_runner_reruns_the_whole_block_after_a_lost_gateway_or_a_crash(manifest, tmp_path, monkeypatch):
    import urllib.error

    class Dies(FakeGateway):
        """The Gateway stops answering after accepting the worker; with ``watchdog`` the
        watchdog killed it and recorded an event for the current row."""

        def __init__(self, run_root=None):
            super().__init__()
            self.run_root = run_root

        def __call__(self, method, path, body):
            if body and body.get("params", {}).get("name") in ("nexus_task_wait", "nexus_task_status",
                                                                  "nexus_task_cancel"):
                if self.run_root is not None:
                    current = json.loads((self.run_root / "run" / "current_row.json").read_text())
                    with (self.run_root / "run" / "infra_events.jsonl").open("a") as handle:
                        handle.write(json.dumps({"row_id": current["row_id"], "kind": "killed"}) + "\n")
                    self.run_root = None
                raise ConnectionResetError(54, "Connection reset by peer")
            return super().__call__(method, path, body)

    # (a) Lost after acceptance, no watchdog event: a Nexus failure, not infra (re-review #3).
    run = tmp_path / "run"
    _fake_build(monkeypatch, {"NEXUS": Dies()})
    assert _runner_main(manifest, tmp_path, run) == 75
    (row,) = [r for r in read_jsonl(run / "rows.jsonl") if r["arm"] == "NEXUS"]
    assert row["void_reason"] == "GATEWAY_CONNECTION_LOST" and row["worker_accepted"] and not row["infra"]
    assert blind.exclusion_reason(row) is None and blind.run_invalid_reason(row) == "VOID:GATEWAY_CONNECTION_LOST"
    _fake_build(monkeypatch, {"NEXUS": FakeGateway()})
    assert _runner_main(manifest, tmp_path, run) == 0
    (block,) = list(read_jsonl(run / "blocks.jsonl"))  # the same attempt finished: no second NEXUS try
    assert block["status"] == "COMPLETE" and block["run_ids"]["NEXUS"] == row["run_id"]
    # (b) The watchdog killed the Gateway (an event for the row): INFRA, the whole block re-runs.
    run_w = tmp_path / "run-w"
    _fake_build(monkeypatch, {"NEXUS": Dies(run_w)})
    assert _runner_main(manifest, tmp_path, run_w, ledger="spend-w.json") == 75
    (row,) = [r for r in read_jsonl(run_w / "rows.jsonl") if r["arm"] == "NEXUS"]
    assert row["infra"] and row["watchdog_event"] and blind.exclusion_reason(row)[0] == "SYMMETRIC_INFRA"
    _fake_build(monkeypatch, {"NEXUS": FakeGateway()})
    assert _runner_main(manifest, tmp_path, run_w, ledger="spend-w.json") == 0
    assert [(b["attempt"], b["status"]) for b in read_jsonl(run_w / "blocks.jsonl")] == [
        (0, "RERUN"), (1, "COMPLETE")]
    # (c) A row crashes outright (no row written): the whole block re-runs, every arm.
    run_c = tmp_path / "run-c"
    real_noop = arms.run_noop
    monkeypatch.setattr(arms, "run_noop", lambda *a, **k: (_ for _ in ()).throw(OSError("disk")))
    assert _runner_main(manifest, tmp_path, run_c, ledger="spend-c.json") == 75
    assert json.loads((run_c / "stop.json").read_text())["reason"] == "ROW_EXCEPTION"
    monkeypatch.setattr(arms, "run_noop", real_noop)
    with (run_c / "progress.jsonl").open("a") as handle:
        handle.write('{"block": 0, "torn')  # a crash mid-write
    assert _runner_main(manifest, tmp_path, run_c, ledger="spend-c.json") == 0
    blocks = list(read_jsonl(run_c / "blocks.jsonl"))
    assert [(b["attempt"], b["status"]) for b in blocks] == [(0, "RERUN"), (1, "COMPLETE")]
    assert blocks[0]["infra_why"]["NOOP"] == "CRASHED"
    final, earlier = blocks[-1]["run_ids"], set(blocks[0]["run_ids"].values())
    assert set(final) == {"BARE", "NEXUS", "NOOP"} and not set(final.values()) & earlier  # every arm re-ran
    # The client: connection-layer errors -> GatewayConnectionLost; an HTTP error answer is the
    # Gateway's own error (GatewayToolError), never a lost connection.
    for exc in (urllib.error.URLError("refused"), TimeoutError("timed out"), ConnectionResetError()):
        def broken(*_a, exc=exc):
            raise exc
        client = nexus_driver.GatewayClient("http://127.0.0.1:18766", "t", transport=broken)
        with pytest.raises(nexus_driver.GatewayConnectionLost):
            client.health()


def test_gateway_http_errors_after_acceptance_are_not_infra(manifest, tmp_path):
    import urllib.error

    (task,) = arms.load_manifest(manifest)

    class Answers400(FakeGateway):
        def __call__(self, method, path, body):
            if body and body.get("params", {}).get("name") == "nexus_task_wait":
                raise urllib.error.HTTPError("http://127.0.0.1:18766/mcp", 400, "Bad Request", {}, None)
            return super().__call__(method, path, body)

    row = _driver(Answers400()).run(task, 1, tmp_path / "run", timeout_seconds=5)
    assert row["worker_accepted"] and row["outcome"] == "GATEWAY_ERROR" and not row["infra"]
    assert "http_status" in row["error"] and blind.exclusion_reason(row) is None
    (candidate,), amap = _blind_rows([row], tmp_path, task)
    assert "RUN_INVALID_NOT_SOLVED" in candidate["scoring_flags"] and amap["excluded"] == []

    class Refuses500(FakeGateway):
        def __call__(self, method, path, body):
            if body and body.get("params", {}).get("name") == "nexus_worker_candidate":
                raise urllib.error.HTTPError("http://127.0.0.1:18766/mcp", 500, "Error", {}, None)
            return super().__call__(method, path, body)

    row = _driver(Refuses500()).run(task, 2, tmp_path / "run", timeout_seconds=5)
    assert row["infra"] and not row["worker_accepted"] and blind.exclusion_reason(row)[0] == "NEXUS_NOT_ACCEPTED"


def test_reopened_complete_block_never_exceeds_two_reruns(manifest, tmp_path, monkeypatch):
    class Flaky(FakeGateway):
        def __init__(self, refusals):
            super().__init__()
            self.refusals, self.refused_last = refusals, False

        def _is_error(self, name):
            return name == "nexus_worker_candidate" and self.refused_last

        def _answer(self, name, args):
            self.refused_last = name == "nexus_worker_candidate" and self.refusals > 0
            if self.refused_last:
                self.refusals -= 1
                return {"error": "WORKER_REFUSED"}
            return super()._answer(name, args)

    _fake_build(monkeypatch, {"NEXUS": Flaky(2)})
    run = tmp_path / "run"
    assert _runner_main(manifest, tmp_path, run) == 0
    last = list(read_jsonl(run / "blocks.jsonl"))[-1]
    assert (last["attempt"], last["status"]) == (2, "COMPLETE")
    with (run / "run" / "infra_events.jsonl").open("a") as handle:
        handle.write(json.dumps({"row_id": last["run_ids"]["BARE"], "kind": "late"}) + "\n")
    _fake_build(monkeypatch, {"NEXUS": FakeGateway()})
    assert _runner_main(manifest, tmp_path, run) == 0
    blocks = list(read_jsonl(run / "blocks.jsonl"))
    assert [(b["attempt"], b["status"]) for b in blocks][-1] == (2, "EXCLUDED_AFTER_RERUNS")
    assert max(b["attempt"] for b in blocks) == 2


def test_runner_reruns_a_complete_block_with_a_late_watchdog_event(manifest, tmp_path, monkeypatch):
    _fake_build(monkeypatch, {"NEXUS": FakeGateway()})
    run = tmp_path / "run"
    assert _runner_main(manifest, tmp_path, run) == 0
    (block,) = list(read_jsonl(run / "blocks.jsonl"))
    with (run / "run" / "infra_events.jsonl").open("a") as handle:
        handle.write(json.dumps({"row_id": block["run_ids"]["BARE"], "kind": "late"}) + "\n")
    assert _runner_main(manifest, tmp_path, run) == 0
    blocks = list(read_jsonl(run / "blocks.jsonl"))
    assert [(b["attempt"], b["status"]) for b in blocks] == [(0, "COMPLETE"), (0, "RERUN"), (1, "COMPLETE")]
    assert blocks[1]["late_infra"] == {"BARE": "WATCHDOG_EVENT"}


def test_probe_cache_is_kept_when_the_self_hosted_dir_is_inside_the_state_root(tmp_path):
    from scripts.bench.measure_2721 import state_phase

    root, snap = tmp_path / "state", tmp_path / "snap"
    (snap / "tasks").mkdir(parents=True)
    (snap / "tasks" / "memory.json").write_text("start")
    jobs = root / "tasks" / "assisted_provider_jobs"
    (jobs / "probe_evidence").mkdir(parents=True)
    (jobs / "probe-1.json").write_text("{}")
    (jobs / "probe_evidence" / "e.json").write_text("{}")
    (root / "tasks" / "memory.json").write_text("learned")
    result = state_phase.restore_state(root, snap)
    assert result["ok"] and (jobs / "probe-1.json").is_file() and (jobs / "probe_evidence" / "e.json").is_file()
    assert (root / "tasks" / "memory.json").read_text() == "start"
    assert state_phase.state_sha256(root) == state_phase.state_sha256(snap)


def test_runner_reruns_an_infra_block_twice_then_excludes_it(manifest, tmp_path, monkeypatch):
    class Flaky(FakeGateway):
        def __init__(self, refusals):
            super().__init__()
            self.refusals = refusals

            self.refused_last = False

        def _is_error(self, name):
            return name == "nexus_worker_candidate" and self.refused_last

        def _answer(self, name, args):
            self.refused_last = name == "nexus_worker_candidate" and self.refusals > 0
            if self.refused_last:
                self.refusals -= 1
                return {"error": "WORKER_REFUSED"}
            return super()._answer(name, args)

    _fake_build(monkeypatch, {"NEXUS": Flaky(1)})
    run = tmp_path / "run"
    assert _runner_main(manifest, tmp_path, run) == 0
    blocks = list(read_jsonl(run / "blocks.jsonl"))
    assert [(b["attempt"], b["status"], b["infra_arms"]) for b in blocks] == [
        (0, "RERUN", ["NEXUS"]), (1, "COMPLETE", [])]
    assert blocks[0]["arm_order"] == blocks[1]["arm_order"]  # the same order on a re-run
    out, amap_path = tmp_path / "blind", tmp_path / "custody" / "map.json"
    blind.main(["--run-roots", str(run), "--out", str(out), "--arm-map", str(amap_path),
                "--manifest", str(manifest)])
    amap = json.loads(amap_path.read_text())
    assert len(amap["map"]) == 3 and amap["excluded"] == []
    assert amap["noop_nonempty_diff"] == []  # real NOOP rows, superseded ones too: no false hit
    assert sorted(d["reason"] for d in amap["dropped"]) == ["RERUN_SUPERSEDED"] * 3
    # Infra in all three attempts: the block is excluded after two re-runs.
    _fake_build(monkeypatch, {"NEXUS": Flaky(3)})
    run2 = tmp_path / "run2"
    assert _runner_main(manifest, tmp_path, run2, ledger="spend2.json") == 0
    statuses = [(b["attempt"], b["status"]) for b in read_jsonl(run2 / "blocks.jsonl")]
    assert statuses == [(0, "RERUN"), (1, "RERUN"), (2, "EXCLUDED_AFTER_RERUNS")]


def test_runner_stops_with_75_when_the_instance_stays_busy(manifest, tmp_path, monkeypatch):
    from scripts.bench.measure_2721 import runner

    states = tmp_path / "self-hosted"
    states.mkdir()
    (states / "other.json").write_text(json.dumps({"status": "IN_PROGRESS"}))
    gateway = FakeGateway()

    def build(args, parser):
        client = nexus_driver.GatewayClient("http://127.0.0.1:18766", "tok-123", transport=gateway)
        return nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s",
                                           sleep=lambda _s: None, state_dir=states)

    monkeypatch.setattr(nexus_driver, "build_driver", build)
    run = tmp_path / "run"
    rc = _runner_main(manifest, tmp_path, run, "--seed", "3", repeats=("1", "2"), arms_=("NEXUS", "BARE"))
    stop = json.loads((run / "stop.json").read_text())
    assert rc == 75 and stop["reason"] == "INSTANCE_BUSY" and not gateway.calls
    rows = list(read_jsonl(run / "rows.jsonl"))
    assert rows[-1]["arm"] == "NEXUS" and rows[-1]["void_reason"].startswith("INSTANCE_BUSY:")
    assert runner.block_outcomes(run)["counted"] == set()


@pytest.mark.parametrize("line", [
    "NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1", "NEXUS_EXTERNAL_WORKER_OPERATION_ROOT=/x",
    "NEXUS_LOCAL_MODEL_CALL_ALLOWED=1", "NEXUS_LOCAL_MODEL=qwen", "NEXUS_LLM_JUDGE_PROVIDERS=codex",
    "NEXUS_LEARNING_REFLECT_JUDGE=1", "NEXUS_USE_COMMITTEE=1", "NEXUS_COMMITTEE_BUDGET_REMAINING=5",
    "NEXUS_CORE_EXTERNAL_VERIFICATION=1", "NEXUS_DOC_SCOUT_EXTERNAL_ROWS_JSON=/r.json", "NEXUS_MSA_ENABLED=1",
    "NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL=1", "NEXUS_ENABLE_LOCAL_SWARM_EXECUTOR=true",
    "NEXUS_ONLINE_LOCAL_ASSIST=yes", "NEXUS_OLLAMA_ENABLED=1", "export NEXUS_SHADOW_ADVISOR_ENABLED=True",
])
def test_gate6_refuses_every_extra_model_switch(manifest, tmp_path, line, capsys):
    env_file = _runner_env(tmp_path, line + "\nexec python gateway.py\n")
    rc = arms.main(["noop", "--manifest", str(manifest), "--run-root", str(tmp_path / "run"),
                    "--spend-ledger", str(tmp_path / "spend.json"), "--gateway-env", str(env_file)])
    out = capsys.readouterr().out
    name = line.split()[-1].split("=")[0]
    assert rc == 2 and "GATE6_EXTRA_MODEL_SWITCH" in out and name in out
    assert json.loads((tmp_path / "run" / "gate6_refused.json").read_text())["switches"] == [name]
    assert "/x" not in out and "qwen" not in out  # names only, never values


def test_gate6_clean_env_passes_and_agy_only_warns(manifest, tmp_path, capsys):
    from scripts.bench.measure_2721 import gateway_env

    env_file = _runner_env(tmp_path, "NEXUS_USE_COMMITTEE=0\nNEXUS_LOCAL_MODEL_CALL_ALLOWED=\n"
                                     "NEXUS_AGY_RUNTIME_AUTHORIZED=1\nexec x\nNEXUS_USE_COMMITTEE=1\n")
    warnings: list[str] = []
    assert gateway_env.gate6_switches(env_file, warnings=warnings) == []
    assert warnings == ["NEXUS_AGY_RUNTIME_AUTHORIZED"]
    rc = arms.main(["noop", "--manifest", str(manifest), "--run-root", str(tmp_path / "run"),
                    "--spend-ledger", str(tmp_path / "spend.json"), "--gateway-env", str(env_file)])
    assert rc == 0 and "GATE 6: NEXUS_AGY_RUNTIME_AUTHORIZED" in capsys.readouterr().err


def test_learning_phase_without_every_snapshot_fails_closed(tmp_path):
    client = nexus_driver.GatewayClient("http://127.0.0.1:18766", "t", transport=FakeGateway())
    root, snap, hosted = tmp_path / "state", tmp_path / "snap", tmp_path / "hosted"
    for phase in ("M", "LA", "LB"):
        with pytest.raises(ValueError, match="STATE_ROOT_SNAPSHOT_REQUIRED"):
            nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s", state_root=root,
                                        state_dir=root / "tasks", learning_phase=phase)
        with pytest.raises(ValueError, match="SELF_HOSTED_STATE_DIR_REQUIRED"):
            nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s", state_root=root,
                                        state_snapshot=snap, learning_phase=phase)
        with pytest.raises(ValueError, match="SELF_HOSTED_STATE_NOT_RESTORED"):
            nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s", state_root=root,
                                        state_snapshot=snap, state_dir=hosted, learning_phase=phase)
    with pytest.raises(ValueError, match="LEARNING_PHASE_REQUIRED"):
        nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s", state_root=root,
                                    state_snapshot=snap, state_dir=root / "tasks", learning_phase="X")
    with pytest.raises(ValueError, match="LEARNING_PHASE_REQUIRED"):
        nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s",
                                    gateway_state_paths={"NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR": str(hosted)})


def test_probe_cache_is_never_restored_or_hashed(tmp_path):
    from scripts.bench.measure_2721 import state_phase

    root, snap = tmp_path / "state", tmp_path / "snap"
    (snap / "learning").mkdir(parents=True)
    (snap / "learning" / "x.json").write_text("start")
    jobs = root / "assisted_provider_jobs"
    (jobs / "probe_evidence").mkdir(parents=True)
    (jobs / "probe-1.json").write_text("{}")
    (jobs / "probe-1.stdout").write_text("ok")
    (jobs / "probe_evidence" / "e.json").write_text("{}")
    result = state_phase.restore_state(root, snap)
    assert result["ok"] and (jobs / "probe-1.json").is_file() and (jobs / "probe-1.stdout").is_file()
    assert state_phase.state_sha256(root) == state_phase.state_sha256(snap)


def test_harness_side_presubmit_failure_is_not_nexus_reliability(manifest, tmp_path):
    (task,) = arms.load_manifest(manifest)
    row = {**_nexus_row(1, task_id=task["task_id"]), "worker_accepted": False, "submitted": False,
           "infra": True, "outcome": "INFRA", "void_reason": "CONTROLLER_RESET_MISMATCH"}
    gateway_refused = {**row, "run_id": "n-r2", "repeat": 2, "void_reason": "PRE_SUBMIT_FAILURE:nexus_task_card_create"}
    _candidates, amap = _blind_rows([row, gateway_refused], tmp_path, task)
    by_run = {e["run_id"]: e for e in amap["excluded"]}
    assert by_run["n-r1"]["rule"] == "HARNESS_NOT_SUBMITTED" and by_run["n-r1"]["nexus_reliability"] is False
    assert by_run["n-r1"]["harness_failure"] is True
    assert by_run["n-r2"]["rule"] == "NEXUS_NOT_ACCEPTED" and by_run["n-r2"]["nexus_reliability"] is True


def test_started_at_is_written_once_in_utc_for_every_arm(manifest, tmp_path, monkeypatch):
    import re
    import time as time_module

    from scripts.bench.measure_2721 import watchdog

    (task,) = arms.load_manifest(manifest)
    run = tmp_path / "run"
    current = run / "run" / "current_row.json"
    utc = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
    seen = {}
    real_mark, real_gmtime = watchdog.mark_snapshot, time_module.gmtime

    def later_snapshot(run_root):
        before = json.loads(current.read_text())["started_at"]
        watchdog.time.gmtime = lambda *_a: real_gmtime(4102444800)  # year 2100
        try:
            real_mark(run_root)
        finally:
            watchdog.time.gmtime = real_gmtime
        seen["after"] = json.loads(current.read_text())
        assert seen["after"]["started_at"] == before  # never rewritten by the snapshot update

    monkeypatch.setattr(watchdog, "mark_snapshot", later_snapshot)
    bare = arms.run_bare(task, 1, run, FakeProvider(edit=_edit), timeout_seconds=5)
    assert utc.match(bare["started_at"]) and bare["started_at"] == seen["after"]["started_at"]
    assert seen["after"]["snapshot_at"].startswith("2100-")
    nexus = _driver(FakeGateway()).run(task, 1, run, timeout_seconds=5)
    assert utc.match(nexus["started_at"]) and nexus["started_at"] == json.loads(current.read_text())["started_at"]
    noop = arms.run_noop(task, 1, run)
    assert utc.match(noop["started_at"]) and json.loads(current.read_text())["row_id"] == noop["run_id"]
    assert json.loads(current.read_text())["started_at"] == noop["started_at"]
    for row in read_jsonl(run / "rows.jsonl"):
        assert utc.match(row["started_at"]), row["arm"]


def test_non_json_gateway_reply_after_acceptance_is_not_solved_and_never_rerun(manifest, tmp_path, monkeypatch):
    from scripts.bench.measure_2721 import runner

    class TextReply(FakeGateway):
        """After acceptance the first wait answers with plain text (not JSON)."""

        def __init__(self):
            super().__init__()
            self.waits = 0

        def __call__(self, method, path, body):
            if body and body.get("params", {}).get("name") == "nexus_task_wait":
                self.waits += 1
                if self.waits == 1:
                    return {"result": {"content": [{"type": "text", "text": "Error executing tool: boom"}],
                                       "isError": True}}
            return super().__call__(method, path, body)

    gateway = TextReply()
    _fake_build(monkeypatch, {"NEXUS": gateway})
    run = tmp_path / "run"
    assert _runner_main(manifest, tmp_path, run) == 0
    (block,) = list(read_jsonl(run / "blocks.jsonl"))
    assert (block["attempt"], block["status"]) == (0, "COMPLETE")  # NEXUS is not re-run
    (row,) = [r for r in read_jsonl(run / "rows.jsonl") if r["arm"] == "NEXUS"]
    assert row["worker_accepted"] and row["outcome"] == "GATEWAY_ERROR" and not row["infra"]
    assert "malformed_reply" in row["error"]
    out, amap_path = tmp_path / "blind", tmp_path / "custody" / "map.json"
    blind.main(["--run-roots", str(run), "--out", str(out), "--arm-map", str(amap_path),
                "--manifest", str(manifest)])
    amap = json.loads(amap_path.read_text())
    nexus = [o for o, m in amap["map"].items() if m["arm"] == "NEXUS"]
    flags = {c["opaque_id"]: c["scoring_flags"] for c in read_jsonl(out / "candidates.jsonl")}
    assert len(nexus) == 1 and "RUN_INVALID_NOT_SOLVED" in flags[nexus[0]] and amap["excluded"] == []
    # Any other driver failure after acceptance (here: parsing the final state) is a
    # GATEWAY_ERROR row too, never a crash.
    (task,) = arms.load_manifest(manifest)
    driver = _driver(FakeGateway())
    monkeypatch.setattr(driver, "_collect", lambda *a, **k: (_ for _ in ()).throw(KeyError("status")))
    row = driver.run(task, 2, tmp_path / "run2", timeout_seconds=5)
    assert row["worker_accepted"] and row["outcome"] == "GATEWAY_ERROR" and not row["infra"]
    assert row["void_reason"] == "GATEWAY_ERROR_AFTER_ACCEPTANCE:KeyError"
    # The runner dies after the row was written but before its completion record: the
    # resume takes the row from rows.jsonl instead of calling it CRASHED.
    run3 = tmp_path / "run3"
    _fake_build(monkeypatch, {"NEXUS": FakeGateway()})
    real_append = runner._append

    def dies_on_nexus_done(path, record):
        if record.get("arm") == "NEXUS" and "event" not in record:
            raise KeyboardInterrupt("killed")
        real_append(path, record)

    monkeypatch.setattr(runner, "_append", dies_on_nexus_done)
    with pytest.raises(KeyboardInterrupt):
        _runner_main(manifest, tmp_path, run3, ledger="spend3.json")
    monkeypatch.setattr(runner, "_append", real_append)
    (first,) = [r for r in read_jsonl(run3 / "rows.jsonl") if r["arm"] == "NEXUS"]
    assert _runner_main(manifest, tmp_path, run3, ledger="spend3.json") == 0
    (block,) = list(read_jsonl(run3 / "blocks.jsonl"))
    assert (block["attempt"], block["status"]) == (0, "COMPLETE") and block["run_ids"]["NEXUS"] == first["run_id"]
    assert len([r for r in read_jsonl(run3 / "rows.jsonl") if r["arm"] == "NEXUS"]) == 1


def test_interrupt_after_acceptance_is_crashed_and_the_whole_block_reruns(manifest, tmp_path, monkeypatch):
    class Interrupted(FakeGateway):
        def __init__(self):
            super().__init__()
            self.fired = False

        def __call__(self, method, path, body):
            if not self.fired and body and body.get("params", {}).get("name") == "nexus_task_wait":
                self.fired = True
                raise KeyboardInterrupt("operator")
            return super().__call__(method, path, body)

    _fake_build(monkeypatch, {"NEXUS": Interrupted()})
    run = tmp_path / "run"
    with pytest.raises(KeyboardInterrupt):
        _runner_main(manifest, tmp_path, run)
    (row,) = [r for r in read_jsonl(run / "rows.jsonl") if r["arm"] == "NEXUS"]
    assert row["worker_accepted"] and row["outcome"] == "INTERRUPTED" and row["infra"]
    assert row["void_reason"] == "INTERRUPTED:KeyboardInterrupt"
    before = {r["arm"]: r["run_id"] for r in read_jsonl(run / "rows.jsonl")}
    _fake_build(monkeypatch, {"NEXUS": FakeGateway()})
    assert _runner_main(manifest, tmp_path, run) == 0
    blocks = list(read_jsonl(run / "blocks.jsonl"))
    assert [(b["attempt"], b["status"]) for b in blocks] == [(0, "RERUN"), (1, "COMPLETE")]
    assert blocks[0]["infra_why"]["NEXUS"] == "CRASHED"
    final = blocks[1]["run_ids"]
    assert set(final) == {"BARE", "NEXUS", "NOOP"} and not set(final.values()) & set(before.values())


@pytest.mark.parametrize("tamper", ["no_offset", "consumed"])
def test_recovery_needs_an_offset_and_an_unconsumed_finished_row(manifest, tmp_path, monkeypatch, tamper):
    from scripts.bench.measure_2721 import runner

    _fake_build(monkeypatch, {"NEXUS": FakeGateway()})
    run = tmp_path / "run"
    real_append = runner._append

    def dies_on_nexus_done(path, record):
        if record.get("arm") == "NEXUS" and "event" not in record:
            raise KeyboardInterrupt("killed")
        real_append(path, record)

    monkeypatch.setattr(runner, "_append", dies_on_nexus_done)
    with pytest.raises(KeyboardInterrupt):
        _runner_main(manifest, tmp_path, run)
    monkeypatch.setattr(runner, "_append", real_append)
    (nexus,) = [r for r in read_jsonl(run / "rows.jsonl") if r["arm"] == "NEXUS"]
    progress = run / "progress.jsonl"
    records = list(read_jsonl(progress))
    if tamper == "no_offset":
        records = [{k: v for k, v in r.items() if k != "rows_offset"} if r.get("arm") == "NEXUS" else r
                   for r in records]
    else:  # another progress record already consumed that row
        records.append({"block": 99, "attempt": 0, "slot": 0, "arm": "NEXUS", "run_id": nexus["run_id"],
                        "infra": False})
    progress.write_text("".join(json.dumps(r) + "\n" for r in records))
    assert _runner_main(manifest, tmp_path, run) == 0
    blocks = list(read_jsonl(run / "blocks.jsonl"))
    assert [(b["attempt"], b["status"]) for b in blocks] == [(0, "RERUN"), (1, "COMPLETE")]
    assert blocks[0]["infra_why"]["NEXUS"] == "CRASHED" and blocks[1]["run_ids"]["NEXUS"] != nexus["run_id"]


# -- re-review #6: one classification from immutable facts ------------------------------

_ACC = {"accepted": True}


@pytest.mark.parametrize("facts, expected", [
    # (facts, (outcome, infra, void_reason, rule, nexus_reliability))
    ({"accepted": True, "model_outcome": "OK"}, ("OK", False, None, None, False)),
    ({**_ACC, "model_outcome": "TIMEOUT"}, ("TIMEOUT", False, None, None, False)),
    ({**_ACC, "model_outcome": "MODEL_FAILED"}, ("MODEL_FAILED", False, None, None, False)),
    # 2. not accepted
    ({"accepted": False, "harness_error": "CONTROLLER_RESET_MISMATCH"},
     ("INFRA", True, "CONTROLLER_RESET_MISMATCH", "HARNESS_NOT_SUBMITTED", False)),
    ({"accepted": False, "nexus_refusal": "WORKER_NOT_ACCEPTED:x", "void_reason": "WORKER_NOT_ACCEPTED:x"},
     ("INFRA", True, "WORKER_NOT_ACCEPTED:x", "NEXUS_NOT_ACCEPTED", True)),
    ({"accepted": False, "nexus_refusal": "BLOCKED_EXTERNAL_TARGET_UNSUPPORTED",
      "refusal_outcome": "BLOCKED_EXTERNAL_TARGET_UNSUPPORTED"},
     ("BLOCKED_EXTERNAL_TARGET_UNSUPPORTED", True, "BLOCKED_EXTERNAL_TARGET_UNSUPPORTED", "NEXUS_NOT_ACCEPTED", True)),
    ({"accepted": False, "nexus_refusal": "GATEWAY_CONNECTION_LOST", "connection_lost": True},
     ("INFRA", True, "GATEWAY_CONNECTION_LOST", "NEXUS_NOT_ACCEPTED", True)),
    # 3-5. accepted, symmetric infra
    ({**_ACC, "connection_lost": True, "watchdog_event": True, "void_reason": "GATEWAY_CONNECTION_LOST"},
     ("INFRA", True, "GATEWAY_CONNECTION_LOST", "SYMMETRIC_INFRA", False)),
    ({**_ACC, "model_infra": ["MODEL_ATTEMPT_INFRA"]}, ("INFRA", True, None, "SYMMETRIC_INFRA", False)),
    ({**_ACC, "model_infra": ["VENV_NOT_USABLE"], "void_reason": "VENV_MISMATCH"},
     ("INFRA", True, "VENV_MISMATCH", "SYMMETRIC_INFRA", False)),
    ({**_ACC, "stuck_by_harness_timeout": True}, ("INFRA", True, None, "SYMMETRIC_INFRA", False)),
    # 6. accepted, Gateway-side error: not infra
    ({**_ACC, "connection_lost": True, "void_reason": "GATEWAY_CONNECTION_LOST"},
     ("GATEWAY_ERROR", False, "GATEWAY_CONNECTION_LOST", None, False)),
    ({**_ACC, "gateway_error": "TOOL_ERROR:nexus_task_wait"}, ("GATEWAY_ERROR", False, None, None, False)),
    ({**_ACC, "gateway_error": "STATUS_ERROR"}, ("GATEWAY_ERROR", False, None, None, False)),
    # 7. accepted, void: not infra
    ({**_ACC, "void": ["LB_STATE_CHANGED"], "void_reason": "LB_STATE_CHANGED", "model_outcome": "OK"},
     ("OK", False, "LB_STATE_CHANGED", None, False)),
    ({**_ACC, "void": ["TRACE_MISSING"], "void_reason": "TRACE_MISSING"}, ("OK", False, "TRACE_MISSING", None, False)),
    # precedence
    ({**_ACC, "interrupted": "KeyboardInterrupt", "connection_lost": True, "void": ["LB_STATE_CHANGED"],
      "void_reason": "LB_STATE_CHANGED", "gateway_error": "STATUS_ERROR"},
     ("INTERRUPTED", True, "INTERRUPTED:KeyboardInterrupt", "INTERRUPTED", False)),
    ({"accepted": False, "interrupted": "SystemExit", "harness_error": "X"},
     ("INTERRUPTED", True, "INTERRUPTED:SystemExit", "INTERRUPTED", False)),
    ({"accepted": False, "harness_error": "INSTANCE_BUSY:x", "nexus_refusal": "PRE_SUBMIT_FAILURE:y"},
     ("INFRA", True, "INSTANCE_BUSY:x", "HARNESS_NOT_SUBMITTED", False)),
    ({**_ACC, "watchdog_event": True, "gateway_error": "TOOL_ERROR:x"}, ("INFRA", True, None, "SYMMETRIC_INFRA", False)),
    ({**_ACC, "stuck_by_harness_timeout": True, "gateway_error": "TOOL_ERROR:x"},
     ("INFRA", True, None, "SYMMETRIC_INFRA", False)),
    ({**_ACC, "gateway_error": "TOOL_ERROR:x", "void": ["SNAPSHOT_MISSING"], "void_reason": "SNAPSHOT_MISSING"},
     ("GATEWAY_ERROR", False, "SNAPSHOT_MISSING", None, False)),
])
def test_classify_row_rules_and_precedence(facts, expected):
    from scripts.bench.measure_2721.common import classify_row

    verdict = classify_row(facts)
    rule = verdict["exclusion"][0] if verdict["exclusion"] else None
    assert (verdict["outcome"], verdict["infra"], verdict["void_reason"], rule, verdict["nexus_reliability"]) == \
        expected


def test_sticky_facts_are_never_cleared():
    from scripts.bench.measure_2721.common import set_fact

    row: dict = {}
    set_fact(row, "interrupted", "KeyboardInterrupt")
    set_fact(row, "interrupted", "SystemExit")
    set_fact(row, "connection_lost", True)
    set_fact(row, "connection_lost", False)
    set_fact(row, "void", "A")
    set_fact(row, "void", "B")
    set_fact(row, "void_reason", "A")
    set_fact(row, "void_reason", "B")
    assert row["facts"] == {"interrupted": "KeyboardInterrupt", "connection_lost": True, "void": ["A", "B"],
                            "void_reason": "A"}


class _InterruptThenDead(FakeGateway):
    """Ctrl-C during the first wait after acceptance; afterwards the Gateway is gone too
    (the same process group got the signal), so the cancel loses its connection."""

    def __init__(self, state_root=None):
        super().__init__()
        self.fired = False
        self.state_root = state_root

    def __call__(self, method, path, body):
        name = (body or {}).get("params", {}).get("name")
        if name == "nexus_task_wait" and not self.fired:
            self.fired = True
            raise KeyboardInterrupt("Ctrl-C")
        if self.fired and name in ("nexus_task_cancel", "nexus_task_status", "nexus_task_wait"):
            raise ConnectionResetError(54, "Connection reset by peer")
        return super().__call__(method, path, body)

    def _answer(self, name, args):
        if name == "nexus_worker_candidate" and self.state_root is not None:
            (self.state_root / "learning" / "episodes.jsonl").write_text(f"learned from {args['task_id']}\n")
        return super()._answer(name, args)


def test_interrupt_then_lost_cancel_after_acceptance_reruns_the_whole_block(manifest, tmp_path, monkeypatch):
    _fake_build(monkeypatch, {"NEXUS": _InterruptThenDead()})
    run = tmp_path / "run"
    with pytest.raises(KeyboardInterrupt):
        _runner_main(manifest, tmp_path, run)
    (row,) = [r for r in read_jsonl(run / "rows.jsonl") if r["arm"] == "NEXUS"]
    assert row["facts"]["interrupted"] == "KeyboardInterrupt" and row["facts"]["connection_lost"]
    assert row["outcome"] == "INTERRUPTED" and row["infra"] and row["void_reason"] == "INTERRUPTED:KeyboardInterrupt"
    before = {r["run_id"] for r in read_jsonl(run / "rows.jsonl")}
    _fake_build(monkeypatch, {"NEXUS": FakeGateway()})
    assert _runner_main(manifest, tmp_path, run) == 0
    blocks = list(read_jsonl(run / "blocks.jsonl"))
    assert [(b["attempt"], b["status"]) for b in blocks] == [(0, "RERUN"), (1, "COMPLETE")]
    assert blocks[0]["infra_why"]["NEXUS"] == "CRASHED"
    assert set(blocks[1]["run_ids"]) == {"BARE", "NEXUS", "NOOP"} and not set(blocks[1]["run_ids"].values()) & before


def test_interrupt_with_an_lb_state_change_reruns_the_whole_block(manifest, tmp_path, monkeypatch):
    state_root, snapshot = tmp_path / "state", tmp_path / "snapshot"
    (snapshot / "learning").mkdir(parents=True)
    (snapshot / "learning" / "episodes.jsonl").write_text("phase start\n")
    state_root.mkdir()
    gateways = {"current": _InterruptThenDead(state_root)}

    def build(args, parser):
        client = nexus_driver.GatewayClient("http://127.0.0.1:18766", "tok-123", transport=gateways["current"])
        return nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s", sleep=lambda _s: None,
                                           state_root=state_root, state_snapshot=snapshot,
                                           state_dir=state_root / "tasks", learning_phase="LB")

    monkeypatch.setattr(nexus_driver, "build_driver", build)
    run = tmp_path / "run"
    with pytest.raises(KeyboardInterrupt):
        _runner_main(manifest, tmp_path, run)
    (row,) = [r for r in read_jsonl(run / "rows.jsonl") if r["arm"] == "NEXUS"]
    assert "LB_STATE_CHANGED" in row["facts"]["void"] and row["facts"]["interrupted"]
    assert row["outcome"] == "INTERRUPTED" and row["infra"]  # the interrupt wins over the L-B change
    gateways["current"] = FakeGateway()
    assert _runner_main(manifest, tmp_path, run) == 0
    blocks = list(read_jsonl(run / "blocks.jsonl"))
    assert [(b["attempt"], b["status"]) for b in blocks] == [(0, "RERUN"), (1, "COMPLETE")]
    assert blocks[0]["infra_why"]["NEXUS"] == "CRASHED"


def _excluded_block_run(run: Path, *, crashed: str | None = None) -> None:
    """A block excluded after re-runs whose final rows all say ``infra: false``
    (the exclusion came from a late watchdog event); ``crashed`` left no row."""
    arms_ = ["BARE", "NEXUS", "NOOP"]
    run.mkdir(parents=True)
    rows, progress = [], []
    for attempt in range(3):
        for arm in arms_:
            if attempt == 2 and arm == crashed:
                progress.append({"event": "start", "block": 0, "attempt": attempt, "arm": arm, "slot": 0})
                continue
            run_id = f"{arm}-a{attempt}"
            rows.append({"arm": arm, "run_id": run_id, "task_id": "pkg-100", "repeat": 1, "infra": False,
                         "outcome": "OK", "empty": True, "diff_sha256": blind.sha256_text("")})
            progress.append({"block": 0, "attempt": attempt, "arm": arm, "slot": 0, "run_id": run_id,
                             "infra": False})
    late = {arm: "WATCHDOG_EVENT" for arm in arms_ if arm != crashed} | ({crashed: "CRASHED"} if crashed else {})
    blocks = [{"block": 0, "task_id": "pkg-100", "repeat": 1, "attempt": a, "status": s, "arm_order": arms_,
               "infra_arms": ["NEXUS"], "infra_why": {"NEXUS": "WATCHDOG_EVENT"}}
              for a, s in ((0, "RERUN"), (1, "RERUN"), (2, "COMPLETE"))]
    blocks.append(dict(blocks[-1], status="EXCLUDED_AFTER_RERUNS", late_infra=late))
    for name, records in (("rows.jsonl", rows), ("progress.jsonl", progress), ("blocks.jsonl", blocks)):
        (run / name).write_text("".join(json.dumps(r) + "\n" for r in records))


@pytest.mark.parametrize("crashed", [None, "NEXUS"])
def test_excluded_block_never_reaches_the_scorer(tmp_path, crashed):
    """Gemini F2a/F2b (1d, 2026-10-20): the final attempt of an EXCLUDED_AFTER_RERUNS
    block is not counted even with ``infra: false`` rows, and every arm of it -- one
    that crashed without a row too -- gets an infra exclusion the scorer can explain."""
    from scripts.bench.measure_2721 import runner

    run = tmp_path / "run"
    _excluded_block_run(run, crashed=crashed)
    outcome = runner.block_outcomes(run)
    assert outcome["counted"] == set()
    assert len(outcome["excluded_blocks"]) == 1
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("")
    out, amap_path = tmp_path / "blind", tmp_path / "custody" / "map.json"
    blind.main(["--run-roots", str(run), "--out", str(out), "--arm-map", str(amap_path),
                "--manifest", str(manifest)])
    amap = json.loads(amap_path.read_text())
    assert amap["map"] == {}
    assert sorted(e["arm"] for e in amap["excluded"]) == ["BARE", "NEXUS", "NOOP"]
    assert all(e["infra"] is True and e["reason"].startswith("EXCLUDED_AFTER_RERUNS:") for e in amap["excluded"])
    assert sorted(d["reason"] for d in amap["dropped"]) == ["RERUN_SUPERSEDED"] * 6


def test_late_watchdog_event_on_a_counted_row_excludes_it(manifest, tmp_path, monkeypatch):
    """A watchdog event written after the runner last looked still makes the row infra."""
    from scripts.bench.measure_2721 import runner, watchdog

    _fake_build(monkeypatch, {"NEXUS": FakeGateway()})
    run = tmp_path / "run"
    assert _runner_main(manifest, tmp_path, run) == 0
    nexus_row = next(r for r in read_jsonl(run / "rows.jsonl") if r["arm"] == "NEXUS")
    assert nexus_row["run_id"] in runner.block_outcomes(run)["counted"]
    events = watchdog._run_dir(run) / "infra_events.jsonl"
    events.parent.mkdir(parents=True, exist_ok=True)
    events.write_text(json.dumps({"row_id": nexus_row["run_id"], "reason": "GATEWAY_KILLED"}) + "\n")
    out, amap_path = tmp_path / "blind", tmp_path / "custody" / "map.json"
    blind.main(["--run-roots", str(run), "--out", str(out), "--arm-map", str(amap_path),
                "--manifest", str(manifest)])
    amap = json.loads(amap_path.read_text())
    assert [(e["arm"], e["reason"]) for e in amap["excluded"]] == [("NEXUS", "WATCHDOG_EVENT_LATE")]
    assert sorted(m["arm"] for m in amap["map"].values()) == ["BARE", "NOOP"]


@pytest.mark.parametrize("arm", ["NOOP", "NEXUS_NOOP"])
def test_noop_nonempty_diff_is_recorded_from_any_attempt(tmp_path, arm):
    """PREREG v0.9.7 (layer1-rie): any NOOP / NEXUS_NOOP row with a non-empty diff --
    here in a superseded attempt of an excluded block -- is listed in the arm map."""
    run = tmp_path / "run"
    _excluded_block_run(run)
    rows = list(read_jsonl(run / "rows.jsonl"))
    diff = run / "diffs" / "x.diff"
    diff.parent.mkdir()
    diff.write_text("diff --git a/x.py b/x.py\n+edit\n")
    rows.append({"arm": arm, "run_id": f"{arm}-extra", "task_id": "pkg-100", "repeat": 1, "infra": False,
                 "diff_path": str(diff)})
    rows.append({"arm": arm, "run_id": f"{arm}-clean", "task_id": "pkg-100", "repeat": 1, "infra": False,
                 "empty": True, "diff_sha256": blind.sha256_text("")})
    # No diff file and no proof of an empty diff: counted as a hit (fail closed).
    rows.append({"arm": arm, "run_id": f"{arm}-unproven", "task_id": "pkg-100", "repeat": 1, "infra": False})
    # An empty (truncated) diff file whose row says it was not empty: a hit.
    truncated = run / "diffs" / "t.diff"
    truncated.write_text("")
    rows.append({"arm": arm, "run_id": f"{arm}-truncated", "task_id": "pkg-100", "repeat": 1, "infra": False,
                 "diff_path": str(truncated), "empty": False, "diff_sha256": "cd" * 32})
    # A diff with no row (killed between the diff and the row), and an empty orphan.
    (run / "diffs" / f"m2721-{arm.lower()}-pkg-100-r1-orphan.diff").write_text("+x\n")
    (run / "diffs" / f"m2721-{arm.lower()}-pkg-100-r1-blank.diff").write_text("")
    (run / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("")
    amap_path = tmp_path / "custody" / "map.json"
    rc = blind.main(["--run-roots", str(run), "--out", str(tmp_path / "blind"), "--arm-map", str(amap_path),
                     "--manifest", str(manifest)])
    # A hit voids the run: exit 3, nothing for the scorer, the arm map in custody (0600).
    assert rc == 3 and not (tmp_path / "blind" / "candidates.jsonl").exists()
    assert stat.S_IMODE(amap_path.stat().st_mode) == 0o600
    hits = json.loads(amap_path.read_text())["noop_nonempty_diff"]
    assert [(h["arm"], h["run_id"]) for h in hits] == [
        (arm, f"{arm}-extra"), (arm, f"{arm}-unproven"), (arm, f"{arm}-truncated"),
        (arm, f"m2721-{arm.lower()}-pkg-100-r1-orphan")]
    assert hits[0]["diff_sha256"] == blind.sha256_text("diff --git a/x.py b/x.py\n+edit\n")
    assert hits[3]["orphan"] is True


def test_blind_refuses_a_non_empty_out_dir(tmp_path):
    """A stale candidates.jsonl in --out must never be scored as this run's (1d)."""
    run = tmp_path / "run"
    _excluded_block_run(run)
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("")
    out = tmp_path / "blind"
    out.mkdir()
    (out / "candidates.jsonl").write_text("{}\n")
    with pytest.raises(SystemExit):
        blind.main(["--run-roots", str(run), "--out", str(out), "--arm-map", str(tmp_path / "c" / "m.json"),
                    "--manifest", str(manifest)])
    assert not (tmp_path / "c" / "m.json").exists()


def test_venv_asymmetry_between_bare_and_nexus_is_caught(tmp_path):
    """v0.9.8 (layer1-rie): the same task's BARE and NEXUS Claude rows must report the
    same task venv; a None on one side (35 gate 1: BARE VENV_MISMATCH) is a mismatch."""
    from scripts.bench.measure_2721 import runner

    run = tmp_path / "run"
    run.mkdir()
    entries = [{"arm": "BARE", "run_id": "b"}, {"arm": "NEXUS", "run_id": "n"}, {"arm": "NOOP", "run_id": "o"}]

    def write(bare_venv, nexus_venv, *, claude=True):
        extra = {"claude_version": "2.0"} if claude else {}
        rows = [{"run_id": "b", "arm": "BARE", "venv": bare_venv, **extra},
                {"run_id": "n", "arm": "NEXUS", "venv": nexus_venv, **extra},
                {"run_id": "o", "arm": "NOOP"}]
        (run / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    write("/m/venvs/t", "/m/venvs/t")
    assert runner.venv_asymmetry(run, entries) is None
    write(None, "/m/venvs/t")
    assert runner.venv_asymmetry(run, entries) == {"BARE": None, "NEXUS": "/m/venvs/t"}
    write("/m/venvs/a", "/m/venvs/b")
    assert runner.venv_asymmetry(run, entries) == {"BARE": "/m/venvs/a", "NEXUS": "/m/venvs/b"}
    write(None, "/m/venvs/t", claude=False)  # no Claude run on either side (fake provider): nothing to compare
    assert runner.venv_asymmetry(run, entries) is None


def test_venv_missing_on_both_sides_stops_when_the_task_has_one(tmp_path):
    """1d L2: no venv in BARE and NEXUS although the task has one -- stop, do not burn re-runs."""
    from scripts.bench.measure_2721 import runner

    run = tmp_path / "run"
    run.mkdir()
    rows = [{"run_id": "b", "arm": "BARE", "venv": None, "claude_version": "2"},
            {"run_id": "n", "arm": "NEXUS", "venv": None, "claude_version": "2"}]
    (run / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    entries = [{"arm": "BARE", "run_id": "b"}, {"arm": "NEXUS", "run_id": "n"}]
    assert runner.venv_asymmetry(run, entries, "/m/venvs/t") == {"BARE": None, "NEXUS": None,
                                                                 "task_venv": "/m/venvs/t"}
    assert runner.venv_asymmetry(run, entries, None) is None


def test_a_fatal_stop_is_never_resumed(manifest, tmp_path, monkeypatch, capsys):
    """1d M1: a VENV_ASYMMETRY stop must not be washed out by a resume."""
    from scripts.bench.measure_2721 import runner

    _fake_build(monkeypatch, {"NEXUS": FakeGateway()})
    run = tmp_path / "run"
    assert _runner_main(manifest, tmp_path, run) == 0
    (run / runner.FATAL_STOP_FILE).write_text(json.dumps({"reason": "VENV_ASYMMETRY"}))
    capsys.readouterr()
    assert _runner_main(manifest, tmp_path, run) == 2
    assert "FATAL_STOP_NOT_RESUMABLE" in capsys.readouterr().out


def test_card_objective_fits_the_gateway_limit_for_a_4000_character_what(tmp_path):
    """35, formal M block 3: a ``what`` of 4000 characters plus the row suffix went over the
    Gateway's 4000-character objective limit (PRE_SUBMIT_FAILURE on every long task)."""
    client = nexus_driver.GatewayClient("http://127.0.0.1:18766", "tok-123", transport=FakeGateway())
    driver = nexus_driver.NexusArmDriver(client, campaign_id="c", goal_id="g", scope_id="s")
    task = {"text": {"what": "w" * 4000, "why": "y", "allowed_files": ["a.py"], "verifier_commands": ["true"]}}
    gw_task = "m2721-nexus-pkg-100-r3-abcdef"
    args = driver.card_args(task, gw_task, repeat=3)
    assert len(args["objective"]) <= nexus_driver.CARD_OBJECTIVE_MAX == 4000
    assert args["objective"].endswith(f"Measurement row {gw_task} (repeat 3).")
    assert args["objective"].startswith("w" * 3900)
    # Short tasks and the no-repeat form are unchanged.
    short = {"text": {**task["text"], "what": "fix it"}}
    assert driver.card_args(short, gw_task, repeat=1)["objective"] == f"fix it\n\nMeasurement row {gw_task} (repeat 1)."
    assert driver.card_args(task, gw_task)["objective"] == "w" * 4000
    # The worker gets the full what (the prompt is unchanged).
    assert driver.worker_args(task, gw_task, "card.md", "h", external=False)["what"] == "w" * 4000


def test_gateway_task_id_fits_the_gateway_bound_and_stays_unique():
    """The card and worker task_id take at most 80 characters (the old 96 cut also dropped
    the repeat and random part of a long run id)."""
    import re as _re

    long_task = "some-org__a-rather-long-repository-name-" + "x" * 60
    ids = {nexus_driver.gateway_task_id(arms.new_run_id(arm, long_task, repeat))
           for arm in ("NEXUS", "NEXUS_NOOP") for repeat in (1, 2, 3)}
    assert len(ids) == 6
    for gw in ids:
        assert len(gw) <= nexus_driver.GATEWAY_TASK_ID_MAX == 80
        assert _re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", gw)
    short = arms.new_run_id("NEXUS", "pkg-100", 1)
    assert nexus_driver.gateway_task_id(short) == short  # short ids unchanged


def test_pytest_temp_dirs_are_dropped_from_a_captured_diff_in_every_arm():
    """35, formal M-main2: pytest's basetemp (pytest-of-<user>/..., pytest-current) landed in
    a NEXUS Target worktree and in its diff, with a .env file; tool output, not an edit."""
    from scripts.bench.measure_2721.leakage import drop_tool_artifacts

    edit = "diff --git a/src/pkg/mod.py b/src/pkg/mod.py\n--- a/src/pkg/mod.py\n+++ b/src/pkg/mod.py\n@@ -1 +1 @@\n-a\n+b\n"
    junk = ("diff --git a/pytest-of-someone/pytest-0/test_x0/.env b/pytest-of-someone/pytest-0/test_x0/.env\n"
            "new file mode 100644\n--- /dev/null\n+++ b/pytest-of-someone/pytest-0/test_x0/.env\n@@ -0,0 +1 @@\n+K=v\n"
            "diff --git a/pytest-current b/pytest-current\nnew file mode 120000\n--- /dev/null\n"
            "+++ b/pytest-current\n@@ -0,0 +1 @@\n+pytest-of-someone/pytest-0\n\\ No newline at end of file\n")
    diff, removed = drop_tool_artifacts(edit + junk)
    assert diff == edit
    assert removed == ["pytest-of-someone/pytest-0/test_x0/.env", "pytest-current"]
    # Nothing else is touched: a real path that only looks alike stays.
    lookalike = edit.replace("src/pkg/mod.py", "src/pytest-of-docs.py")
    assert drop_tool_artifacts(lookalike) == (lookalike, [])
    assert drop_tool_artifacts("") == ("", [])


@needs_sandbox
def test_worker_sandbox_temp_dir_is_the_same_in_both_arms(manifest, tmp_path):
    """1d, M-main2: zero-model reproduction. Inside the worker sandbox Python resolves its
    temp dir to the run's own tmp (outside the Target) in BARE and NEXUS alike (the
    fixture venv has no pytest, so the pytest call itself is not asserted here)."""
    dryrun.dry_run(manifest, tmp_path / "dry", file_scope=True, fake_mode="tmpprobe")
    probes = {}
    for stream in (tmp_path / "dry" / "traces").glob("*/*.stream.jsonl"):
        for line in stream.read_text().splitlines():
            if '"tmp_probe"' in line:
                arm = "BARE" if stream.parent.name.startswith("m2721-bare-") else "NEXUS"
                probes[arm] = json.loads(line)["tmp_probe"]
    assert set(probes) == {"BARE", "NEXUS"}, probes
    for arm, probe in probes.items():
        tmp = os.path.realpath(probe["TMPDIR"])
        assert probe["TMPDIR"] and Path(tmp).name == "tmp", (arm, probe)
        assert os.path.realpath(probe["gettempdir"]) == tmp, (arm, probe)
        assert not tmp.startswith(os.path.realpath(probe["cwd"])), (arm, probe)
        assert probe["cwd_pytest_dirs"] == [], (arm, probe)
    # Same shape in both arms: the adapter's per-run tmp, which tempfile actually uses.
    assert {k for k, v in probes["BARE"].items() if v} == {k for k, v in probes["NEXUS"].items() if v}
