#!/usr/bin/env python3
"""Benchmark policy matching quality: baseline proxy vs current v4 router.

Notes:
- "baseline" here is a strict lexical proxy (not historical runtime code).
- v4 uses AutonomicRouter.route(...).matched_policies from current codebase.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from nexus.core.state_contracts import NexusState
from nexus.engine.autonomic_router import AutonomicRouter

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "nexus" / "knowledge" / "policy_memory.jsonl"


@dataclass
class Case:
    name: str
    task: str
    expected_tags: list[str]  # substring(s) expected in matched rule_id


CASES: list[Case] = [
    Case("deterministic_fix_en", "Execution of high-frequency automated bug fixes for OFF-001 pattern", ["DETERMINISTIC"]),
    Case("deterministic_fix_zh", "優化自動化修復循環，確保執行序列具備 100% 確定性", ["DETERMINISTIC"]),
    Case("glass_en", "Applying glassmorphism effects in dashboard components", ["GLASS"]),
    Case("glass_zh", "為 Dashboard 核心組件實現玻璃擬態效果", ["GLASS"]),
    Case("state_guard", "Implement strict state transition guard to block invalid bypass", ["STATE"]),
    Case("python_import", "Fix NameError by adding missing os import in research phase module", ["IMPORT"]),
    Case("deploy_perm", "Fix permission denied during deploy script execution", ["DEPLOY", "PERM"]),
    Case("audit_strike", "When audit fails 3 times escalate to intervention protocol", ["AUDIT"]),
    Case("api_health", "Add a /health endpoint for API readiness checks", ["API", "HEALTH"]),
    Case("skill_opt", "Optimize skill and require validation status ok", ["SKILL"]),
    Case("noise_marketing", "Write a marketing landing page headline", []),
    Case("noise_recipe", "Generate a pasta recipe", []),
]


def load_policies(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def baseline_proxy_match(task: str, policies: Iterable[dict]) -> list[str]:
    """Strict lexical proxy: full condition term-set must be mostly covered by task words.

    This is intentionally strict to simulate a weaker pre-fuzzy matcher.
    """
    t = words(task)
    out: list[str] = []
    for p in policies:
        cond = str(p.get("condition", ""))
        c = words(cond)
        if not c:
            continue
        overlap = len(t & c) / len(c)
        if overlap >= 0.8:
            rid = str(p.get("rule_id", ""))
            if rid:
                out.append(rid)
    return out


def case_has_expected(hits: list[str], expected_tags: list[str]) -> bool:
    if not expected_tags:
        return False
    for h in hits:
        hu = h.upper()
        if any(tag.upper() in hu for tag in expected_tags):
            return True
    return False


def run() -> int:
    policies = load_policies(POLICY_PATH)
    router = AutonomicRouter(str(ROOT))

    expected_cases = [c for c in CASES if c.expected_tags]
    negative_cases = [c for c in CASES if not c.expected_tags]

    b_tp = b_fp = v_tp = v_fp = 0

    print(f"policies_loaded={len(policies)}")
    print("name | baseline_hits | v4_hits | baseline_ok | v4_ok")
    print("-" * 72)

    for c in CASES:
        b_hits = baseline_proxy_match(c.task, policies)
        v_hits = router.route(c.task, NexusState(task_id="bench"), {"est_tokens": 100}).matched_policies

        b_ok = case_has_expected(b_hits, c.expected_tags)
        v_ok = case_has_expected(v_hits, c.expected_tags)

        if c.expected_tags:
            b_tp += int(b_ok)
            v_tp += int(v_ok)
        else:
            b_fp += int(len(b_hits) > 0)
            v_fp += int(len(v_hits) > 0)

        print(f"{c.name} | {len(b_hits):>3} | {len(v_hits):>3} | {str(b_ok):>5} | {str(v_ok):>5}")

    b_hit_rate = b_tp / max(1, len(expected_cases))
    v_hit_rate = v_tp / max(1, len(expected_cases))
    b_fp_rate = b_fp / max(1, len(negative_cases))
    v_fp_rate = v_fp / max(1, len(negative_cases))

    print("\nsummary")
    print(json.dumps(
        {
            "expected_case_count": len(expected_cases),
            "negative_case_count": len(negative_cases),
            "baseline_proxy": {
                "hit_cases": b_tp,
                "hit_rate": round(b_hit_rate, 4),
                "fp_cases": b_fp,
                "fp_rate": round(b_fp_rate, 4),
            },
            "v4_current": {
                "hit_cases": v_tp,
                "hit_rate": round(v_hit_rate, 4),
                "fp_cases": v_fp,
                "fp_rate": round(v_fp_rate, 4),
            },
            "delta": {
                "hit_rate": round(v_hit_rate - b_hit_rate, 4),
                "fp_rate": round(v_fp_rate - b_fp_rate, 4),
            },
            "note": "baseline_proxy is a strict lexical proxy, not historical v3 runtime code",
        },
        ensure_ascii=False,
        indent=2,
    ))

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
