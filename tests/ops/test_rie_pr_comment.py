"""Repository Intelligence sticky PR comment (Owner decision 2026-10-13)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ops import rie_pr_comment as rpc

ROOT = Path(__file__).resolve().parents[2]
COMMENT_WORKFLOW = ROOT / ".github/workflows/repository-intelligence-comment.yml"
SNAPSHOT_WORKFLOW = ROOT / ".github/workflows/repository-intelligence.yml"


# ------------------------------------------------------------- sanitizing


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("scripts/ops/a.py", "scripts/ops/a.py"),
        ("a`b`c", "a'b'c"),
        ("line\nbreak\r\tx", "line break x"),
        ("evil‮gnp.py", "evilgnp.py"),
        ("zero​width", "zerowidth"),
        ("", "?"),
        ("x" * 300, "x" * 99 + "…"),
    ],
)
def test_sanitize_text(raw: str, expected: str) -> None:
    assert rpc.sanitize_text(raw) == expected


def test_untrusted_names_stay_inside_one_code_span() -> None:
    hostile = "`](https://evil)\n@James3014 <img src=x>"
    rendered = rpc.code(hostile)
    assert rendered.count("`") == 2
    assert "\n" not in rendered


# --------------------------------------------------------------- rendering


def test_nothing_to_flag_is_a_single_line() -> None:
    assert rpc.render_comment(rpc.Findings()) == f"{rpc.MARKER}\nRIE: nothing to flag"


def test_render_actionable_lines_only() -> None:
    body = rpc.render_comment(
        rpc.Findings(
            overlaps={
                1967: ["nexus/core/registry.py"],
                1982: ["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"],
            },
            direct_impacted=["nexus/x.py"],
            all_impacted=["nexus/x.py", "nexus/y.py", "scripts/ops/z.py", "tests/ops/test_z.py"],
            systemic=[("Trusted impact controller (default branch)", [1951, 1972, 1987])],
        )
    )
    lines = body.splitlines()
    assert lines[0] == rpc.MARKER
    assert lines[1] == "- Overlaps with open PR #1967 on `nexus/core/registry.py`"
    assert lines[2] == "- Overlaps with open PR #1982 on `a.py`, `b.py`, `c.py`, `d.py` (+2 more)"
    assert lines[3] == (
        "- Impact: 4 files depend on the changed code (1 directly, 1 of them tests): `nexus` (2), `scripts/ops` (1)"
    )
    assert lines[4] == (
        "- Check `Trusted impact controller (default branch)` is failing on 3 open PRs (#1951, #1972, #1987), likely systemic"
    )
    assert len(lines) == 5
    assert not re.search(r"\b[0-9a-f]{40}\b", body)


def test_render_caps_volume() -> None:
    overlaps = {n: [f"p{n}/{i}.py" for i in range(50)] for n in range(1, 40)}
    systemic = [(f"check-{i}", list(range(1, 20))) for i in range(20)]
    body = rpc.render_comment(rpc.Findings(overlaps=overlaps, systemic=systemic))
    assert len(body) <= rpc.MAX_COMMENT_CHARS
    assert body.count("Overlaps with open PR #") == rpc.MAX_OVERLAP_LINES
    assert body.count("likely systemic") == rpc.MAX_SYSTEMIC_LINES
    assert "- Overlaps with 31 more open PRs" in body


def test_impact_areas_group_by_directory() -> None:
    assert rpc.impact_areas(["a/b/c.py", "a/b/d.py", "a/e.py", "top.py"]) == [
        ("a/b", 2),
        (".", 1),
        ("a", 1),
    ]


# --------------------------------------------------------- import graph


def test_import_graph_parses_without_importing(tmp_path: Path) -> None:
    files = {
        "pkg/__init__.py": "",
        "pkg/core.py": "X = 1\n",
        "pkg/sub/__init__.py": "from .. import core\n",
        "pkg/sub/leaf.py": "from ..core import X\nfrom . import sibling\n",
        "pkg/sub/sibling.py": "import pkg.core\n",
        "app.py": "from pkg.sub import leaf\nimport os\nraise SystemExit('must not run')\n",
        "broken.py": "def (\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    covered, edges, errors = rpc.build_import_graph(tmp_path, sorted(files))
    pairs = {(e["consumer"], e["dependency"]) for e in edges}
    assert ("pkg/sub/__init__.py", "pkg/core.py") in pairs
    assert ("pkg/sub/leaf.py", "pkg/core.py") in pairs
    assert ("pkg/sub/leaf.py", "pkg/sub/sibling.py") in pairs
    assert ("pkg/sub/sibling.py", "pkg/core.py") in pairs
    assert ("app.py", "pkg/sub/leaf.py") in pairs
    assert not any(dep == "os" for _, dep in pairs)
    assert errors == ["broken.py: SyntaxError"]
    assert covered == sorted(files)


# ------------------------------------------------------------ analysis glue


def _pr(
    number: int, files: tuple[str, ...], checks: tuple[dict[str, Any], ...] = ()
) -> rpc.PullRequestData:
    return rpc.PullRequestData(number, "h" * 40, "b" * 40, files, checks)


def test_analyze_maps_engine_results_to_findings() -> None:
    calls: dict[str, Any] = {}

    def fake_engine(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls[operation] = payload
        if operation == "overlap":
            return {
                "overlap_pairs": [
                    {"pr_a": 5, "pr_b": 7, "shared_paths": ["a.py"]},
                    {"pr_a": 7, "pr_b": 9, "shared_paths": ["b.py", "c.py"]},
                    {"pr_a": 5, "pr_b": 9, "shared_paths": ["z.py"]},
                ]
            }
        if operation == "impact":
            return {
                "direct_impacted_files": ["d.py", "a.py"],
                "all_impacted_files": ["d.py", "e.py", "a.py"],
            }
        return {"systemic_failures": [{"check_name": "pytest", "pr_numbers": [5, 7, 9]}]}

    this = _pr(7, ("a.py", "b.py"))
    findings = rpc.analyze(
        "o/r",
        this,
        [_pr(5, ("a.py",)), this, _pr(9, ("b.py",))],
        "m" * 40,
        (["a.py", "d.py", "e.py"], [{"consumer": "d.py", "dependency": "a.py"}], []),
        fake_engine,
        "2026-10-13T06:00:00Z",
    )
    assert findings.overlaps == {5: ["a.py"], 9: ["b.py", "c.py"]}
    assert findings.direct_impacted == ["d.py"]
    assert findings.all_impacted == ["d.py", "e.py"]
    assert findings.systemic == [("pytest", [5, 7, 9])]
    assert calls["impact"]["graph_complete"] is True
    assert set(calls["impact"]["covered_files"]) == {"a.py", "b.py", "d.py", "e.py"}
    assert [p["pr_number"] for p in calls["systemic"]["pull_requests"]] == [5, 7, 9]


# ----------------------------------------------------------- sticky upsert


class FakeClient:
    def __init__(self, comments: list[dict[str, Any]]) -> None:
        self.comments = comments
        self.writes: list[tuple[str, str, Any]] = []

    def paginate(self, path: str, **_: Any) -> list[dict[str, Any]]:
        return self.comments

    def request(self, method: str, path: str, params: Any = None, body: Any = None) -> Any:
        self.writes.append((method, path, body))
        return {}


BOT = {"login": "github-actions[bot]", "type": "Bot"}


def test_upsert_creates_when_absent() -> None:
    client = FakeClient([{"id": 1, "body": "hello", "user": BOT}])
    assert rpc.upsert_sticky_comment(client, "o/r", 7, f"{rpc.MARKER}\nx") == "CREATED"  # type: ignore[arg-type]
    assert client.writes == [("POST", "/repos/o/r/issues/7/comments", {"body": f"{rpc.MARKER}\nx"})]


def test_upsert_updates_only_the_bot_marker_comment() -> None:
    spoof = {"id": 2, "body": f"{rpc.MARKER}\nfake", "user": {"login": "someone", "type": "User"}}
    ours = {"id": 3, "body": f"{rpc.MARKER}\nold", "user": BOT}
    client = FakeClient([spoof, ours])
    assert rpc.upsert_sticky_comment(client, "o/r", 7, f"{rpc.MARKER}\nnew") == "UPDATED"  # type: ignore[arg-type]
    assert client.writes == [
        ("PATCH", "/repos/o/r/issues/comments/3", {"body": f"{rpc.MARKER}\nnew"})
    ]


def test_upsert_is_a_no_op_when_unchanged() -> None:
    client = FakeClient([{"id": 3, "body": f"{rpc.MARKER}\nsame", "user": BOT}])
    assert rpc.upsert_sticky_comment(client, "o/r", 7, f"{rpc.MARKER}\nsame") == "UNCHANGED"  # type: ignore[arg-type]
    assert client.writes == []


def test_main_skips_without_posting_on_expected_errors(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    summary = tmp_path / "summary.md"
    code = rpc.main([
        "--repository",
        "o/r",
        "--pr-number",
        "7",
        "--repo-root",
        str(tmp_path),
        "--engine-root",
        str(tmp_path),
        "--engine-pin",
        "0" * 40,
        "--post",
        "--step-summary",
        str(summary),
    ])
    assert code == 0
    assert "RIE comment skipped" in summary.read_text(encoding="utf-8")


def test_engine_runner_refuses_unpinned_checkout(tmp_path: Path) -> None:
    with pytest.raises(rpc.CommentError):
        rpc.engine_runner(tmp_path, "0" * 40)


# ------------------------------------------------------ workflow security


def _load(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["on"] = data.pop(True, data.get("on"))
    return data


def test_comment_workflow_runs_only_default_branch_code_with_scoped_write() -> None:
    wf = _load(COMMENT_WORKFLOW)
    assert set(wf["on"]) == {"pull_request_target"}
    assert wf["permissions"] == {}
    (job,) = wf["jobs"].values()
    assert job["permissions"] == {"contents": "read", "checks": "read", "pull-requests": "write"}
    for step in job["steps"]:
        with_ = step.get("with", {})
        if "actions/checkout" in step.get("uses", ""):
            assert with_.get("persist-credentials") is False
            assert "ref" not in with_ or re.fullmatch(r"[0-9a-f]{40}", str(with_["ref"]))
            assert with_.get("repository") in (None, "James3014/repository-intelligence-engine")
    text = COMMENT_WORKFLOW.read_text(encoding="utf-8")
    # No PR-controlled value is ever interpolated into a script or checkout ref.
    for forbidden in (
        "head.sha",
        "head.ref",
        "head.repo",
        "pull_request.title",
        "pull_request.body",
        "merge_commit_sha",
    ):
        assert forbidden not in text
    assert "python3 -I scripts/ops/rie_pr_comment.py" in text


def test_comment_and_snapshot_use_the_same_engine_pin() -> None:
    comment = _load(COMMENT_WORKFLOW)
    (job,) = comment["jobs"].values()
    engine_ref = next(
        s["with"]["ref"] for s in job["steps"] if s.get("with", {}).get("path") == ".rie-engine"
    )
    run_step = next(s for s in job["steps"] if "run" in s)
    assert run_step["env"]["RIE_PIN"] == engine_ref
    snapshot = _load(SNAPSHOT_WORKFLOW)
    uses = snapshot["jobs"]["snapshot"]["steps"][0]["uses"]
    assert uses == f"James3014/repository-intelligence-engine@{engine_ref}"


def test_script_is_stdlib_only() -> None:
    import ast

    tree = ast.parse((ROOT / "scripts/ops/rie_pr_comment.py").read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    import sys

    assert imported - {"__future__"} <= set(sys.stdlib_module_names)
