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
    assert row["infra"] is True and row["gateway_stuck"] == "PENDING_HUMAN_APPROVAL"


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
    assert row["infra"] is True and row["void_reason"] == "SNAPSHOT_MISSING"


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
    assert row["infra"] is True and row["void_reason"] == "TRACE_MISSING"


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
def test_venv_probe_runs_python_and_pytest_inside_the_sandbox(manifest, tmp_path, monkeypatch):
    """8d witness item 3, zero-model: the task venv works under the adapter's sandbox."""
    import site
    import subprocess as sp
    import sys

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
    monkeypatch.setenv("NEXUS_MEASUREMENT_READ_ROOTS", ":".join((str(venv.parent), str(base_prefix))))
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
    assert all(r["infra"] and r["void_reason"] == "LB_STATE_CHANGED" for r in rows), rows
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
    assert row["outcome"] == "GATEWAY_ERROR" and not row["infra"] and row["submitted"] is True
    # The scorer gets it as a candidate that cannot count as solved.
    assert blind.run_invalid_reason(row) == "OUTCOME:GATEWAY_ERROR"


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
    _controller_driver(
        FakeGateway(),
        layout,
        state_root=outside,
        gateway_state_paths={"NEXUS_STATE_ROOT": str(outside)},
    )


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
    # Row 2 started from the phase start: row 1's learning and assist job were restored away ...
    assert (hosted / "memory.json").read_text().endswith(f'{rows[1]["gateway_task_id"]}"}}')
    jobs = sorted(p.name for p in (hosted / "assisted_provider_jobs").glob("*.json"))
    assert jobs == sorted(["old-job.json", f"{rows[1]['gateway_task_id']}.json"])
    # ... but the probe evidence of both rows is kept and never hashed.
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
