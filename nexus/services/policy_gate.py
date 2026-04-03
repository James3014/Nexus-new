# nexus/services/policy_gate.py

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import json
from datetime import datetime


class GateSeverity(str, Enum):
    INFO = "info"
    ALERT = "alert"
    WARN = "warn"
    BLOCK = "block"


@dataclass
class GateSignal:
    signal_id: str
    severity: GateSeverity
    score_delta: float
    condition: str
    metadata: Dict[str, Any]


@dataclass
class GateDecision:
    route_id: str
    original_score: float
    gated_score: float
    signals: List[GateSignal]
    decision: GateSeverity
    policy_version: str = "v1.0"


def load_policy_memory(repo_root: Path) -> Path:
    """載入 .nexus/knowledge/policymemory.jsonl"""
    policy_path = repo_root / ".nexus" / "knowledge" / "policymemory.jsonl"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    return policy_path


def apply_policy_gate(
    route_id: str,
    original_score: float,
    phase: str,
    health_metrics: Dict[str, float],
    repo_root: Path,
) -> GateDecision:
    """
    🛡️ Policy Gate: 根據健康指標執行分層治理與權重修正。
    """
    signals = []

    # Signal 1: Phase Health < 0.3 → BLOCK (強制阻斷)
    if health_metrics.get("health_score", 1.0) < 0.3:
        signals.append(GateSignal(
            signal_id="phase-health-block",
            severity=GateSeverity.BLOCK,
            score_delta=-1.0,
            condition="health_score < 0.3",
            metadata={"phase": phase, "health_score": health_metrics["health_score"]},
        ))

    # Signal 2: Phantom FP > 0.2 → WARN (降權重)
    phantom_rate = health_metrics.get("phantom_fp_rate", 0.0)
    if phantom_rate > 0.2:
        delta = -0.3 * phantom_rate
        signals.append(GateSignal(
            signal_id="phantom-fp-warn",
            severity=GateSeverity.WARN,
            score_delta=delta,
            condition="phantom_fp_rate > 0.2",
            metadata={"phantom_fp_rate": phantom_rate},
        ))

    # Signal 3: Pattern Reuse < 0.5 → ALERT (僅告警)
    reuse_rate = health_metrics.get("pattern_reuse", 1.0)
    if reuse_rate < 0.5:
        signals.append(GateSignal(
            signal_id="low-pattern-reuse",
            severity=GateSeverity.ALERT,
            score_delta=0.0,
            condition="pattern_reuse < 0.5",
            metadata={"pattern_reuse": reuse_rate},
        ))

    # 計算 gated score (最低不小於 -1.0)
    gated_score = round(max(-1.0, original_score + sum(s.score_delta for s in signals)), 4)
    
    # 決策判定
    decision = GateSeverity.INFO
    if any(s.severity == GateSeverity.BLOCK for s in signals):
        decision = GateSeverity.BLOCK
    elif any(s.severity == GateSeverity.WARN for s in signals):
        decision = GateSeverity.WARN
    elif any(s.severity == GateSeverity.ALERT for s in signals):
        decision = GateSeverity.ALERT

    # 持久化到 policy memory (.nexus/knowledge/policymemory.jsonl)
    policy_record = {
        "timestamp": datetime.utcnow().isoformat(),
        "route_id": route_id,
        "phase": phase,
        "original_score": original_score,
        "gated_score": gated_score,
        "decision": decision.value,
        "signals": [asdict(s) for s in signals],
        "health_metrics": health_metrics,
        "policy_version": "v1.0",
    }
    
    try:
        policy_path = load_policy_memory(repo_root)
        with open(policy_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(policy_record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"⚠️ [Policy:Fail] Could not persist decision: {e}")

    return GateDecision(
        route_id=route_id,
        original_score=original_score,
        gated_score=gated_score,
        signals=signals,
        decision=decision,
        policy_version="v1.0",
    )
