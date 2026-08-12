from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.ops import check_golden_authority_drift as drift

ROOT = Path(__file__).resolve().parents[2]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_unmapped_change_needs_no_disposition(tmp_path):
    head = _git("rev-parse", "HEAD")
    dispositions = tmp_path / "dispositions.json"
    dispositions.write_text(
        json.dumps(
            {
                "schema": drift.DISPOSITIONS_SCHEMA,
                "base_revision": head,
                "head_revision": head,
                "cases": {},
            }
        ),
        encoding="utf-8",
    )

    result = drift.check_golden_authority_drift(
        base_ref=head,
        head_ref=head,
        dispositions_path=dispositions,
        root=ROOT,
    )

    assert result["status"] == "PASS"
    assert result["affected_cases"] == []


def test_changed_mapped_authority_requires_exact_fingerprint(tmp_path, monkeypatch):
    monkeypatch.setattr(drift, "_changed_paths", lambda *_args: ["AGENTS.md"])
    head = _git("rev-parse", "HEAD")
    missing = tmp_path / "missing.json"
    missing.write_text(
        json.dumps(
            {
                "schema": drift.DISPOSITIONS_SCHEMA,
                "base_revision": head,
                "head_revision": head,
                "cases": {},
            }
        ),
        encoding="utf-8",
    )

    blocked = drift.check_golden_authority_drift(
        base_ref=head,
        head_ref=head,
        dispositions_path=missing,
        root=ROOT,
    )
    assert blocked["status"] == "FAIL_CLOSED"
    assert "GB-001:missing_disposition" in blocked["errors"]

    rows = {
        case_id: {
            "disposition": "NO_GOLDEN_IMPACT",
            "source_fingerprint": blocked["current_case_fingerprints"][case_id],
            "rationale": "Formatting-only wording change; mapped behavior is unchanged.",
        }
        for case_id in blocked["affected_cases"]
    }
    supplied = tmp_path / "supplied.json"
    supplied.write_text(
        json.dumps(
            {
                "schema": drift.DISPOSITIONS_SCHEMA,
                "base_revision": head,
                "head_revision": head,
                "cases": rows,
            }
        ),
        encoding="utf-8",
    )
    passed = drift.check_golden_authority_drift(
        base_ref=head,
        head_ref=head,
        dispositions_path=supplied,
        root=ROOT,
    )
    assert passed["status"] == "PASS"


def test_stale_fingerprint_and_malformed_rationale_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(drift, "_changed_paths", lambda *_args: ["AGENTS.md"])
    head = _git("rev-parse", "HEAD")
    path = tmp_path / "dispositions.json"
    path.write_text(
        json.dumps(
            {
                "schema": drift.DISPOSITIONS_SCHEMA,
                "base_revision": head,
                "head_revision": head,
                "cases": {
                    "GB-001": {
                        "disposition": "NO_GOLDEN_IMPACT",
                        "source_fingerprint": "0" * 64,
                        "rationale": "short",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = drift.check_golden_authority_drift(
        base_ref=head,
        head_ref=head,
        dispositions_path=path,
        root=ROOT,
    )

    assert result["status"] == "FAIL_CLOSED"
    assert "GB-001:stale_source_fingerprint" in result["errors"]
    assert "GB-001:invalid_no_golden_impact_rationale" in result["errors"]


def test_unsafe_authority_path_fails_closed(tmp_path, monkeypatch):
    head = _git("rev-parse", "HEAD")
    cases = drift.CorpusSnapshot(
        cases={
            "GB-X": drift.CaseSnapshot(
                case_id="GB-X",
                status="covered",
                authority_sources=("../outside",),
                automated_tests=(),
                finding_probe=None,
                finding_id=None,
            )
        },
        findings={},
    )
    monkeypatch.setattr(drift, "_load_corpus", lambda *_args, **_kwargs: cases)
    path = tmp_path / "dispositions.json"
    path.write_text(
        json.dumps(
            {
                "schema": drift.DISPOSITIONS_SCHEMA,
                "base_revision": head,
                "head_revision": head,
                "cases": {},
            }
        ),
        encoding="utf-8",
    )

    result = drift.check_golden_authority_drift(
        base_ref=head,
        head_ref=head,
        dispositions_path=path,
        root=ROOT,
    )

    assert result["status"] == "FAIL_CLOSED"
    assert "GB-X:unsafe_authority_path:../outside" in result["errors"]


def test_missing_ref_and_duplicate_json_key_fail_closed(tmp_path):
    head = _git("rev-parse", "HEAD")
    path = tmp_path / "dispositions.json"
    path.write_text(
        '{"schema":"nexus.golden_authority_dispositions.v1",'
        f'"base_revision":"{head}","head_revision":"{head}",'
        '"cases":{},"cases":{}}',
        encoding="utf-8",
    )

    result = drift.check_golden_authority_drift(
        base_ref="refs/heads/does-not-exist",
        head_ref=head,
        dispositions_path=path,
        root=ROOT,
    )

    assert result["status"] == "FAIL_CLOSED"
    assert "base_revision_unavailable" in result["errors"]
    assert "duplicate_json_key:cases" in result["errors"]


def test_finding_cannot_be_promoted_by_mapping_metadata(tmp_path, monkeypatch):
    head = _git("rev-parse", "HEAD")
    finding = drift.CorpusSnapshot(
        cases={
            "GB-F": drift.CaseSnapshot(
                case_id="GB-F",
                status="finding",
                authority_sources=("AGENTS.md",),
                automated_tests=(),
                finding_probe=None,
                finding_id="GBF-X",
            )
        },
        findings={"GBF-X": "Unresolved evidence."},
    )
    monkeypatch.setattr(drift, "_load_corpus", lambda *_args, **_kwargs: finding)
    monkeypatch.setattr(drift, "_changed_paths", lambda *_args: ["AGENTS.md"])
    fingerprint = drift._fingerprint(ROOT, head, finding.cases["GB-F"])
    path = tmp_path / "dispositions.json"
    path.write_text(
        json.dumps(
            {
                "schema": drift.DISPOSITIONS_SCHEMA,
                "base_revision": head,
                "head_revision": head,
                "cases": {
                    "GB-F": {
                        "disposition": "MAPPING_UPDATED",
                        "source_fingerprint": fingerprint,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = drift.check_golden_authority_drift(
        base_ref=head,
        head_ref=head,
        dispositions_path=path,
        root=ROOT,
    )

    assert "GB-F:mapping_cannot_promote_finding" in result["errors"]


def test_report_is_deterministic(tmp_path):
    head = _git("rev-parse", "HEAD")
    path = tmp_path / "dispositions.json"
    path.write_text(
        json.dumps(
            {
                "schema": drift.DISPOSITIONS_SCHEMA,
                "base_revision": head,
                "head_revision": head,
                "cases": {},
            }
        ),
        encoding="utf-8",
    )

    first = drift.check_golden_authority_drift(
        base_ref=head,
        head_ref=head,
        dispositions_path=path,
        root=ROOT,
    )
    second = drift.check_golden_authority_drift(
        base_ref=head,
        head_ref=head,
        dispositions_path=path,
        root=ROOT,
    )

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_malformed_corpus_returns_fail_closed_report(tmp_path, monkeypatch):
    head = _git("rev-parse", "HEAD")
    monkeypatch.setattr(drift, "_git_bytes", lambda *_args: b"not python: [")
    path = tmp_path / "dispositions.json"
    path.write_text(
        json.dumps(
            {
                "schema": drift.DISPOSITIONS_SCHEMA,
                "base_revision": head,
                "head_revision": head,
                "cases": {},
            }
        ),
        encoding="utf-8",
    )

    result = drift.check_golden_authority_drift(
        base_ref=head,
        head_ref=head,
        dispositions_path=path,
        root=ROOT,
    )

    assert result["status"] == "FAIL_CLOSED"
    assert "corpus_unavailable_or_malformed" in result["errors"]
