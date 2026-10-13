"""Tests for scripts/ops/pr_preflight.py (nexus-pr-preflight, #1916).

Each failure class from the #1916 sample has a fixture that reproduces it in a
throwaway Git repository whose base commit carries the real trusted gate
scripts, so the checks exercise the same validators CI runs.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "ops" / "pr_preflight.py"
WRAPPER = ROOT / "scripts" / "ops" / "nexus-pr-preflight"
TRUSTED = (
    "scripts/ops/trusted_merge_lane_gate.py",
    "scripts/ops/trusted_deletion_anchor.py",
    "scripts/ops/exact_base_tool_gate.py",
)
MARKER = "sha256:" + "a" * 64
OTHER_MARKER = "sha256:" + "b" * 64


def _load():
    spec = importlib.util.spec_from_file_location("pr_preflight_under_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pf = _load()


def _git(repo: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env
    ).stdout.strip()


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-verify", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Base commit on origin/main with the real trusted scripts; HEAD on a branch."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "remote", "add", "origin", "https://github.com/James3014/Nexus-new.git")
    for rel in TRUSTED:
        _write(root, rel, (ROOT / rel).read_text(encoding="utf-8"))
    _write(root, "pyproject.toml", '[project]\nname = "fixture"\nversion = "0"\n')
    _write(root, "uv.lock", "version = 1\n")
    _write(root, "tests/test_ok.py", "def test_ok():\n    assert True\n")
    _write(root, "nexus/__init__.py", "")
    _write(root, "nexus/mod.py", "VALUE = 1\n")
    base = _commit(root, "base")
    _git(root, "update-ref", "refs/remotes/origin/main", base)
    _git(root, "checkout", "-q", "-b", "feature")
    _write(root, "docs/note.md", "note\n")
    _commit(root, "feature work")
    return root


def _body(issue: int = 1916, *, intent: str = "CLOSE", closes: bool = True, lane: str = "") -> str:
    prose = f"Closes #{issue}.\n\n" if closes else f"#{issue} remains open.\n\n"
    return (
        prose
        + f"<!-- NEXUS_CORE_ISSUE: {issue} -->\n\n"
        + "<!-- NEXUS_ISSUE_INTENT_V1\n"
        + json.dumps([{"issue": issue, "on_merge": intent}])
        + "\nNEXUS_ISSUE_INTENT_V1 -->\n"
        + lane
    )


@pytest.fixture
def fake_certify(tmp_path: Path) -> Path:
    """A stand-in for `nexus-certify markers` that prints a fixed marker."""
    script = tmp_path / "nexus-certify"
    payload = json.dumps({
        "issue_marker": f"<!-- NEXUS_CORE_EVIDENCE_UNIVERSE: {MARKER} -->",
        "pr_marker": "<!-- NEXUS_CORE_ISSUE: 1916 -->",
    })
    script.write_text(
        "#!/bin/sh\n"
        'if [ "$2" = "--help" ]; then echo "usage: markers [--json]"; exit 0; fi\n'
        f"cat <<'EOF'\n{payload}\nEOF\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _run(repo: Path, tmp_path: Path, *args: str, body: str | None = None, issue=None, certify=None):
    argv = ["--repo", str(repo), "--no-fetch", "--json", "--skip-static"]
    if body is not None:
        body_file = tmp_path / "body.md"
        body_file.write_text(body, encoding="utf-8")
        argv += ["--body-file", str(body_file)]
    if issue is not None:
        issue_file = tmp_path / "issue.json"
        issue_file.write_text(json.dumps(issue), encoding="utf-8")
        argv += ["--issue-json", str(issue_file)]
    if certify is not None:
        argv += ["--nexus-certify", str(certify)]
    return list(argv) + list(args)


def _report(capsys, argv) -> tuple[int, dict]:
    code = pf.main(argv)
    return code, json.loads(capsys.readouterr().out)


def _check(report: dict, name: str) -> dict:
    return next(c for c in report["checks"] if c["check"] == name)


# ---------------------------------------------------------------- bindings


def test_missing_core_issue_marker_fails_and_prints_blocks(repo, tmp_path, capsys):
    body = "Closes #1916.\n\nsummary only\n"
    code, report = _report(capsys, _run(repo, tmp_path, "--issue", "1916", body=body))
    check = _check(report, "bindings")
    assert code == 1
    assert check["status"] == "FAIL"
    assert check["code"] == pf.PR_MISSING_CORE_ISSUE_BINDING
    blocks = report["suggested_blocks"]
    assert blocks["core_issue"] == "<!-- NEXUS_CORE_ISSUE: 1916 -->"
    assert '"on_merge": "CLOSE"' in blocks["issue_intent"]
    assert all("NEXUS_MERGE_LANE_V1" not in block for block in blocks.values())


def test_duplicate_core_issue_marker_fails(repo, tmp_path, capsys):
    body = _body() + "\n<!-- NEXUS_CORE_ISSUE: 7 -->\n"
    _code, report = _report(capsys, _run(repo, tmp_path, body=body))
    assert _check(report, "bindings")["code"] == pf.PR_MISSING_CORE_ISSUE_BINDING


def test_closing_keyword_for_keep_open_issue_fails(repo, tmp_path, capsys):
    body = _body(intent="KEEP_OPEN", closes=True)
    _code, report = _report(capsys, _run(repo, tmp_path, body=body))
    check = _check(report, "bindings")
    assert check["status"] == "FAIL"
    assert check["code"] == "REJECTED_CLOSING_KEYWORD_FOR_KEEP_OPEN"


def test_close_intent_without_closing_prose_fails(repo, tmp_path, capsys):
    _code, report = _report(capsys, _run(repo, tmp_path, body=_body(closes=False)))
    assert _check(report, "bindings")["code"] == "MISSING_EXPLICIT_CLOSING_DECLARATION"


def test_commit_message_closing_untracked_issue_fails(repo, tmp_path, capsys):
    _write(repo, "docs/other.md", "x\n")
    _commit(repo, "fix stuff\n\nFixes #42")
    _code, report = _report(capsys, _run(repo, tmp_path, body=_body()))
    check = _check(report, "bindings")
    assert check["code"] == "UNINTENDED_CLOSING_KEYWORD_FOR_UNTRACKED_ISSUE"


def test_good_bindings_pass(repo, tmp_path, capsys):
    _code, report = _report(capsys, _run(repo, tmp_path, body=_body()))
    assert _check(report, "bindings")["status"] == "PASS"


def test_no_body_skips_body_checks(repo, tmp_path, capsys):
    _code, report = _report(capsys, _run(repo, tmp_path, "--only", "bindings,merge_lane"))
    assert {c["status"] for c in report["checks"]} == {"SKIP"}


# -------------------------------------------------------------- merge lane


def test_missing_lane_block_fails_without_minting(repo, tmp_path, capsys):
    code, report = _report(capsys, _run(repo, tmp_path, "--only", "merge_lane", body=_body()))
    check = _check(report, "merge_lane")
    assert code == 1
    assert check["status"] == "FAIL"
    assert check["code"] == pf.MERGE_LANE_BINDING_MISSING
    assert "binding_hash" not in json.dumps(report)


def test_missing_lane_block_is_skip_when_owner_pending(repo, tmp_path, capsys):
    argv = _run(repo, tmp_path, "--only", "merge_lane", "--lane-owner-pending", body=_body())
    code, report = _report(capsys, argv)
    assert code == 0
    assert _check(report, "merge_lane")["status"] == "SKIP"


def test_malformed_lane_block_fails(repo, tmp_path, capsys):
    lane = "<!-- NEXUS_MERGE_LANE_V1\n{not json\nNEXUS_MERGE_LANE_V1 -->\n"
    argv = _run(repo, tmp_path, "--only", "merge_lane", body=_body(lane=lane))
    _code, report = _report(capsys, argv)
    check = _check(report, "merge_lane")
    assert check["code"] == "MERGE_LANE_BINDING_JSON_INVALID"
    assert check["data"] == {"present": True, "parses": False}


def test_lane_block_with_bad_hash_is_rejected_by_trusted_gate(repo, tmp_path, capsys):
    binding = {
        "schema": "nexus.merge_lane_binding.v1",
        "execution_lane": "DIRECT_CANONICAL",
        "contract_kind": "OWNER_INLINE",
        "owner_id": "James3014",
        "issue_number": None,
        "task_id": None,
        "attempt_id": None,
        "task_card_path": None,
        "task_card_sha256": None,
        "owner_lane_rebind": None,
        "binding_hash": "0" * 64,
    }
    lane = "<!-- NEXUS_MERGE_LANE_V1\n" + json.dumps(binding) + "\nNEXUS_MERGE_LANE_V1 -->\n"
    argv = _run(repo, tmp_path, "--only", "merge_lane", body=_body(lane=lane))
    _code, report = _report(capsys, argv)
    check = _check(report, "merge_lane")
    assert check["status"] == "FAIL"
    assert check["code"] == "BINDING_HASH_INVALID"
    assert check["data"] == {"present": True, "parses": True}


def _inline_lane(contract_kind: str) -> str:
    binding = {
        "schema": "nexus.merge_lane_binding.v1",
        "execution_lane": "DIRECT_CANONICAL",
        "contract_kind": contract_kind,
        "owner_id": "James3014",
        "issue_number": None,
        "task_id": None,
        "attempt_id": None,
        "task_card_path": None,
        "task_card_sha256": None,
        "owner_lane_rebind": None,
    }
    binding["binding_hash"] = hashlib.sha256(
        json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return "<!-- NEXUS_MERGE_LANE_V1\n" + json.dumps(binding) + "\nNEXUS_MERGE_LANE_V1 -->\n"


@pytest.mark.parametrize(
    ("contract_kind", "author", "status", "code"),
    [
        ("OWNER_INLINE", None, "SKIP", "PULL_REQUEST_AUTHOR_REQUIRED"),
        ("OWNER_INLINE", "James3014", "PASS", ""),
        ("OWNER_INLINE", "app/james3014-nexus-agent", "FAIL", "OWNER_INLINE_AUTHOR_MISMATCH"),
        ("AGENT_INLINE", "app/james3014-nexus-agent", "PASS", ""),
        ("AGENT_INLINE", "James3014", "FAIL", "AGENT_INLINE_AUTHOR_NOT_ALLOWLISTED_APP"),
    ],
)
def test_inline_lane_is_checked_against_pr_author(
    repo, tmp_path, capsys, contract_kind, author, status, code
):
    extra = ["--author", author] if author else []
    argv = _run(
        repo, tmp_path, "--only", "merge_lane", *extra, body=_body(lane=_inline_lane(contract_kind))
    )
    _code, report = _report(capsys, argv)
    check = _check(report, "merge_lane")
    assert check["status"] == status
    assert check["code"] == code


# ------------------------------------------------------------------- issue


@pytest.mark.parametrize(
    ("issue", "expected_status", "expected_code"),
    [
        ({"state": "CLOSED", "body": ""}, "FAIL", pf.ISSUE_NOT_OPEN),
        ({"state": "OPEN", "body": "no marker"}, "FAIL", pf.ISSUE_MISSING_EVIDENCE_UNIVERSE),
        (
            {"state": "OPEN", "body": f"<!-- NEXUS_CORE_EVIDENCE_UNIVERSE: {OTHER_MARKER} -->"},
            "FAIL",
            pf.ISSUE_EVIDENCE_UNIVERSE_STALE,
        ),
        (
            {"state": "OPEN", "body": "<!-- NEXUS_CORE_EVIDENCE_UNIVERSE: sha256:zz -->"},
            "FAIL",
            pf.ISSUE_EVIDENCE_UNIVERSE_BINDING_MALFORMED,
        ),
        (
            {"state": "OPEN", "body": f"x\n<!-- NEXUS_CORE_EVIDENCE_UNIVERSE: {MARKER} -->\n"},
            "PASS",
            "",
        ),
    ],
)
def test_issue_readiness(
    repo, tmp_path, capsys, fake_certify, issue, expected_status, expected_code
):
    argv = _run(repo, tmp_path, "--only", "issue", body=_body(), issue=issue, certify=fake_certify)
    _code, report = _report(capsys, argv)
    check = _check(report, "issue")
    assert (check["status"], check["code"]) == (expected_status, expected_code)
    if expected_status == "FAIL" and expected_code != pf.ISSUE_NOT_OPEN:
        assert MARKER in check["fix"]


def test_issue_marker_skips_without_nexus_certify(repo, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(pf, "_resolve_nexus_certify", lambda explicit: None)
    argv = _run(
        repo, tmp_path, "--only", "issue", body=_body(), issue={"state": "OPEN", "body": ""}
    )
    _code, report = _report(capsys, argv)
    check = _check(report, "issue")
    assert (check["status"], check["code"]) == ("FAIL", pf.NEXUS_CERTIFY_UNAVAILABLE)


def _certify_script(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "nexus-certify-stub"
    script.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


_OPEN_ISSUE = {"state": "OPEN", "body": ""}


def _assert_certify_unavailable(check: dict) -> None:
    assert check["status"] == "FAIL"
    assert check["code"] == pf.NEXUS_CERTIFY_UNAVAILABLE
    assert "nexus-core-issue-completion.yml" in check["fix"]
    assert "uvx --from git+https://github.com/James3014/nexus-core@" in check["fix"]
    assert "sha256:" + "a" * 64 not in check["detail"]
    assert "NEXUS_CORE_EVIDENCE_UNIVERSE: sha256" not in check["detail"]


def test_certify_nonzero_exit_fails_unavailable(repo, tmp_path, capsys):
    stub = _certify_script(tmp_path, 'echo "INVALID_CONFIG" >&2\nexit 2\n')
    argv = _run(repo, tmp_path, "--only", "issue", body=_body(), issue=_OPEN_ISSUE, certify=stub)
    _code, report = _report(capsys, argv)
    check = _check(report, "issue")
    _assert_certify_unavailable(check)
    assert "INVALID_CONFIG" in check["detail"]


def test_certify_empty_marker_fails_unavailable(repo, tmp_path, capsys):
    stub = _certify_script(
        tmp_path,
        'if [ "$2" = "--help" ]; then exit 0; fi\n'
        'echo \'{"issue_marker": "<!-- NEXUS_CORE_EVIDENCE_UNIVERSE:  -->"}\'\n',
    )
    argv = _run(repo, tmp_path, "--only", "issue", body=_body(), issue=_OPEN_ISSUE, certify=stub)
    _code, report = _report(capsys, argv)
    _assert_certify_unavailable(_check(report, "issue"))


def test_certify_missing_issue_marker_fails_unavailable(repo, tmp_path, capsys):
    stub = _certify_script(
        tmp_path, 'if [ "$2" = "--help" ]; then exit 0; fi\necho \'{"issue_marker": ""}\'\n'
    )
    argv = _run(repo, tmp_path, "--only", "issue", body=_body(), issue=_OPEN_ISSUE, certify=stub)
    _code, report = _report(capsys, argv)
    _assert_certify_unavailable(_check(report, "issue"))


def test_certify_live_check_stale_exit_one_is_stale_not_unavailable(
    repo, tmp_path, capsys, monkeypatch
):
    payload = json.dumps({
        "issue_marker": f"<!-- NEXUS_CORE_EVIDENCE_UNIVERSE: {MARKER} -->",
        "issue_check": {"status": "STALE"},
    })
    stub = _certify_script(
        tmp_path,
        'if [ "$2" = "--help" ]; then echo "usage: markers [--json] [--check]"; exit 0; fi\n'
        f"cat <<'EOF'\n{payload}\nEOF\nexit 1\n",
    )
    stale = {"state": "OPEN", "body": f"<!-- NEXUS_CORE_EVIDENCE_UNIVERSE: {OTHER_MARKER} -->"}
    monkeypatch.setattr(pf, "_fetch_issue", lambda ctx, issue: stale)
    argv = _run(repo, tmp_path, "--only", "issue", body=_body(), certify=stub)
    _code, report = _report(capsys, argv)
    check = _check(report, "issue")
    assert (check["status"], check["code"]) == ("FAIL", pf.ISSUE_EVIDENCE_UNIVERSE_STALE)


def test_certify_valid_marker_unchanged(repo, tmp_path, capsys, fake_certify):
    issue = {"state": "OPEN", "body": f"<!-- NEXUS_CORE_EVIDENCE_UNIVERSE: {MARKER} -->\n"}
    argv = _run(repo, tmp_path, "--only", "issue", body=_body(), issue=issue, certify=fake_certify)
    _code, report = _report(capsys, argv)
    check = _check(report, "issue")
    assert (check["status"], check["code"]) == ("PASS", "")


# --------------------------------------------- freshness and git identity


def _make_behind(repo: Path) -> None:
    _git(repo, "checkout", "-q", "main")
    _write(repo, "docs/main-moved.md", "moved\n")
    moved = _commit(repo, "main moved")
    _git(repo, "update-ref", "refs/remotes/origin/main", moved)
    _git(repo, "checkout", "-q", "feature")


def test_branch_behind_main_fails_freshness_and_identity(repo, tmp_path, capsys):
    _make_behind(repo)
    argv = _run(repo, tmp_path, "--only", "freshness,git_identity")
    code, report = _report(capsys, argv)
    fresh = _check(report, "freshness")
    assert code == 1
    assert fresh["code"] == pf.BASE_REF_NOT_ANCESTOR
    assert fresh["data"]["behind"] == 1
    assert "no force-push" in fresh["fix"]
    assert _check(report, "git_identity")["code"] == pf.EXECUTOR_GIT_IDENTITY_MISMATCH


def test_fresh_branch_passes_freshness_and_identity(repo, tmp_path, capsys):
    code, report = _report(capsys, _run(repo, tmp_path, "--only", "freshness,git_identity"))
    assert code == 0
    assert {c["status"] for c in report["checks"]} == {"PASS"}


def test_export_ignored_test_file_breaks_executor_tree(repo, tmp_path, capsys):
    _write(repo, ".gitattributes", "tests/test_hidden.py export-ignore\n")
    _write(repo, "tests/test_hidden.py", "def test_hidden():\n    pass\n")
    _commit(repo, "hide a test from git archive")
    _code, report = _report(capsys, _run(repo, tmp_path, "--only", "git_identity"))
    check = _check(report, "git_identity")
    assert check["status"] == "FAIL"
    assert "tests/ tree" in check["detail"]


# ---------------------------------------------------- dependency contract


def test_dependency_drift_fails(repo, tmp_path, capsys):
    _write(repo, "uv.lock", "version = 1\n# new pin\n")
    _commit(repo, "bump lock")
    _code, report = _report(capsys, _run(repo, tmp_path, "--only", "dependency_contract"))
    check = _check(report, "dependency_contract")
    assert check["code"] == pf.DEPENDENCY_CONTRACT_DRIFT
    assert check["data"]["changed"] == ["uv.lock"]


def test_unchanged_dependency_contract_passes(repo, tmp_path, capsys):
    _code, report = _report(capsys, _run(repo, tmp_path, "--only", "dependency_contract"))
    assert _check(report, "dependency_contract")["status"] == "PASS"


# ------------------------------------------------------------ static gates


def _tools_venv() -> Path | None:
    venv = ROOT / ".venv"
    return venv if (venv / "bin" / "ruff").is_file() else None


@pytest.mark.skipif(_tools_venv() is None, reason="needs REPO/.venv with ruff")
def test_ruff_regression_prints_new_finding(repo, tmp_path, capsys):
    _write(repo, "nexus/mod.py", "import os\n\nVALUE = 1\n")
    _commit(repo, "add unused import")
    argv = [
        "--repo", str(repo), "--no-fetch", "--json", "--only", "static_ruff",
        "--tools-venv", str(_tools_venv()),
    ]  # fmt: skip
    code, report = _report(capsys, argv)
    check = _check(report, "static_ruff")
    assert code == 1
    assert check["code"] == pf.STATIC_NEW_REGRESSION
    assert any("F401" in finding for finding in check["data"]["new_findings"])
    assert not _git(repo, "worktree", "list", "--porcelain").count("nexus-pr-preflight-wt")


def test_static_gate_without_python_change_passes_without_tools(repo, tmp_path, capsys):
    argv = ["--repo", str(repo), "--no-fetch", "--json", "--only", "static_pyright"]
    argv += ["--tools-venv", str(tmp_path / "missing-venv")]
    _code, report = _report(capsys, argv)
    assert _check(report, "static_pyright")["status"] == "PASS"


def test_static_gate_with_change_but_no_tool_skips(repo, tmp_path, capsys):
    _write(repo, "nexus/mod.py", "VALUE = 2\n")
    _commit(repo, "change python")
    argv = ["--repo", str(repo), "--no-fetch", "--json", "--only", "static_bandit"]
    argv += ["--tools-venv", str(tmp_path / "missing-venv")]
    _code, report = _report(capsys, argv)
    check = _check(report, "static_bandit")
    assert check["status"] == "SKIP"
    assert "uv sync" in check["fix"]


# ------------------------------------------------------- output and drift


def test_text_output_has_one_line_fix_per_failure(repo, tmp_path, capsys):
    body_file = tmp_path / "b.md"
    body_file.write_text("no markers\n", encoding="utf-8")
    code = pf.main([
        "--repo", str(repo), "--no-fetch", "--skip-static", "--issue", "1916",
        "--only", "bindings", "--body-file", str(body_file),
    ])  # fmt: skip
    out = capsys.readouterr().out
    assert code == 1
    assert "FAIL  bindings [PR_MISSING_CORE_ISSUE_BINDING]" in out
    assert "fix: add exactly one" in out
    assert "<!-- NEXUS_CORE_ISSUE: 1916 -->" in out
    assert out.rstrip().endswith("RESULT: FAIL")


def test_wrapper_runs_isolated(repo, tmp_path):
    proc = subprocess.run(
        [str(WRAPPER), "--repo", str(repo), "--no-fetch", "--only", "freshness", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["schema"] == pf.SCHEMA


def test_static_tool_constants_match_workflows():
    """Preflight replicates workflow file selection; fail if a workflow drifts."""
    for tool, spec in pf.STATIC_TOOLS.items():
        text = (ROOT / spec["workflow"]).read_text(encoding="utf-8")
        assert " ".join(spec["trigger_files"]) in text, tool
        for pattern in spec["scope"]:
            assert f"'{pattern}'" in text, (tool, pattern)
        if spec["fallback"]:
            assert f"-- {spec['fallback']}" in text, tool
        assert "scripts/ops/exact_base_tool_gate.py" in text
    lint = (ROOT / ".github/workflows/lint.yml").read_text(encoding="utf-8")
    assert "format --check --preview --output-format json" in lint
    security = (ROOT / ".github/workflows/security.yml").read_text(encoding="utf-8")
    assert "-q -f json -ll -ii" in security


def test_core_issue_regex_matches_issue_gate_contract():
    assert pf._core_issue_markers("<!--NEXUS_CORE_ISSUE:12-->") == ["12"]
    assert pf._core_issue_markers("<!-- NEXUS_CORE_ISSUE: 0 -->") == []


def test_trusted_scripts_are_loaded_from_base_not_head(repo, tmp_path, capsys):
    # A head that rewrites the lane gate to always pass must not change the verdict.
    _write(repo, "scripts/ops/trusted_merge_lane_gate.py", "raise SystemExit('tampered')\n")
    _commit(repo, "tamper with gate")
    _code, report = _report(capsys, _run(repo, tmp_path, "--only", "bindings", body=_body()))
    assert _check(report, "bindings")["status"] == "PASS"
