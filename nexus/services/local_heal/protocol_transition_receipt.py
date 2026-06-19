"""Protocol transition dry-run receipt module."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import json


@dataclass
class ProtocolTransitionReceipt:
    receipt_id: str
    task_id: str
    model: str
    source_stage: str
    old_path: dict
    new_path: dict
    comparison: dict
    governance: dict
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema: str = "nexus.protocol_transition_receipt.v0"


def create_receipt(
    receipt_id: str,
    task_id: str,
    model: str,
    source_stage: str,
    old_path: dict,
    new_path: dict,
    comparison: dict,
) -> ProtocolTransitionReceipt:
    governance = {
        "dry_run_only": True,
        "routing_changed": False,
        "execution_changed": False,
        "llm_calls": False,
        "patch_apply": False,
        "verifier_run": False,
        "m6_executed": False,
        "training_export": False,
        "public_claim_allowed": False,
    }
    return ProtocolTransitionReceipt(
        receipt_id=receipt_id,
        task_id=task_id,
        model=model,
        source_stage=source_stage,
        old_path=old_path,
        new_path=new_path,
        comparison=comparison,
        governance=governance,
    )


def to_dict(receipt: ProtocolTransitionReceipt) -> dict:
    return {
        "schema": receipt.schema,
        "receipt_id": receipt.receipt_id,
        "created_at": receipt.created_at,
        "task_id": receipt.task_id,
        "model": receipt.model,
        "source_stage": receipt.source_stage,
        "old_path": receipt.old_path,
        "new_path": receipt.new_path,
        "comparison": receipt.comparison,
        "governance": receipt.governance,
    }
