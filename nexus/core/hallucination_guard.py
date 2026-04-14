#!/usr/bin/env python3
"""
🧠 Nexus Hallucination Index Guard v1.0
自動標註 Agent 回覆的幻覺風險，綁定 CritiqueEngine。
"""

import re
import os
from typing import Any, Dict, List
import json

class HallucinationGuard:
    def __init__(self):
        self.schema = self.load_schema()
        self.score = 0
        self.triggers: List[str] = []
        self.trigger_details: List[Dict[str, Any]] = []
        self.response_text = ""
        self.evidence_bundle = {}
    
    def load_schema(self) -> Dict:
        path = os.path.join(os.path.dirname(__file__), "../schemas/hallucination_index_v1.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        # Fallback if file missing
        return {
            "metrics": {
                "restricted_claims": {"weight": 5, "keywords": ["solved", "fixed"]},
                "evidence_gap": {"weight": 7, "check": "no_code_or_log_attached"}
            },
            "thresholds": {"VERIFIED": 2, "PARTIAL": 5, "REJECTED": 6},
            "output_template": "\n## 🧠 幻覺指數: {score}/10 ({status}) - {verdict}"
        }

    def _iter_artifact_values(self) -> List[str]:
        values: List[str] = []
        if not isinstance(self.evidence_bundle, dict):
            return values
        for key in ("code_artifacts", "test_artifacts", "command_artifacts", "log_artifacts"):
            entries = self.evidence_bundle.get(key, [])
            if isinstance(entries, list):
                for entry in entries:
                    values.append(str(entry))
            elif entries:
                values.append(str(entries))
        return values

    def _has_any_artifact(self) -> bool:
        return len(self._iter_artifact_values()) > 0

    def _check_no_code_or_log_attached(self) -> bool:
        if not isinstance(self.evidence_bundle, dict):
            return True
        code = self.evidence_bundle.get("code_artifacts", [])
        logs = self.evidence_bundle.get("test_artifacts", [])
        cmds = self.evidence_bundle.get("command_artifacts", [])
        return not bool(code) and not bool(logs) and not bool(cmds)

    def _check_self_100_percent_with_evidence(self) -> bool:
        text = self.response_text.lower()
        return bool(re.search(r"100(?:/100|%)", self.response_text, re.I) and "pytest" in text)

    def _check_status_claim_without_evidence(self) -> bool:
        return not self._has_any_artifact()

    def _check_contradiction_with_failed_artifacts(self) -> bool:
        text = self.response_text.lower()
        success_claimed = any(
            token in text for token in ("completed", "done", "success", "passed", "fixed", "verified", "完成", "成功", "已完成")
        )
        if not success_claimed:
            return False
        evidence_blob = "\n".join(self._iter_artifact_values()).lower()
        fail_markers = (" fail", "failed", "error", "traceback", "returncode\": 1", "returncode=1", "exit code: 1", "exit_code\": 1")
        return any(marker in evidence_blob for marker in fail_markers)

    def _match_keywords(self, response_text: str, keywords: List[str], word_boundary: bool = True) -> List[str]:
        matches: List[str] = []
        for word in keywords:
            if word_boundary:
                pattern = rf"\b{re.escape(word)}\b"
            else:
                pattern = re.escape(word)
            if re.search(pattern, response_text, re.I):
                matches.append(word)
        return matches

    def _apply_trigger(self, rule_id: str, weight: float, detail: str) -> None:
        self.score += weight
        self.triggers.append(f"{rule_id}:{detail} (+{weight})")
        self.trigger_details.append({"rule_id": rule_id, "detail": detail, "weight": weight})

    def analyze(self, response_text: str, evidence_bundle: Dict = None) -> Dict:
        """核心分析，0-10 分"""
        self.response_text = response_text
        self.evidence_bundle = evidence_bundle or {}
        self.score = 0
        self.triggers = []
        self.trigger_details = []

        metrics = self.schema.get("metrics", {})
        forced_rejected = False
        for rule_id, metric in metrics.items():
            if not isinstance(metric, dict):
                continue
            weight = float(metric.get("weight", 0))
            keywords = metric.get("keywords", [])
            word_boundary = bool(metric.get("word_boundary", True))
            matched = False

            if isinstance(keywords, list) and keywords:
                hits = self._match_keywords(response_text, keywords, word_boundary=word_boundary)
                if hits:
                    matched = True
                    self._apply_trigger(rule_id, weight, f"keywords={','.join(hits)}")

            check_name = metric.get("check")
            if isinstance(check_name, str) and check_name:
                check_fn = getattr(self, f"_check_{check_name}", None)
                if callable(check_fn) and check_fn():
                    # Avoid double score when both keywords and check trigger in same rule.
                    if not matched:
                        self._apply_trigger(rule_id, weight, f"check={check_name}")
                    if bool(metric.get("force_rejected", False)):
                        forced_rejected = True

        # Cap score at 10
        if self.score > 10:
            self.score = 10.0

        status = "REJECTED" if forced_rejected else self.get_status()
        return {
            "score": round(float(self.score), 1),
            "status": status,
            "triggers": ", ".join(self.triggers) if self.triggers else "None",
            "trigger_details": self.trigger_details,
            "verdict": self.get_verdict(status),
        }
    
    def get_status(self) -> str:
        score = self.score
        thresholds = self.schema["thresholds"]
        if score <= thresholds["VERIFIED"]: return "VERIFIED"
        elif score <= thresholds["PARTIAL"]: return "PARTIAL"
        return "REJECTED"
    
    def get_verdict(self, status: str) -> str:
        return {"VERIFIED": "🟢 安全", "PARTIAL": "🟡 需審核", "REJECTED": "🔴 重做"}[status]
    
    def render(self) -> str:
        """產生 Markdown 標註"""
        analysis = self.analyze(self.response_text, self.evidence_bundle)
        return self.schema["output_template"].format(
            score=analysis["score"],
            status=analysis["status"],
            triggers=analysis["triggers"],
            verdict=analysis["verdict"]
        )
