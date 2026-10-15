from __future__ import annotations

import json
import subprocess
import sys

import pytest

from scripts.ops.exact_base_tool_gate import (
    Finding,
    _distinct_roots,
    classify_findings,
    parse_bandit_json,
    parse_pyright_json,
    parse_ruff_json,
    parse_wiki_governance_receipt,
)


def test_ruff_json_is_normalized_to_repo_relative_path(tmp_path):
    root = tmp_path / "base-worktree"
    findings = parse_ruff_json(
        [
            {
                "filename": str(root / "nexus/app.py"),
                "location": {"row": 7, "column": 3},
                "end_location": {"row": 7, "column": 4},
                "code": "F401",
                "message": "unused import: os",
            }
        ],
        root=root,
    )

    assert findings == [Finding("ruff", "F401", "nexus/app.py", 7, 3, "error", "unused import: os")]


def test_pyright_json_is_normalized():
    findings = parse_pyright_json({
        "generalDiagnostics": [
            {
                "file": "nexus/app.py",
                "severity": "error",
                "message": "Unknown import",
                "rule": "reportMissingImports",
                "range": {"start": {"line": 2, "character": 1}},
            }
        ]
    })

    assert findings == [
        Finding("pyright", "reportMissingImports", "nexus/app.py", 3, 2, "error", "Unknown import")
    ]


def test_bandit_json_is_normalized():
    findings = parse_bandit_json({
        "results": [
            {
                "filename": "scripts/run.py",
                "line_number": 11,
                "test_id": "B101",
                "issue_severity": "LOW",
                "issue_text": "Use of assert detected.",
            }
        ]
    })

    assert findings == [
        Finding("bandit", "B101", "scripts/run.py", 11, 0, "low", "Use of assert detected.")
    ]


def test_wiki_receipt_findings_are_normalized():
    findings = parse_wiki_governance_receipt({
        "status": "BLOCK",
        "critical_gates": [],
        "findings": [
            {
                "path": "openwiki/index.md",
                "line": 4,
                "rule_id": "WIKI001",
                "severity": "warning",
                "message": "Unresolved link",
            }
        ],
    })

    assert findings == [
        Finding(
            "wiki-governance", "WIKI001", "openwiki/index.md", 4, 0, "warning", "Unresolved link"
        )
    ]


def test_wiki_release_receipt_failed_gate_and_missing_evidence_are_findings():
    findings = parse_wiki_governance_receipt({
        "status": "BLOCK",
        "critical_gates": [{"name": "wiki_links", "status": "BLOCK", "reason": "unresolved"}],
        "missing_evidence_reasons": ["receipt missing"],
    })

    assert findings == [
        Finding(
            "wiki-governance", "missing_evidence", "<receipt>", 0, 0, "error", "receipt missing"
        ),
        Finding("wiki-governance", "wiki_links", "<receipt>", 0, 0, "error", "unresolved"),
    ]


def test_exact_base_debt_is_non_blocking_when_head_has_same_findings():
    finding = Finding("ruff", "F401", "nexus/app.py", 7, 3, "error", "unused import")

    result = classify_findings([finding], [finding])

    assert result.classification == "EXACT_BASELINE_DEBT"
    assert result.blocking is False
    assert result.new_findings == []


def test_identical_clean_base_and_head_pass():
    result = classify_findings([], [])

    assert result.classification == "PASS"
    assert result.blocking is False


def test_base_and_head_both_fail_but_new_head_finding_blocks():
    baseline = Finding("bandit", "B101", "scripts/run.py", 11, 0, "low", "assert")
    introduced = Finding("bandit", "B602", "scripts/run.py", 12, 0, "high", "shell=True")

    result = classify_findings([baseline], [baseline, introduced])

    assert result.classification == "NEW_REGRESSION"
    assert result.blocking is True
    assert result.new_findings == [introduced]


def test_identity_ignores_line_and_column_but_keeps_stable_message():
    base = Finding("ruff", "F401", "nexus/app.py", 7, 3, "error", "unused import")
    head = Finding("ruff", "F401", "nexus/app.py", 99, 1, "error", "unused import")

    result = classify_findings([base], [head])

    assert result.classification == "EXACT_BASELINE_DEBT"
    assert result.new_findings == []


def test_severity_increase_is_a_new_regression():
    base = Finding("bandit", "B101", "run.py", 1, 1, "low", "assert")
    head = Finding("bandit", "B101", "run.py", 1, 1, "high", "assert")

    result = classify_findings([base], [head])

    assert result.classification == "NEW_REGRESSION"


def test_duplicate_finding_count_cannot_be_hidden():
    finding = Finding("ruff", "F401", "app.py", 1, 1, "error", "unused")

    result = classify_findings([finding], [finding, finding])

    assert result.classification == "NEW_REGRESSION"
    assert len(result.new_findings) == 1


def test_malformed_ruff_entry_is_rejected():
    with pytest.raises(ValueError, match="list of objects"):
        parse_ruff_json([{}, "bad"])


def test_failed_wiki_receipt_without_details_is_not_clean():
    findings = parse_wiki_governance_receipt({"status": "BLOCK", "critical_gates": []})

    assert findings == [
        Finding("wiki-governance", "receipt_status", "<receipt>", 0, 0, "error", "BLOCK")
    ]


def test_empty_wiki_object_is_rejected():
    with pytest.raises(ValueError, match="PASS or BLOCK"):
        parse_wiki_governance_receipt({})


def test_absolute_finding_path_must_stay_inside_root(tmp_path):
    with pytest.raises(ValueError, match="escapes evidence root"):
        parse_ruff_json(
            [
                {
                    "filename": "/outside/app.py",
                    "code": "F401",
                    "location": {"row": 1, "column": 1},
                    "message": "unused",
                }
            ],
            root=tmp_path,
        )


def test_relative_path_spelling_is_normalized():
    base = parse_ruff_json([
        {
            "filename": "./nexus/app.py",
            "code": "F401",
            "location": {"row": 1, "column": 1},
            "message": "unused",
        }
    ])
    head = parse_ruff_json([
        {
            "filename": "nexus/app.py",
            "code": "F401",
            "location": {"row": 2, "column": 1},
            "message": "unused",
        }
    ])

    assert classify_findings(base, head).classification == "EXACT_BASELINE_DEBT"


def test_malformed_pyright_range_is_rejected():
    with pytest.raises(ValueError, match="integer start coordinates"):
        parse_pyright_json({
            "generalDiagnostics": [{"file": "app.py", "severity": "error", "range": {}}]
        })


def test_malformed_bandit_coordinates_are_rejected():
    with pytest.raises(ValueError, match="integer line"):
        parse_bandit_json({
            "results": [
                {
                    "filename": "app.py",
                    "test_id": "B101",
                    "line_number": "1",
                    "issue_severity": 3,
                }
            ]
        })


@pytest.mark.parametrize(
    ("parser", "payload"),
    [
        (
            parse_ruff_json,
            [
                {
                    "filename": "app.py",
                    "code": "F401",
                    "location": {"row": True, "column": 1},
                }
            ],
        ),
        (
            parse_pyright_json,
            {
                "generalDiagnostics": [
                    {
                        "file": "app.py",
                        "severity": "error",
                        "range": {"start": {"line": True, "character": 1}},
                    }
                ]
            },
        ),
        (
            parse_bandit_json,
            {
                "results": [
                    {
                        "filename": "app.py",
                        "test_id": "B101",
                        "line_number": True,
                        "issue_severity": "HIGH",
                    }
                ]
            },
        ),
    ],
)
def test_boolean_coordinates_are_rejected(parser, payload):
    with pytest.raises(ValueError, match="integer"):
        parser(payload)


def test_boolean_pyright_severity_is_rejected():
    with pytest.raises(ValueError, match="file or severity"):
        parse_pyright_json({
            "generalDiagnostics": [
                {
                    "file": "app.py",
                    "severity": True,
                    "range": {"start": {"line": 1, "character": 1}},
                }
            ]
        })


@pytest.mark.parametrize("field", ["findings", "critical_gates"])
def test_malformed_wiki_entry_is_rejected(field):
    payload = {"status": "PASS", "critical_gates": []}
    payload[field] = ["bad"]

    with pytest.raises(ValueError, match="list of objects"):
        parse_wiki_governance_receipt(payload)


def test_different_worktree_roots_do_not_create_fake_regression(tmp_path):
    base_root = tmp_path / "base-worktree"
    head_root = tmp_path / "head-worktree"
    base = parse_ruff_json(
        [
            {
                "filename": str(base_root / "nexus/app.py"),
                "code": "F401",
                "location": {"row": 1, "column": 1},
                "message": "unused",
            }
        ],
        root=base_root,
    )
    head = parse_ruff_json(
        [
            {
                "filename": str(head_root / "nexus/app.py"),
                "code": "F401",
                "location": {"row": 1, "column": 1},
                "message": "unused",
            }
        ],
        root=head_root,
    )

    result = classify_findings(base, head)

    assert result.classification == "EXACT_BASELINE_DEBT"
    assert result.new_findings == []


def test_cli_writes_classification_and_blocks_new_finding(tmp_path):
    base = tmp_path / "base.json"
    head = tmp_path / "head.json"
    output = tmp_path / "classification.json"
    base.write_text(json.dumps([]), encoding="utf-8")
    head.write_text(
        json.dumps([
            {
                "filename": "nexus/app.py",
                "code": "F401",
                "location": {"row": 1, "column": 1},
                "message": "unused",
            }
        ]),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/ops/exact_base_tool_gate.py",
            "--tool",
            "ruff",
            "--base",
            str(base),
            "--head",
            str(head),
            "--output",
            str(output),
        ],
        check=False,
    )

    assert completed.returncode == 1
    assert json.loads(output.read_text(encoding="utf-8"))["classification"] == "NEW_REGRESSION"


def test_cli_invalid_json_is_bootstrap_defect_and_blocks(tmp_path):
    base = tmp_path / "base.json"
    head = tmp_path / "head.json"
    output = tmp_path / "classification.json"
    base.write_text("not-json", encoding="utf-8")
    head.write_text("[]", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/ops/exact_base_tool_gate.py",
            "--tool",
            "ruff",
            "--base",
            str(base),
            "--head",
            str(head),
            "--output",
            str(output),
        ],
        check=False,
    )

    assert completed.returncode == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["classification"] == "CI_BOOTSTRAP_DEFECT"
    assert report["blocking"] is True


def test_cli_tool_crash_is_bootstrap_defect_and_blocks(tmp_path):
    base = tmp_path / "base.json"
    head = tmp_path / "head.json"
    output = tmp_path / "classification.json"
    base.write_text("[]", encoding="utf-8")
    head.write_text("[]", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/ops/exact_base_tool_gate.py",
            "--tool",
            "ruff",
            "--base",
            str(base),
            "--head",
            str(head),
            "--base-exit-code",
            "2",
            "--output",
            str(output),
        ],
        check=False,
    )

    assert completed.returncode == 2
    assert json.loads(output.read_text(encoding="utf-8"))["classification"] == "CI_BOOTSTRAP_DEFECT"


def test_unknown_input_is_fail_closed():
    result = classify_findings([], [], base_valid=False)

    assert result.classification == "IMPACT_UNKNOWN"
    assert result.blocking is True


def test_json_text_is_accepted_by_parsers():
    assert parse_ruff_json(json.dumps([])) == []


def test_cli_prints_new_findings_with_fix_hints_to_job_log(tmp_path):
    base = tmp_path / "base.json"
    head = tmp_path / "head.json"
    output = tmp_path / "classification.json"
    base.write_text(json.dumps([]), encoding="utf-8")
    head.write_text(
        json.dumps([
            {
                "filename": "nexus/app.py",
                "code": "F401",
                "location": {"row": 3, "column": 1},
                "message": "`os` imported but unused",
            },
            {
                "filename": "nexus/fmt.py",
                "code": "unformatted",
                "location": {"row": 1, "column": 1},
                "message": "File would be reformatted",
            },
        ]),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/ops/exact_base_tool_gate.py",
            "--tool",
            "ruff",
            "--base",
            str(base),
            "--head",
            str(head),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    log = completed.stdout
    assert "Exact-base gate BLOCKED: NEW_REGRESSION" in log
    assert "nexus/app.py:3 F401 `os` imported but unused" in log
    assert "nexus/fmt.py:1 unformatted File would be reformatted" in log
    assert "run `ruff format --preview nexus/fmt.py`" in log
    assert "run `ruff check --fix nexus/app.py`" in log
    assert not any(line.startswith("::") for line in log.splitlines())
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["classification"] == "NEW_REGRESSION"


def test_cli_is_silent_when_not_blocking(tmp_path):
    base = tmp_path / "base.json"
    head = tmp_path / "head.json"
    output = tmp_path / "classification.json"
    base.write_text("[]", encoding="utf-8")
    head.write_text("[]", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/ops/exact_base_tool_gate.py",
            "--tool",
            "ruff",
            "--base",
            str(base),
            "--head",
            str(head),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stdout == ""


def test_cli_bootstrap_defect_prints_error_to_job_log(tmp_path):
    base = tmp_path / "base.json"
    head = tmp_path / "head.json"
    output = tmp_path / "classification.json"
    base.write_text("not-json", encoding="utf-8")
    head.write_text("[]", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/ops/exact_base_tool_gate.py",
            "--tool",
            "ruff",
            "--base",
            str(base),
            "--head",
            str(head),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "Exact-base gate BLOCKED: CI_BOOTSTRAP_DEFECT" in completed.stdout
    assert "error: JSONDecodeError" in completed.stdout


def test_blocking_log_cannot_emit_workflow_commands_from_candidate_paths():
    from dataclasses import asdict

    from scripts.ops.exact_base_tool_gate import render_blocking_log

    hostile = Finding(
        "ruff", "F401", "::set-env name=X::1", 1, 1, "error", "msg\n::add-mask::secret"
    )
    lines = render_blocking_log({
        "blocking": True,
        "classification": "NEW_REGRESSION",
        "new_findings": [asdict(hostile)],
    })
    assert lines
    assert not any(line.startswith("::") for line in lines)
    assert all("\n" not in line for line in lines)


def test_blocking_log_flattens_multiline_paths_and_errors():
    from dataclasses import asdict

    from scripts.ops.exact_base_tool_gate import render_blocking_log

    hostile = Finding(
        "ruff",
        "unformatted",
        "a.py\n::warning::injected",
        1,
        1,
        "error",
        "File would be reformatted",
    )
    lines = render_blocking_log({
        "blocking": True,
        "classification": "NEW_REGRESSION",
        "error": "ValueError: bad path x\n::error::injected",
        "new_findings": [asdict(hostile)],
    })
    assert lines
    for line in lines:
        assert "\n" not in line and "\r" not in line
        assert not line.lstrip().startswith("::")
        assert "##[" not in line


def test_log_safe_defuses_legacy_and_trimmed_workflow_commands():
    from scripts.ops.exact_base_tool_gate import _log_safe

    for raw in (
        "\r::notice::x",
        "  ::notice::x",
        "src/##[error]injected.py",
        "###[x",
        "a\u2028::y",
    ):
        safe = _log_safe(raw)
        assert "\n" not in safe and "\r" not in safe and "\u2028" not in safe
        assert not safe.lstrip().startswith("::")
        assert "##[" not in safe


def _write_src(root, rel, lines):
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ruff_at(root, rel, row, code="F401", message="`os` imported but unused"):
    return parse_ruff_json(
        [
            {
                "filename": rel,
                "code": code,
                "location": {"row": row, "column": 1},
                "message": message,
            }
        ],
        root=root,
    )


def _pyright_at(root, rel, line0, message="Unknown import"):
    return parse_pyright_json(
        {
            "generalDiagnostics": [
                {
                    "file": str(root / rel),
                    "severity": "error",
                    "message": message,
                    "rule": "reportMissingImports",
                    "range": {"start": {"line": line0, "character": 0}},
                }
            ]
        },
        root=root,
    )


def _finding_at(rel, row):
    # built directly: the parsers already reject symlink-escaping paths
    return Finding("ruff", "F401", rel, row, 1, "error", "`os` imported but unused")


def test_inserted_lines_above_baseline_debt_are_not_new(tmp_path):
    base_root, head_root = tmp_path / "base", tmp_path / "head"
    _write_src(base_root, "nexus/a.py", ["import os", "x = 1"])
    _write_src(head_root, "nexus/a.py", ["# new", "# lines", "import os", "x = 1"])
    _write_src(base_root, "nexus/b.py", ["import foo", "y = 1"])
    _write_src(head_root, "nexus/b.py", ["", "", "import foo", "y = 1"])

    ruff = classify_findings(
        _ruff_at(base_root, "nexus/a.py", 1),
        _ruff_at(head_root, "nexus/a.py", 3),
        base_root=base_root,
        head_root=head_root,
    )
    pyright = classify_findings(
        _pyright_at(base_root, "nexus/b.py", 0),
        _pyright_at(head_root, "nexus/b.py", 2),
        base_root=base_root,
        head_root=head_root,
    )

    for result in (ruff, pyright):
        assert result.classification == "EXACT_BASELINE_DEBT"
        assert result.new_findings == []
        assert result.resolved_findings == []
        assert not result.blocking


def test_same_rule_on_new_line_with_different_text_is_new(tmp_path):
    base_root, head_root = tmp_path / "base", tmp_path / "head"
    _write_src(base_root, "nexus/a.py", ["import os", "x = 1"])
    _write_src(head_root, "nexus/a.py", ["import os", "x = 1", "import os as other"])
    head = _ruff_at(head_root, "nexus/a.py", 1) + _ruff_at(head_root, "nexus/a.py", 3)

    result = classify_findings(
        _ruff_at(base_root, "nexus/a.py", 1), head, base_root=base_root, head_root=head_root
    )

    assert result.classification == "NEW_REGRESSION"
    assert [f.line for f in result.new_findings] == [3]


def test_duplicated_identical_line_is_new_via_ordinal(tmp_path):
    base_root, head_root = tmp_path / "base", tmp_path / "head"
    _write_src(base_root, "nexus/a.py", ["import os", "x = 1"])
    _write_src(head_root, "nexus/a.py", ["import os", "x = 1", "import os"])
    head = _ruff_at(head_root, "nexus/a.py", 1) + _ruff_at(head_root, "nexus/a.py", 3)

    result = classify_findings(
        _ruff_at(base_root, "nexus/a.py", 1), head, base_root=base_root, head_root=head_root
    )

    assert result.classification == "NEW_REGRESSION"
    assert len(result.new_findings) == 1
    assert result.resolved_findings == []


def test_unreadable_source_falls_back_without_hiding_new_findings(tmp_path):
    base_root, head_root = tmp_path / "base", tmp_path / "head"
    base_root.mkdir()
    head_root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("import os\n", encoding="utf-8")
    (head_root / "link.py").symlink_to(outside)
    _write_src(head_root, "short.py", ["import os"])

    # missing file, symlink escaping the root, and out-of-range line: none may crash
    # or be matched against a base finding at a different line.
    for rel, base_row, head_row in (
        ("missing.py", 1, 5),
        ("link.py", 1, 2),
        ("short.py", 1, 9),
    ):
        result = classify_findings(
            [_finding_at(rel, base_row)],
            [_finding_at(rel, head_row)],
            base_root=base_root,
            head_root=head_root,
        )
        assert result.classification == "NEW_REGRESSION", rel
        assert len(result.new_findings) == 1

    # an extra finding in an unreadable file still shows as new
    result = classify_findings(
        [_finding_at("missing.py", 1)],
        [_finding_at("missing.py", 1), _finding_at("missing.py", 4)],
        base_root=base_root,
        head_root=head_root,
    )
    assert result.classification == "NEW_REGRESSION"
    assert [f.line for f in result.new_findings] == [4]


def test_unformatted_is_keyed_per_file_not_by_first_line(tmp_path):
    base_root, head_root = tmp_path / "base", tmp_path / "head"
    _write_src(base_root, "nexus/f.py", ["x=1"])
    _write_src(head_root, "nexus/f.py", ["# header", "x=1"])
    args = ("unformatted", "File would be reformatted")

    same = classify_findings(
        _ruff_at(base_root, "nexus/f.py", 1, *args),
        _ruff_at(head_root, "nexus/f.py", 1, *args),
        base_root=base_root,
        head_root=head_root,
    )
    assert same.classification == "EXACT_BASELINE_DEBT"

    other = classify_findings(
        _ruff_at(base_root, "nexus/f.py", 1, *args),
        _ruff_at(head_root, "nexus/f.py", 1, *args) + _ruff_at(head_root, "nexus/g.py", 1, *args),
        base_root=base_root,
        head_root=head_root,
    )
    assert other.classification == "NEW_REGRESSION"


def _run_cli_ruff(tmp_path, base_rows, head_rows, *root_args):
    base = tmp_path / "base.json"
    head = tmp_path / "head.json"
    output = tmp_path / "classification.json"
    base.write_text(json.dumps(base_rows), encoding="utf-8")
    head.write_text(json.dumps(head_rows), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/ops/exact_base_tool_gate.py",
            "--tool",
            "ruff",
            "--base",
            str(base),
            "--head",
            str(head),
            "--output",
            str(output),
            *root_args,
        ],
        check=False,
        capture_output=True,
    )
    return completed.returncode, json.loads(output.read_text(encoding="utf-8"))


def _ruff_row(rel, row):
    return {
        "filename": rel,
        "code": "F401",
        "location": {"row": row, "column": 1},
        "message": "`os` imported but unused",
    }


def test_cli_shared_root_keeps_line_shift_as_baseline_debt(tmp_path):
    # One --root cannot hold both trees: reading the base finding's line from the
    # head tree would misreport a shifted debt finding as new, so the CLI falls back
    # to the source-independent identity.
    root = tmp_path / "tree"
    _write_src(root, "nexus/a.py", ["# new", "# lines", "import os"])

    code, report = _run_cli_ruff(
        tmp_path,
        [_ruff_row("nexus/a.py", 1)],
        [_ruff_row("nexus/a.py", 3)],
        "--root",
        str(root),
    )

    assert code == 0
    assert report["classification"] == "EXACT_BASELINE_DEBT"
    assert report["new_findings"] == []


def test_cli_distinct_roots_report_swapped_finding_as_new(tmp_path):
    # Base debt on one line is fixed while the same rule and message appear on a
    # different statement: the source-independent identity matched the two and hid
    # the new finding.
    base_root, head_root = tmp_path / "base", tmp_path / "head"
    _write_src(base_root, "nexus/a.py", ["OLD = 'a' * 1", "NEW = 1"])
    _write_src(head_root, "nexus/a.py", ["OLD = 1", "NEW = 'b' * 1"])
    row = {"filename": "nexus/a.py", "code": "E501", "message": "Line too long (120 > 100)"}

    code, report = _run_cli_ruff(
        tmp_path,
        [{**row, "location": {"row": 1, "column": 101}}],
        [{**row, "location": {"row": 2, "column": 101}}],
        "--base-root",
        str(base_root),
        "--head-root",
        str(head_root),
    )

    assert code == 1
    assert report["classification"] == "NEW_REGRESSION"
    assert [item["line"] for item in report["new_findings"]] == [2]


def test_unresolvable_roots_fall_back_to_legacy_keys(tmp_path, monkeypatch):
    from pathlib import Path

    def boom(self, *args, **kwargs):
        raise OSError("resolve failed")

    assert _distinct_roots(tmp_path / "a", tmp_path / "b") is True
    assert _distinct_roots(tmp_path / "a", tmp_path / "a") is False
    assert _distinct_roots(None, tmp_path / "b") is False
    monkeypatch.setattr(Path, "resolve", boom)
    assert _distinct_roots(tmp_path / "a", tmp_path / "b") is False
