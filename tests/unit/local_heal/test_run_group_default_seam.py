from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.services.local_heal.context import GovernanceContext, OperationalContext
from nexus.services.local_heal.context import HealContext as HealContextV2
from nexus.services.local_heal.governance_gate import GovernanceGate
from nexus.services.local_heal.orchestrator import HealOrchestrator
from nexus.services.local_heal.receipt import (
    build_repair_receipt,
    canonical_run_group,
    derive_default_run_group,
    write_repair_receipt,
)


class _OpCtx:
    def __init__(self, instance_id: str = "i-1"):
        self.instance_id = instance_id


def _v2_ctx(*, run_group: str | None = None) -> HealContextV2:
    return HealContextV2(
        op=OperationalContext(
            instance_id="seam-i",
            repo_dir=Path("."),
            problem_statement="run-group seam",
            run_group=run_group,
        ),
        gov=GovernanceContext(),
    )


def test_build_receipt_omitted_run_group_derives_deterministic_default() -> None:
    first = build_repair_receipt(_OpCtx("same-id"))
    second = build_repair_receipt(_OpCtx("same-id"))
    assert first["run_group"] == "same-id"
    assert first["run_group"] == second["run_group"]


def test_build_receipt_omitted_run_group_distinct_instances_stay_distinct() -> None:
    first = build_repair_receipt(_OpCtx("group-a"))
    second = build_repair_receipt(_OpCtx("group-b"))
    assert first["run_group"] != second["run_group"]


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        ".",
        "..",
        "../escape",
        "nested/group",
        "nested\\group",
        "bad\nvalue",
        "bad..value",
    ],
)
def test_build_receipt_explicit_invalid_run_group_still_fails_closed(value: object) -> None:
    with pytest.raises(ValueError):
        build_repair_receipt(_OpCtx("i-1"), run_group=value)


def test_write_receipt_omitted_run_group_writes_with_derived_group(tmp_path: Path) -> None:
    ctx = _OpCtx("write-seam")
    receipt_path = write_repair_receipt(ctx, reports_root=tmp_path)
    assert receipt_path.is_file()
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert payload["run_group"] == "write-seam"


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        ".",
        "..",
        "../escape",
        "nested/group",
        "nested\\group",
        "bad\nvalue",
        "bad..value",
    ],
)
def test_write_receipt_explicit_invalid_run_group_fails_before_write(
    tmp_path: Path, value: object
) -> None:
    with pytest.raises(ValueError):
        write_repair_receipt(_OpCtx("i-1"), reports_root=tmp_path / "reports", run_group=value)
    assert not (tmp_path / "reports").exists()


def test_derive_default_run_group_is_deterministic_and_grammar_safe() -> None:
    assert derive_default_run_group(_OpCtx("stable-id")) == "stable-id"
    assert derive_default_run_group(_OpCtx("stable-id")) == "stable-id"
    assert derive_default_run_group(_OpCtx("")) == "default"
    assert canonical_run_group(derive_default_run_group(_OpCtx("p5-i8-test"))) == "p5-i8-test"


def test_orchestrator_resolves_unset_run_group_before_work() -> None:
    seen: list[str] = []

    def receipt_writer(ctx, *, run_group):
        seen.append(run_group)
        return Path("receipt.json")

    orchestrator = HealOrchestrator(
        phases=[],
        governance_gate=GovernanceGate(),
        receipt_writer=receipt_writer,
    )
    ctx = _v2_ctx(run_group=None)
    orchestrator.run(ctx)
    assert ctx.op.run_group == "seam-i"
    assert seen == ["seam-i"]


def test_orchestrator_explicit_empty_run_group_fails_closed_before_work() -> None:
    orchestrator = HealOrchestrator(
        phases=[],
        governance_gate=GovernanceGate(),
        receipt_writer=lambda ctx, *, run_group: Path("receipt.json"),
    )
    with pytest.raises(ValueError):
        orchestrator.run(_v2_ctx(run_group=""))


def test_orchestrator_explicit_unsafe_run_group_fails_closed_before_work() -> None:
    orchestrator = HealOrchestrator(
        phases=[],
        governance_gate=GovernanceGate(),
        receipt_writer=lambda ctx, *, run_group: Path("receipt.json"),
    )
    with pytest.raises(ValueError):
        orchestrator.run(_v2_ctx(run_group="../escape"))
