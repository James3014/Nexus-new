"""Caller-chain witnesses for the source-owned Runtime writer port."""

from pathlib import Path


def test_canonical_seam_resolves_loaded_factory_and_forwards_it(monkeypatch, tmp_path):
    from nexus.engine.canonical_task_seam import execute_canonical_product_task

    factory = object()
    captured = {}

    monkeypatch.setattr(
        "nexus.orchestrator.writer_quiescence.lookup_runtime_writer_factory",
        lambda root: factory,
    )

    class Gateway:
        def __init__(self, project_root):
            captured["root"] = Path(project_root)

        def ask_unified(self, request, **kwargs):
            captured["request"] = request
            captured["factory"] = kwargs["runtime_writer_factory"]
            receipt = {
                "terminal_status": "SUCCEEDED",
                "receipt_complete": True,
                "canonical_execution": {"execution_decision_authority": "CapabilityPlanner"},
                "root_receipt": {"schema": "nexus.root_receipt.v1"},
            }
            path = Path(kwargs["receipt_path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(__import__("json").dumps(receipt), encoding="utf-8")
            return receipt

    monkeypatch.setattr("nexus.services.gateway.BattlesuitGateway", Gateway)
    monkeypatch.setattr(
        "nexus.contracts.root_receipt.validate_root_receipt",
        lambda _root: (True, []),
    )

    result = execute_canonical_product_task(
        "audit bounded runtime",
        tmp_path,
        execution_context={
            "task_id": "runtime-writer-chain",
            "workspace_revision": "fixture-revision",
            "local_assist_mode": "disabled",
            "online_policy": "auto",
        },
    )

    assert bool(result) is True
    assert captured["root"] == tmp_path.resolve()
    assert captured["factory"] is factory


def test_canonical_seam_preserves_missing_factory_as_fail_closed_carrier(monkeypatch, tmp_path):
    from nexus.engine.canonical_task_seam import execute_canonical_product_task

    captured = {}
    monkeypatch.setattr(
        "nexus.orchestrator.writer_quiescence.lookup_runtime_writer_factory",
        lambda _root: None,
    )

    class Gateway:
        def __init__(self, project_root):
            pass

        def ask_unified(self, request, **kwargs):
            captured["factory"] = kwargs["runtime_writer_factory"]
            receipt = {
                "terminal_status": "SUCCEEDED",
                "receipt_complete": True,
                "canonical_execution": {"execution_decision_authority": "CapabilityPlanner"},
                "root_receipt": {"schema": "nexus.root_receipt.v1"},
            }
            path = Path(kwargs["receipt_path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(__import__("json").dumps(receipt), encoding="utf-8")
            return receipt

    monkeypatch.setattr("nexus.services.gateway.BattlesuitGateway", Gateway)
    monkeypatch.setattr(
        "nexus.contracts.root_receipt.validate_root_receipt",
        lambda _root: (True, []),
    )

    execute_canonical_product_task(
        "audit legacy runtime",
        tmp_path,
        execution_context={
            "task_id": "runtime-writer-missing",
            "workspace_revision": "fixture-revision",
            "local_assist_mode": "disabled",
            "online_policy": "auto",
        },
    )

    assert captured["factory"] is None
