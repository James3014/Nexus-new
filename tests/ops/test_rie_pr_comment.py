"""Repository Intelligence sticky PR comment (Owner decision 2026-10-13)."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ops import rie_pr_comment as rpc

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ops/rie_pr_comment.py"
COMMENT_WORKFLOW = ROOT / ".github/workflows/repository-intelligence-comment.yml"
SNAPSHOT_WORKFLOW = ROOT / ".github/workflows/repository-intelligence.yml"
RLO = chr(0x202E)
ZWSP = chr(0x200B)


# ------------------------------------------------------------- sanitizing


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("scripts/ops/a.py", "scripts/ops/a.py"),
        ("a`b`c", "a'b'c"),
        ("line\nbreak\r\tx", "line break x"),
        (f"evil{RLO}gnp.py", "evilgnp.py"),
        (f"zero{ZWSP}width", "zerowidth"),
        ("", "?"),
        ("x" * 300, "x" * 97 + "..."),
    ],
)
def test_sanitize_text(raw: str, expected: str) -> None:
    assert rpc.sanitize_text(raw) == expected


def test_untrusted_names_stay_inside_one_code_span() -> None:
    hostile = "`](https://evil)\n@James3014 <img src=x>"
    rendered = rpc.code(hostile)
    assert rendered.count("`") == 2
    assert "\n" not in rendered


@pytest.mark.parametrize("path", [SCRIPT, Path(__file__)])
def test_sources_contain_no_invisible_or_bidi_characters(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert not [ch for ch in text if ord(ch) > 0x7E and ch != "\n"]


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
            systemic=[
                rpc.SystemicLine(
                    "Trusted impact controller (default branch)",
                    ".github/workflows/trusted-impact-gate.yml",
                    [1951, 1972, 1987],
                )
            ],
        )
    )
    lines = body.splitlines()
    assert lines == [
        rpc.MARKER,
        "- Overlaps with open PR #1967 on `nexus/core/registry.py`",
        "- Overlaps with open PR #1982 on `a.py`, `b.py`, `c.py`, `d.py` (+2 more)",
        "- Impact: 4 files depend on the changed code (1 directly, 1 of them tests): `nexus` (2), `scripts/ops` (1)",
        "- Check `Trusted impact controller (default branch)` in `.github/workflows/trusted-impact-gate.yml`"
        " is failing on 3 open PRs (#1951, #1972, #1987), likely systemic",
    ]
    assert not re.search(r"\b[0-9a-f]{40}\b", body)


def test_notes_follow_nothing_to_flag() -> None:
    body = rpc.render_comment(
        rpc.Findings(notes=["compared only the 60 most recently updated of 75 open PRs"])
    )
    assert body.splitlines()[1:] == [
        "RIE: nothing to flag",
        "- Note: compared only the 60 most recently updated of 75 open PRs",
    ]


def test_render_caps_volume() -> None:
    overlaps = {n: [f"p{n}/{i}.py" for i in range(50)] for n in range(1, 40)}
    systemic = [rpc.SystemicLine(f"check-{i}", "", list(range(1, 20))) for i in range(20)]
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


# ------------------------------------------------------- GraphQL acquisition


def _check_run(
    name: str, conclusion: str | None, run_id: int, *, path: str = ".github/workflows/ci.yml"
) -> dict:
    return {
        "__typename": "CheckRun",
        "databaseId": run_id,
        "name": name,
        "conclusion": conclusion,
        "status": "COMPLETED" if conclusion else "IN_PROGRESS",
        "startedAt": "2026-10-13T05:00:00Z",
        "completedAt": "2026-10-13T05:01:00Z" if conclusion else None,
        "checkSuite": {
            "databaseId": 900 + run_id,
            "app": {"slug": "github-actions"},
            "workflowRun": {"file": {"path": path}, "workflow": {"databaseId": 77}},
        },
    }


def test_check_summary_passes_engine_identity_fields() -> None:
    summary = rpc.check_summary(_check_run("pytest", "FAILURE", 5))
    assert summary == {
        "name": "pytest",
        "status": "failure",
        "check_run_id": 5,
        "completed_at": "2026-10-13T05:01:00Z",
        "started_at": "2026-10-13T05:00:00Z",
        "check_suite_id": 905,
        "app_slug": "github-actions",
        "workflow_id": 77,
        "workflow_path": ".github/workflows/ci.yml",
    }
    status = rpc.check_summary({
        "__typename": "StatusContext",
        "context": "ci/x",
        "state": "ERROR",
        "createdAt": "t",
    })
    assert status == {"name": "ci/x", "status": "error", "completed_at": "t"}


def _pr_node(
    number: int,
    files: list[str],
    checks: list[dict],
    *,
    total_files=None,
    total_checks=None,
    fork=False,
):
    return {
        "number": number,
        "headRefOid": "h" * 40,
        "baseRefOid": "b" * 40,
        "isCrossRepository": fork,
        "files": {"totalCount": total_files or len(files), "nodes": [{"path": f} for f in files]},
        "commits": {
            "nodes": [
                {
                    "commit": {
                        "statusCheckRollup": {
                            "contexts": {"totalCount": total_checks or len(checks), "nodes": checks}
                        }
                    }
                }
            ]
        },
    }


class FakeGraphQL:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.queries: list[tuple[str, dict[str, Any]]] = []
        self.writes: list[tuple[str, str, Any]] = []

    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        self.queries.append((query, variables))
        return self.responses.pop(0)

    def request(self, method: str, path: str, body: Any = None) -> Any:
        self.writes.append((method, path, body))
        return {}


def _overview(open_total: int = 2) -> dict[str, Any]:
    this = _pr_node(7, ["a.py"], [_check_run("pytest", "FAILURE", 1)])
    this["comments"] = {
        "nodes": [
            {
                "databaseId": 3,
                "body": f"{rpc.MARKER}\nold",
                "author": {"login": "github-actions", "__typename": "Bot"},
            }
        ]
    }
    return {
        "repository": {
            "defaultBranchRef": {
                "target": {
                    "oid": "m" * 40,
                    "history": {
                        "nodes": [
                            {
                                "statusCheckRollup": {
                                    "contexts": {
                                        "totalCount": 1,
                                        "nodes": [_check_run("pytest", "SUCCESS", 9)],
                                    }
                                }
                            }
                        ]
                    },
                }
            },
            "pullRequests": {
                "totalCount": open_total,
                "nodes": [
                    _pr_node(7, ["a.py"], [_check_run("pytest", "FAILURE", 1)]),
                    _pr_node(
                        9, [f"f{i}.py" for i in range(100)], [], total_files=250, total_checks=140
                    ),
                ],
            },
            "pullRequest": this,
        }
    }


def test_collect_reads_everything_in_one_graphql_query() -> None:
    client = FakeGraphQL([_overview(open_total=75)])
    acq = rpc.collect(client, "o/r", 7)  # type: ignore[arg-type]
    assert len(client.queries) == 1
    assert client.queries[0][1] == {"owner": "o", "name": "r", "number": 7}
    assert [pr.number for pr in acq.pulls] == [7, 9]
    assert acq.main_sha == "m" * 40
    assert acq.main_checks[0]["status"] == "success"
    assert acq.this_pr.checks[0]["workflow_id"] == 77
    assert rpc.find_sticky_comment(acq.comments)["databaseId"] == 3  # type: ignore[index]
    notes = rpc.truncation_notes(acq)
    assert notes == [
        "compared only the 2 most recently updated of 75 open PRs",
        "file lists of open PRs #9 were cut at 100; overlaps with them may be incomplete",
        "check lists of open PRs #9 were cut at 100; systemic detection may be incomplete",
    ]


def test_collect_flags_main_and_comment_truncation() -> None:
    overview = _overview()
    repo = overview["repository"]
    repo["defaultBranchRef"]["target"]["history"]["nodes"][0]["statusCheckRollup"]["contexts"][
        "totalCount"
    ] = 150
    repo["pullRequest"]["comments"]["totalCount"] = 250
    acq = rpc.collect(FakeGraphQL([overview]), "o/r", 7)  # type: ignore[arg-type]
    assert acq.main_checks_truncated is True
    assert acq.comments_truncated is True
    notes = rpc.truncation_notes(acq)
    assert (
        "main check history was cut at 100 checks per commit; systemic cutoffs may be incomplete"
        in notes
    )
    assert (
        "this PR has more than 100 comments; an earlier RIE comment outside that window may be duplicated"
        in notes
    )


def test_note_when_failing_workflow_paths_exceed_the_lookup_cap() -> None:
    checks = tuple(
        {"name": "x", "status": "failure", "workflow_path": f".github/workflows/w{i}.yml"}
        for i in range(rpc.MAX_WORKFLOW_PATHS + 3)
    )
    this = rpc.PullRequestData(7, "h", "b", (), checks)
    acq = rpc.Acquisition(this, (this,), 1, "m" * 40, (), ())
    assert rpc.truncation_notes(acq) == [
        f"only {rpc.MAX_WORKFLOW_PATHS} of {rpc.MAX_WORKFLOW_PATHS + 3} failing workflows were checked for recent changes on main"
    ]


def test_workflow_paths_travel_only_as_graphql_variables() -> None:
    hostile = '.github/workflows/x.yml") { evil }'
    pr = rpc.PullRequestData(
        1, "h", "b", (), ({"name": "x", "status": "failure", "workflow_path": hostile},)
    )
    client = FakeGraphQL([
        {
            "repository": {
                "defaultBranchRef": {
                    "target": {"w0": {"nodes": [{"committedDate": "2026-10-13T01:00:00Z"}]}}
                }
            }
        }
    ])
    changed = rpc.collect_workflow_changes(client, "o/r", [pr])  # type: ignore[arg-type]
    query, variables = client.queries[0]
    assert hostile not in query and variables["p0"] == hostile
    assert changed == {hostile: "2026-10-13T01:00:00Z"}


def test_no_failing_checks_means_no_second_query() -> None:
    client = FakeGraphQL([])
    pr = rpc.PullRequestData(
        1, "h", "b", (), ({"name": "x", "status": "success", "workflow_path": "w.yml"},)
    )
    assert rpc.collect_workflow_changes(client, "o/r", [pr]) == {}  # type: ignore[arg-type]
    assert client.queries == []


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
        return {
            "systemic_failures": [
                {"check_name": "pytest", "workflow_path": "w.yml", "pr_numbers": [5, 7, 9]}
            ]
        }

    this = _pr(7, ("a.py", "b.py"))
    acq = rpc.Acquisition(
        this_pr=this,
        pulls=(_pr(5, ("a.py",)), this, _pr(9, ("b.py",))),
        open_total=3,
        main_sha="m" * 40,
        main_checks=({"name": "pytest", "status": "success"},),
        comments=(),
    )
    findings = rpc.analyze(
        "o/r",
        acq,
        (["a.py", "d.py", "e.py"], [{"consumer": "d.py", "dependency": "a.py"}], []),
        {"w.yml": "2026-10-13T01:00:00Z"},
        fake_engine,
        "2026-10-13T06:00:00Z",
    )
    assert findings.overlaps == {5: ["a.py"], 9: ["b.py", "c.py"]}
    assert findings.direct_impacted == ["d.py"]
    assert findings.all_impacted == ["d.py", "e.py"]
    assert findings.systemic == [rpc.SystemicLine("pytest", "w.yml", [5, 7, 9])]
    assert findings.notes == []
    assert calls["impact"]["graph_complete"] is True
    assert calls["systemic"]["main_checks"] == [{"name": "pytest", "status": "success"}]
    assert calls["systemic"]["workflow_changed_at"] == {"w.yml": "2026-10-13T01:00:00Z"}


# ----------------------------------------------------------- sticky upsert

BOT = {"login": "github-actions", "__typename": "Bot"}


def test_upsert_creates_when_absent() -> None:
    client = FakeGraphQL([])
    comments = [{"databaseId": 1, "body": "hello", "author": BOT}]
    assert rpc.upsert_sticky_comment(client, "o/r", 7, comments, f"{rpc.MARKER}\nx") == "CREATED"  # type: ignore[arg-type]
    assert client.writes == [("POST", "/repos/o/r/issues/7/comments", {"body": f"{rpc.MARKER}\nx"})]


def test_upsert_updates_only_the_bot_marker_comment() -> None:
    spoof = {
        "databaseId": 2,
        "body": f"{rpc.MARKER}\nfake",
        "author": {"login": "github-actions", "__typename": "User"},
    }
    ours = {"databaseId": 3, "body": f"{rpc.MARKER}\nold", "author": BOT}
    client = FakeGraphQL([])
    assert (
        rpc.upsert_sticky_comment(client, "o/r", 7, [spoof, ours], f"{rpc.MARKER}\nnew")
        == "UPDATED"
    )  # type: ignore[arg-type]
    assert client.writes == [
        ("PATCH", "/repos/o/r/issues/comments/3", {"body": f"{rpc.MARKER}\nnew"})
    ]


def test_upsert_is_a_no_op_when_unchanged() -> None:
    client = FakeGraphQL([])
    comments = [{"databaseId": 3, "body": f"{rpc.MARKER}\nsame", "author": BOT}]
    assert (
        rpc.upsert_sticky_comment(client, "o/r", 7, comments, f"{rpc.MARKER}\nsame") == "UNCHANGED"
    )  # type: ignore[arg-type]
    assert client.writes == []


def _main_args(tmp_path: Path, summary: Path) -> list[str]:
    return [
        "--repository", "o/r", "--pr-number", "7", "--repo-root", str(tmp_path),
        "--engine-root", str(tmp_path), "--engine-pin", "0" * 40, "--post", "--step-summary", str(summary),
    ]  # fmt: skip


def test_main_skips_without_posting_on_expected_errors(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    summary = tmp_path / "summary.md"
    assert rpc.main(_main_args(tmp_path, summary)) == 0
    assert "RIE comment skipped" in summary.read_text(encoding="utf-8")


def test_main_skips_fork_pull_requests(tmp_path: Path, monkeypatch) -> None:
    overview = _overview()
    overview["repository"]["pullRequest"]["isCrossRepository"] = True
    client = FakeGraphQL([overview])
    monkeypatch.setattr(rpc, "GitHubClient", lambda *a, **k: client)
    summary = tmp_path / "summary.md"
    assert rpc.main(_main_args(tmp_path, summary)) == 0
    assert "fork pull request" in summary.read_text(encoding="utf-8")
    assert client.writes == []


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
    # actions: read lets the token resolve checkSuite.workflowRun (workflow id/path).
    assert job["permissions"] == {
        "contents": "read",
        "checks": "read",
        "actions": "read",
        "pull-requests": "write",
    }
    assert job["if"] == "github.event.pull_request.head.repo.full_name == github.repository"
    for step in job["steps"]:
        with_ = step.get("with", {})
        if "actions/checkout" in step.get("uses", ""):
            assert with_.get("persist-credentials") is False
            assert "ref" not in with_ or re.fullmatch(r"[0-9a-f]{40}", str(with_["ref"]))
            assert with_.get("repository") in (None, "James3014/repository-intelligence-engine")
    # No PR-controlled value is ever interpolated into a script, env, or input.
    executable = yaml.safe_dump([
        {k: s.get(k) for k in ("run", "env", "with")} for s in job["steps"]
    ])
    for forbidden in (
        "head.ref",
        "head.repo",
        "pull_request.title",
        "pull_request.body",
        "merge_commit_sha",
    ):
        assert forbidden not in executable
    # #1580: the PR head SHA (40 hex, not free text) may only be passed as an env value to the
    # data-only guard step, never interpolated into a script or action input.
    for step in job["steps"]:
        assert "head.sha" not in str(step.get("run", "")) + str(step.get("with", ""))
        if "head.sha" in str(step.get("env", "")):
            assert "rie_guard_delta_evidence.py" in step["run"]
            assert step["env"]["HEAD_SHA"] == "${{ github.event.pull_request.head.sha }}"
    assert "python3 -I scripts/ops/rie_pr_comment.py" in executable


def test_comment_workflow_debounces_before_any_api_use() -> None:
    wf = _load(COMMENT_WORKFLOW)
    assert wf["concurrency"]["cancel-in-progress"] is True
    assert "pull_request.number" in wf["concurrency"]["group"]
    (job,) = wf["jobs"].values()
    assert job["steps"][0]["run"].startswith("sleep ")


def test_comment_and_snapshot_use_the_same_engine_pin() -> None:
    comment = _load(COMMENT_WORKFLOW)
    (job,) = comment["jobs"].values()
    engine_ref = next(
        s["with"]["ref"] for s in job["steps"] if s.get("with", {}).get("path") == ".rie-engine"
    )
    run_step = next(s for s in job["steps"] if "RIE_PIN" in (s.get("env") or {}))
    assert run_step["env"]["RIE_PIN"] == engine_ref
    snapshot = _load(SNAPSHOT_WORKFLOW)
    uses = snapshot["jobs"]["snapshot"]["steps"][0]["uses"]
    assert uses == f"James3014/repository-intelligence-engine@{engine_ref}"


def test_script_is_stdlib_only() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
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
    assert imported - {"__future__"} <= set(sys.stdlib_module_names)


# ------------------------------------------- guard semantic delta (#1580)

import importlib.util  # noqa: E402
import json  # noqa: E402

GUARD_SCRIPT = ROOT / "scripts/ops/rie_guard_delta_evidence.py"
GUARD_PIN = "88285acf570688befbc8e36eb73f46987171bd4e"
_PR = 77
_HEAD = "a" * 40
_BASE = "b" * 40
_MAIN = "c" * 40


def _guard_module() -> Any:
    spec = importlib.util.spec_from_file_location("rie_guard_delta_evidence_t", GUARD_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _identity(**overrides: Any) -> dict[str, Any]:
    ident = {
        "repository": "James3014/Nexus-new",
        "pr_number": _PR,
        "head_sha": _HEAD,
        "base_sha": _BASE,
        "current_main_sha": _MAIN,
    }
    ident.update(overrides)
    return ident


def _report(classification: str, **extra: Any) -> dict[str, Any]:
    ident = _identity()
    old = {**ident, "head_sha": _BASE}
    report = {
        "classification": classification,
        "reason_codes": [],
        "tightening_witnesses": [],
        "loosening_witnesses": [],
        "evidence_gaps": [],
        "collection_errors": [],
        "content_sha256": "d" * 64,
        "is_complete": True,
        "collection_complete": True,
        "old_identity": old,
        "new_identity": ident,
    }
    report.update(extra)
    return report


def _projection(classification: str, gaps: tuple[str, ...] = (), **extra: Any) -> dict[str, Any]:
    return _guard_module().project_report(
        _report(classification, **extra), _identity(), "e" * 40, gaps
    )


def _write(tmp_path: Path, projection: dict[str, Any]) -> Path:
    path = tmp_path / "guard.json"
    path.write_text(json.dumps(projection), encoding="utf-8")
    return path


def _render_guard(tmp_path: Path, projection: dict[str, Any], **kw: Any) -> str:
    guard = rpc.load_guard_delta(
        _write(tmp_path, projection), kw.get("pr", _PR), kw.get("head", _HEAD)
    )
    return rpc.render_comment(rpc.Findings(guard_delta=guard))


def test_guard_loosens_is_flagged_and_suppresses_nothing_to_flag(tmp_path: Path) -> None:
    proj = _projection(
        "LOOSENS", loosening_witnesses=["a", "b", "c", "d", "e"], tightening_witnesses=["t"]
    )
    body = _render_guard(tmp_path, proj)
    assert rpc.NOTHING_TO_FLAG not in body
    line = next(x for x in body.splitlines() if "Guard semantic delta" in x)
    assert line.startswith("- Guard semantic delta (`canonical_owner_table`): `LOOSENS`")
    assert "HIGH_SIGNAL_REVIEW_ATTENTION" in line
    assert "loosening `a`, `b`, `c` (+2 more)" in line
    assert "tightening `t`" in line
    assert "`d`" not in line
    assert f"report `{'d' * 12}`" in line


def test_guard_unknown_shows_reason_codes(tmp_path: Path) -> None:
    body = _render_guard(tmp_path, _projection("UNKNOWN", reason_codes=["R1", "R2"]))
    assert "`UNKNOWN`" in body and "reasons `R1`, `R2`" in body
    assert rpc.NOTHING_TO_FLAG not in body


def test_guard_unchanged_is_a_note_and_nothing_to_flag_still_shows(tmp_path: Path) -> None:
    body = _render_guard(tmp_path, _projection("UNCHANGED"))
    lines = body.splitlines()
    assert lines[1] == rpc.NOTHING_TO_FLAG
    assert lines[2].startswith("- Note: guard semantic delta (`canonical_owner_table`) `UNCHANGED`")
    assert f"report `{'d' * 12}`, advisory only" in lines[2]


def test_guard_incomplete_projection_is_not_observed_never_unchanged(tmp_path: Path) -> None:
    proj = _guard_module().make_incomplete_projection(_identity(), "ENGINE_UNAVAILABLE")
    body = _render_guard(tmp_path, proj)
    assert "- Note: guard semantic delta not observed (`ENGINE_UNAVAILABLE`)" in body
    assert "this is not an unchanged result" in body
    assert "`UNCHANGED`" not in body


def test_guard_tampered_seal_is_not_observed(tmp_path: Path) -> None:
    proj = _projection("LOOSENS")
    proj["classification"] = "UNCHANGED"  # edited without resealing
    body = _render_guard(tmp_path, proj)
    assert "not observed (`BAD_SEAL`)" in body
    assert "`UNCHANGED`" not in body


@pytest.mark.parametrize(
    ("pr", "head"), [(_PR + 1, _HEAD), (_PR, "f" * 40)], ids=["pr_number", "head_sha"]
)
def test_guard_identity_mismatch_is_not_observed(tmp_path: Path, pr: int, head: str) -> None:
    body = _render_guard(tmp_path, _projection("UNCHANGED"), pr=pr, head=head)
    assert "not observed (`IDENTITY_MISMATCH`)" in body


def test_guard_head_not_enforced_when_unknown(tmp_path: Path) -> None:
    guard = rpc.load_guard_delta(_write(tmp_path, _projection("UNCHANGED")), _PR)
    assert guard.observed


def test_guard_missing_or_bad_files_are_not_observed(tmp_path: Path) -> None:
    missing = rpc.load_guard_delta(tmp_path / "nope.json", _PR, _HEAD)
    assert (missing.observed, missing.reason) == (False, "FILE_MISSING")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert rpc.load_guard_delta(bad, _PR, _HEAD).reason == "FILE_UNREADABLE"
    bad.write_text("[]", encoding="utf-8")
    assert rpc.load_guard_delta(bad, _PR, _HEAD).reason == "BAD_SHAPE"
    proj = _projection("UNCHANGED")
    proj["schema"] = "other.v1"
    assert rpc.load_guard_delta(_write(tmp_path, proj), _PR, _HEAD).reason == "BAD_SCHEMA"
    proj = _projection("UNCHANGED")
    proj["claim_ceiling"] = "MORE"
    assert rpc.load_guard_delta(_write(tmp_path, proj), _PR, _HEAD).reason == "BAD_CLAIM_CEILING"
    assert "not observed (`FILE_MISSING`)" in rpc.render_comment(rpc.Findings(guard_delta=missing))


def test_no_guard_delta_renders_exactly_as_before() -> None:
    plain = rpc.Findings(notes=("n",))
    assert rpc.render_comment(plain) == rpc.render_comment(
        rpc.Findings(notes=("n",), guard_delta=None)
    )
    assert rpc.Findings().guard_delta is None
    assert rpc.render_comment(rpc.Findings()) == f"{rpc.MARKER}\n{rpc.NOTHING_TO_FLAG}"


def test_guard_untrusted_witnesses_are_sanitized(tmp_path: Path) -> None:
    hostile = "x`](https://evil)\n@James3014 <img>"
    proj = _projection("LOOSENS", loosening_witnesses=[hostile])
    # project_report redacts non-identifiers; reseal a hostile one to test the renderer too.
    proj["loosening_witnesses"] = {"items": [hostile], "total": 1, "truncated": False}
    proj["content_sha256"] = rpc._guard_canonical_hash({
        k: v for k, v in proj.items() if k != "content_sha256"
    })
    body = _render_guard(tmp_path, proj)
    assert "\n@James3014" not in body
    line = next(x for x in body.splitlines() if "Guard semantic delta" in x)
    assert "`x'](https://evil) @James3014 <img>`" in line
    assert len(body.splitlines()) == 2


def test_guard_canonical_hash_parity_with_evidence_script() -> None:
    guard = _guard_module()
    samples: list[dict[str, Any]] = [
        {},
        {"b": 1, "a": [1, 2, {"z": None}]},
        {"u": "caf" + chr(0xE9) + chr(0x4E2D), "t": True, "f": 1.5},
    ]
    samples.append(_projection("LOOSENS"))
    for sample in samples:
        assert rpc._guard_canonical_hash(sample) == guard.canonical_hash(sample)
    proj = _projection("UNCHANGED")
    assert proj["content_sha256"] == rpc._guard_canonical_hash({
        k: v for k, v in proj.items() if k != "content_sha256"
    })


def _comment_steps() -> list[dict[str, Any]]:
    data = yaml.safe_load(COMMENT_WORKFLOW.read_text(encoding="utf-8"))
    return data["jobs"]["sticky-comment"]["steps"]


def test_comment_workflow_guard_step_is_data_only() -> None:
    steps = _comment_steps()
    guard = [s for s in steps if "rie_guard_delta_evidence.py" in s.get("run", "")]
    assert len(guard) == 1
    step = guard[0]
    assert "--run-behavioral-probes" not in step["run"]
    assert "--step-summary" not in step["run"]
    assert step.get("continue-on-error") is True
    assert "python3 -I" in step["run"]
    assert "--engine-root" in step["run"] and ".rie-guard-engine" in step["run"]
    render = [s for s in steps if "rie_pr_comment.py" in s.get("run", "")]
    assert len(render) == 1
    assert '--guard-delta-json "$RUNNER_TEMP/rie-guard-delta.json"' in render[0]["run"]
    assert steps.index(step) < steps.index(render[0])
    assert "--run-behavioral-probes" not in COMMENT_WORKFLOW.read_text(encoding="utf-8").replace(
        "NEVER pass --run-behavioral-probes", ""
    )


def test_comment_workflow_checkouts_are_pinned_and_never_the_pr_head() -> None:
    steps = _comment_steps()
    checkouts = [s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@")]
    assert len(checkouts) == 3
    for step in checkouts:
        with_ = step["with"]
        assert with_["persist-credentials"] is False
        assert "pull_request.head" not in str(with_.get("ref", ""))
    engines = {s["with"].get("path"): s["with"].get("ref") for s in checkouts}
    assert engines[".rie-guard-engine"] == GUARD_PIN
    assert engines[".rie-engine"] == "77a937b67c3da4756f535a41b59cdf5555a25e31"
    default = next(s for s in checkouts if "path" not in s["with"])
    assert default["with"]["fetch-depth"] == 0
    assert "ref" not in default["with"]
    assert ".rie-guard-engine/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
