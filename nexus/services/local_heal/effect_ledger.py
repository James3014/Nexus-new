from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class EffectLedgerRow:
    case_id: str
    source: str  # counterfactual_fixture | historical_replay | real_model_shadow
    phase: str  # P5 | P6
    p5_off_selected_index: int
    p5_on_selected_index: int
    selection_changed: bool
    p5_selected_hash_matches_p4: bool
    memory_trace_status: str  # TRACE_AVAILABLE | TRACE_MISSING | NOT_USED
    memory_sources: list[str]
    trace_event_count: int
    fuzzy_backend_used: bool
    learning_closure_ref: str
    findings_memory_card_id: str
    decision_eligible_memory: bool = False
    audit_only_memory: bool = True
    claim_level: str = "controlled"  # controlled | shadow | verified

    def to_jsonl_row(self) -> dict[str, Any]:
        return asdict(self)


class EffectLedger:
    """P5/P6 effect ledger — evaluation artifact, NOT runtime memory store."""

    def __init__(self, path: str = "artifacts/effect_reports/p5_effect_ledger_v0.jsonl"):
        self.path = path
        self.rows: list[EffectLedgerRow] = []

    def append(self, row: EffectLedgerRow) -> None:
        # Validate claim_level
        if row.claim_level == "shadow" and row.source != "real_model_shadow":
            row.claim_level = "controlled"
        if row.claim_level == "shadow" and row.trace_event_count <= 0:
            row.claim_level = "controlled"
        if row.claim_level == "verified":
            row.claim_level = "controlled"  # No verifier evidence → cannot claim verified
        self.rows.append(row)

    def save(self) -> None:
        import os
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            for row in self.rows:
                f.write(json.dumps(row.to_jsonl_row()) + "\n")

    def load(self) -> list[EffectLedgerRow]:
        rows = []
        try:
            with open(self.path) as f:
                for line in f:
                    data = json.loads(line)
                    rows.append(EffectLedgerRow(**data))
        except FileNotFoundError:
            pass
        self.rows = rows
        return rows

    def summary(self) -> dict[str, Any]:
        claim_levels = {}
        for row in self.rows:
            claim_levels[row.claim_level] = claim_levels.get(row.claim_level, 0) + 1
        return {
            "total_rows": len(self.rows),
            "claim_level_distribution": claim_levels,
            "selection_changed_count": sum(1 for r in self.rows if r.selection_changed),
            "memory_trace_available_count": sum(1 for r in self.rows if r.memory_trace_status == "TRACE_AVAILABLE"),
        }
