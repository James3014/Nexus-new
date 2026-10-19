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
def manifest(bank: dict) -> Path:
    out = bank["root"] / "mat"
    assert materialize.main(["--tasks", str(bank["tasks"]), "--repos-root", str(bank["root"] / "repos"),
                             "--out", str(out)]) == 0
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
        assert set(item) == {"opaque_id", "task_id", "diff_sha256"}
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
    flag_tamper["observed"]["argv"][1] = "--bare"
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
def test_bare_claude_arm_runs_through_the_nexus_adapter(manifest, tmp_path):
    from scripts.bench.measure_2721.fake_claude import write_fake_claude
    from scripts.bench.measure_2721.providers import ClaudeProvider, claude_identity

    (task,) = arms.load_manifest(manifest)
    fake = write_fake_claude(tmp_path / "bin" / "claude", "edit")
    token = tmp_path / "token"
    token.write_text("tok\n")
    token.chmod(0o600)
    provider = ClaudeProvider(str(fake), tmp_path / "run" / "traces", str(token),
                              identity=claude_identity(str(fake), str(token)))
    (task_root := Path(task["base_checkout"])).joinpath("README.md").exists()
    row = arms.run_bare(task, 1, tmp_path / "run", provider, timeout_seconds=60)
    assert row["outcome"] == "OK", row
    assert row["claude_version"].startswith("0.0.0") and row["models_seen"] == ["claude-haiku-5-5"]
    assert row["cache_read_input_tokens"] == 0 and row["cache_creation_input_tokens"] == 0
    assert row["seatbelt_sha256"] and row["proxy_denied"] == []
    assert "README.md" in row["changed_paths"]
    del task_root
