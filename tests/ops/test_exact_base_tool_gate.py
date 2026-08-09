from __future__ import annotations

import json
import subprocess
import sys

import pytest

from scripts.ops.exact_base_tool_gate import (
    Finding,
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
    findings = parse_pyright_json(
        {
            "generalDiagnostics": [
                {
                    "file": "nexus/app.py",
                    "severity": "error",
                    "message": "Unknown import",
                    "rule": "reportMissingImports",
                    "range": {"start": {"line": 2, "character": 1}},
                }
            ]
        }
    )

    assert findings == [
        Finding("pyright", "reportMissingImports", "nexus/app.py", 3, 2, "error", "Unknown import")
    ]


def test_bandit_json_is_normalized():
    findings = parse_bandit_json(
        {
            "results": [
                {
                    "filename": "scripts/run.py",
                    "line_number": 11,
                    "test_id": "B101",
                    "issue_severity": "LOW",
                    "issue_text": "Use of assert detected.",
                }
            ]
        }
    )

    assert findings == [
        Finding("bandit", "B101", "scripts/run.py", 11, 0, "low", "Use of assert detected.")
    ]


def test_wiki_receipt_findings_are_normalized():
    findings = parse_wiki_governance_receipt(
        {
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
        }
    )

    assert findings == [
        Finding(
            "wiki-governance", "WIKI001", "openwiki/index.md", 4, 0, "warning", "Unresolved link"
        )
    ]


def test_wiki_release_receipt_failed_gate_and_missing_evidence_are_findings():
    findings = parse_wiki_governance_receipt(
        {
            "status": "BLOCK",
            "critical_gates": [{"name": "wiki_links", "status": "BLOCK", "reason": "unresolved"}],
            "missing_evidence_reasons": ["receipt missing"],
        }
    )

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
    base = parse_ruff_json(
        [
            {
                "filename": "./nexus/app.py",
                "code": "F401",
                "location": {"row": 1, "column": 1},
                "message": "unused",
            }
        ]
    )
    head = parse_ruff_json(
        [
            {
                "filename": "nexus/app.py",
                "code": "F401",
                "location": {"row": 2, "column": 1},
                "message": "unused",
            }
        ]
    )

    assert classify_findings(base, head).classification == "EXACT_BASELINE_DEBT"


def test_malformed_pyright_range_is_rejected():
    with pytest.raises(ValueError, match="integer start coordinates"):
        parse_pyright_json(
            {"generalDiagnostics": [{"file": "app.py", "severity": "error", "range": {}}]}
        )


def test_malformed_bandit_coordinates_are_rejected():
    with pytest.raises(ValueError, match="integer line"):
        parse_bandit_json(
            {
                "results": [
                    {
                        "filename": "app.py",
                        "test_id": "B101",
                        "line_number": "1",
                        "issue_severity": 3,
                    }
                ]
            }
        )


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
        parse_pyright_json(
            {
                "generalDiagnostics": [
                    {
                        "file": "app.py",
                        "severity": True,
                        "range": {"start": {"line": 1, "character": 1}},
                    }
                ]
            }
        )


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
        json.dumps(
            [
                {
                    "filename": "nexus/app.py",
                    "code": "F401",
                    "location": {"row": 1, "column": 1},
                    "message": "unused",
                }
            ]
        ),
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
