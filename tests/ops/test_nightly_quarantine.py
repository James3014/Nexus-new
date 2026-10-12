from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from tests.nightly_quarantine import (
    QUARANTINE_ENV,
    QuarantineEntry,
    apply_quarantine,
    load_quarantine,
    quarantine_enabled,
    quarantine_reasons,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_every_quarantined_id_names_an_existing_test_with_a_cause() -> None:
    entries = load_quarantine()
    assert entries
    reasons = quarantine_reasons(entries)
    assert len(reasons) == sum(len(entry.tests) for entry in entries)
    for entry in entries:
        source = (REPO_ROOT / entry.file).read_text(encoding="utf-8")
        for test in entry.tests:
            function = test.split("::")[-1].split("[", 1)[0]
            assert re.search(rf"def {re.escape(function)}\(", source), f"{entry.file}::{test}"


def test_duplicate_ids_are_rejected() -> None:
    entry = QuarantineEntry("tests/x.py", "quarantine", "TBD", "cause", ("test_a",))
    with pytest.raises(ValueError, match="duplicate"):
        quarantine_reasons((entry, entry))


def test_quarantine_is_opt_in_by_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(QUARANTINE_ENV, raising=False)
    assert quarantine_enabled() is False
    monkeypatch.setenv(QUARANTINE_ENV, "1")
    assert quarantine_enabled() is True


def test_apply_marks_only_listed_items_as_non_strict_xfail() -> None:
    class _Item:
        def __init__(self, nodeid: str) -> None:
            self.nodeid = nodeid
            self.markers: list[pytest.MarkDecorator] = []

        def add_marker(self, marker: pytest.MarkDecorator) -> None:
            self.markers.append(marker)

    listed, other = _Item("tests/x.py::test_a"), _Item("tests/x.py::test_b")
    entry = QuarantineEntry("tests/x.py", "quarantine", "TBD", "cause", ("test_a",))
    assert apply_quarantine([listed, other], quarantine_reasons((entry,))) == 1
    assert other.markers == []
    (marker,) = listed.markers
    assert marker.name == "xfail"
    assert marker.kwargs["strict"] is False
    assert "cause" in marker.kwargs["reason"]


def test_only_the_scheduled_full_regression_enables_the_quarantine() -> None:
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github/workflows/pytest.yml").read_text(encoding="utf-8")
    )
    enabled = []
    for job_id, job in workflow["jobs"].items():
        for step in job.get("steps", []):
            if (step.get("env") or {}).get(QUARANTINE_ENV) is not None:
                enabled.append((job_id, step.get("name")))
    assert enabled == [("full-regression", "Run full repository regression")]
    job = workflow["jobs"]["full-regression"]
    assert (
        job["if"] == "github.event_name == 'workflow_dispatch' || github.event_name == 'schedule'"
    )
