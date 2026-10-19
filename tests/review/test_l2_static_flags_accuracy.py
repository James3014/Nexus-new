"""Offline accuracy regression on a vendored #1196 round-20 HARD-cohort subset (Refs #2752)."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from nexus.review import l2_static_flags as lib

FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures/l2_static_flags/hard_cohort_subset.jsonl.gz"
)


def _units() -> list[dict]:
    return [json.loads(line) for line in gzip.decompress(FIXTURE.read_bytes()).split(b"\n") if line]


def _run(unit: dict, tmp_path: Path) -> dict:
    root = tmp_path / unit["uid"].replace("|", "_")
    for rel, text in unit["base_files"].items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    for i, text in enumerate(unit["quoting_tests"]):
        p = root / "tests" / f"_quote_{i}.py"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return lib.flag_candidate(unit["diff"], unit["issue_text"], unit["intake_paths"], root)


def test_fixture_flag_rates_and_pinned_checks(tmp_path: Path) -> None:
    assert FIXTURE.stat().st_size < 200_000
    wrong = flagged_wrong = correct = flagged_correct = 0
    slowest = 0
    for unit in _units():
        out = _run(unit, tmp_path)
        assert sorted({f["check"] for f in out["flags"]}) == unit["expect_flags"], unit["uid"]
        slowest = max(slowest, out["elapsed_ms"])
        if unit["label"] == "wrong":
            wrong += 1
            flagged_wrong += bool(out["flags"])
        else:
            correct += 1
            flagged_correct += bool(out["flags"])
    assert wrong >= 30 and correct >= 15
    assert flagged_wrong / wrong >= 0.35, (flagged_wrong, wrong)
    assert flagged_correct / correct <= 0.25, (flagged_correct, correct)
    assert slowest < 1000
