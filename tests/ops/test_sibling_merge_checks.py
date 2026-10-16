"""Reusable sibling merge checks (#2385): workflow shape and bindings script."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REUSABLE = ROOT / ".github" / "workflows" / "sibling-merge-checks.yml"
CALLER = ROOT / "docs" / "ops" / "sibling-merge-checks-caller.yml"
SCRIPT = ROOT / "scripts" / "ops" / "sibling_bindings_check.py"
GATE = ROOT / "scripts" / "ops" / "trusted_merge_lane_gate.py"


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _triggers(doc: dict) -> dict:
    # PyYAML parses the bare key `on` as boolean True.
    return doc["on"] if "on" in doc else doc[True]


def test_reusable_is_call_only_and_tools_come_from_nexus_new_main() -> None:
    doc = _yaml(REUSABLE)
    assert set(_triggers(doc)) == {"workflow_call"}
    assert doc["permissions"] == {}
    checkouts = [
        step["with"]
        for job in doc["jobs"].values()
        for step in job["steps"]
        if "actions/checkout" in step.get("uses", "")
    ]
    tools = [c for c in checkouts if c.get("repository") == "James3014/Nexus-new"]
    assert len(tools) == 2 and all(c["ref"] == "main" for c in tools)
    assert all(c["persist-credentials"] is False for c in checkouts)
    target = [c for c in checkouts if "repository" not in c]
    assert target == [
        {
            "ref": "${{ github.event.repository.default_branch }}",
            "path": "target",
            "fetch-depth": 0,
            "persist-credentials": False,
        }
    ]
    text = REUSABLE.read_text(encoding="utf-8")
    for forbidden in (
        "git checkout",
        "git switch",
        "pip install",
        "uv sync",
        "PYTHONPATH",
        "git -c ",
    ):
        assert forbidden not in text


def test_reusable_bindings_job_fails_closed_and_publishes_status() -> None:
    job = _yaml(REUSABLE)["jobs"]["bindings"]
    assert job["env"]["CONTEXT"] == "Bindings preflight (default branch)"
    names = [s.get("name", "") for s in job["steps"]]
    assert names[0] == "Mark the status pending before anything can fail"
    assert "^[0-9a-f]{40}$" in job["steps"][0]["run"]
    inputs = _triggers(_yaml(REUSABLE))["workflow_call"]["inputs"]
    assert inputs["run_bindings"]["default"] is False
    run = job["steps"][-1]["run"]
    assert "python3 -I nexus-tools/scripts/ops/sibling_bindings_check.py" in run
    assert "! grep -q '^PASS  bindings'" in run
    assert run.rstrip().endswith('exit "$rc"')
    # GitHub runs `bash -e`; without `set +e` a FAIL would abort before posting the status
    assert "set +e -uo pipefail" in run
    assert run.index("::stop-commands::") < run.index('cat "$out"')


def test_caller_template_calls_main_with_least_privilege() -> None:
    doc = _yaml(CALLER)
    assert set(_triggers(doc)) == {"pull_request_target", "issue_comment"}
    assert "pull_request" not in _triggers(doc)
    assert _triggers(doc)["pull_request_target"]["branches"] == ["main"]
    job = doc["jobs"]["checks"]
    assert job["uses"] == "James3014/Nexus-new/.github/workflows/sibling-merge-checks.yml@main"
    assert job["permissions"] == {
        "contents": "read",
        "issues": "read",
        "pull-requests": "read",
        "statuses": "write",
    }
    assert job["with"]["run_bindings"] == "${{ github.event_name == 'pull_request_target' }}"


def _repo(tmp_path: Path, message: str) -> tuple[Path, str]:
    repo = tmp_path / "r"
    repo.mkdir()
    env = ["-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), *env, "commit", "-q", "--allow-empty", "-m", "base"], check=True
    )
    subprocess.run(["git", "-C", str(repo), "branch", "base"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), *env, "commit", "-q", "--allow-empty", "-m", message], check=True
    )
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    )
    return repo, head.stdout.strip()


def _run(tmp_path: Path, body: str, message: str) -> tuple[int, str]:
    repo, head = _repo(tmp_path, message)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    pr = {"head": {"sha": head}, "body": body, "title": "t"}
    (bindir / "gh").write_text(f"#!/bin/sh\ncat <<'J'\n{json.dumps(pr)}\nJ\n", encoding="utf-8")
    (bindir / "gh").chmod(0o755)
    proc = subprocess.run(
        [
            sys.executable,
            "-I",
            str(SCRIPT),
            "--repo",
            "o/r",
            "--repo-dir",
            str(repo),
            "--pr",
            "7",
            "--head",
            head,
            "--base-ref",
            "base",
            "--gate",
            str(GATE),
        ],
        capture_output=True,
        text=True,
        env={"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(tmp_path)},
    )
    return proc.returncode, proc.stdout


INTENT_CLOSE = (
    '<!-- NEXUS_ISSUE_INTENT_V1\n[{"issue": 5, "on_merge": "CLOSE"}]\nNEXUS_ISSUE_INTENT_V1 -->'
)
INTENT_KEEP = (
    '<!-- NEXUS_ISSUE_INTENT_V1\n[{"issue": 5, "on_merge": "KEEP_OPEN"}]\nNEXUS_ISSUE_INTENT_V1 -->'
)


def test_closes_with_close_intent_passes(tmp_path: Path) -> None:
    rc, out = _run(tmp_path, f"Closes #5\n{INTENT_CLOSE}", "fix\n\nCloses #5.")
    assert rc == 0 and out.startswith("PASS  bindings")


def test_closes_without_intent_fails(tmp_path: Path) -> None:
    rc, out = _run(tmp_path, "Closes #5", "fix")
    assert rc == 1 and "UNINTENDED_CLOSING_KEYWORD" in out


def test_keep_open_with_closes_in_commit_message_fails(tmp_path: Path) -> None:
    rc, out = _run(tmp_path, f"Refs #5\n{INTENT_KEEP}", "fix\n\nCloses #5.")
    assert rc == 1 and out.startswith("FAIL  bindings")


def test_no_keywords_passes(tmp_path: Path) -> None:
    rc, out = _run(tmp_path, "Refs #5, test-only", "test")
    assert rc == 0 and out.startswith("PASS  bindings")


def test_head_mismatch_fails_closed(tmp_path: Path) -> None:
    repo, head = _repo(tmp_path, "x")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    pr = {"head": {"sha": "f" * 40}, "body": "Refs #5", "title": "t"}
    (bindir / "gh").write_text(f"#!/bin/sh\ncat <<'J'\n{json.dumps(pr)}\nJ\n", encoding="utf-8")
    (bindir / "gh").chmod(0o755)
    args = [
        sys.executable,
        "-I",
        str(SCRIPT),
        "--repo",
        "o/r",
        "--repo-dir",
        str(repo),
        "--pr",
        "7",
    ]
    args += ["--head", head, "--base-ref", "base", "--gate", str(GATE)]
    proc = subprocess.run(
        args, capture_output=True, text=True, env={"PATH": f"{bindir}:/usr/bin:/bin"}
    )
    assert proc.returncode == 1 and "HEAD_MOVED" in proc.stdout
