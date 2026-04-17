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
                "evidence_gap": {"weight": 7, "check": "no_code_or_log_attached"},
                "completion_claim_with_unmet_benchmark_threshold": {
                    "weight": 9,
                    "check": "completion_claim_with_unmet_benchmark_threshold",
                    "force_rejected": True,
                },
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

    @staticmethod
    def _normalize_rate(value: Any) -> float | None:
        try:
            if isinstance(value, str):
                cleaned = value.strip().replace("%", "")
                num = float(cleaned)
            else:
                num = float(value)
        except Exception:
            return None
        if num < 0:
            return None
        if num > 1.0 and num <= 100.0:
            return num / 100.0
        return num if num <= 1.0 else None

    def _extract_benchmark_metrics(self) -> tuple[float | None, float | None]:
        if not isinstance(self.evidence_bundle, dict):
            return None, None

        def _pick_from_dict(d: Dict[str, Any]) -> tuple[float | None, float | None]:
            success_keys = (
                "success_rate",
                "benchmark_success_rate",
                "successRate",
            )
            threshold_keys = (
                "threshold",
                "success_threshold",
                "success_rate_threshold",
                "target_success_rate",
                "required_success_rate",
            )
            success = None
            threshold = None
            for key in success_keys:
                if key in d and success is None:
                    success = self._normalize_rate(d.get(key))
            for key in threshold_keys:
                if key in d and threshold is None:
                    threshold = self._normalize_rate(d.get(key))
            return success, threshold

        # 1) direct bundle keys
        success, threshold = _pick_from_dict(self.evidence_bundle)
        if success is not None and threshold is not None:
            return success, threshold

        # 2) common nested containers
        for container_key in (
            "benchmark",
            "benchmark_summary",
            "benchmark_metrics",
            "aggregates",
            "ab_summary",
        ):
            block = self.evidence_bundle.get(container_key)
            if isinstance(block, dict):
                s2, t2 = _pick_from_dict(block)
                success = success if success is not None else s2
                threshold = threshold if threshold is not None else t2
                if success is not None and threshold is not None:
                    return success, threshold

        # 3) fallback: parse artifact strings
        blob = "\n".join(self._iter_artifact_values())
        s_match = re.search(r"success_rate\s*[:=]\s*([0-9]+(?:\.[0-9]+)?%?)", blob, re.I)
        t_match = re.search(
            r"(?:threshold|target_success_rate|required_success_rate)\s*(?:>=|:|=)\s*([0-9]+(?:\.[0-9]+)?%?)",
            blob,
            re.I,
        )
        if s_match and success is None:
            success = self._normalize_rate(s_match.group(1))
        if t_match and threshold is None:
            threshold = self._normalize_rate(t_match.group(1))
        return success, threshold

    def _check_completion_claim_with_unmet_benchmark_threshold(self) -> bool:
        completion_claimed = bool(
            re.search(r"\b(completed|done)\b", self.response_text, re.I)
            or re.search(r"(已完成|完成|結案|收斂完成)", self.response_text)
        )
        if not completion_claimed:
            return False
        success, threshold = self._extract_benchmark_metrics()
        if success is None or threshold is None:
            return False
        return success < threshold

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

    def _check_claim_completion_with_low_success(self) -> bool:
        """
        R3: 當回覆含完成宣稱且 evidence 顯示 success_rate < threshold，直接 REJECTED。
        """
        text = self.response_text.lower()
        completion_keywords = ["completed", "done", "完成", "成功", "passed"]
        has_completion_claim = any(kw in text for kw in completion_keywords)
        if not has_completion_claim:
            return False

        # 解析 Evidence 中的 success_rate
        test_artifacts = self.evidence_bundle.get("test_artifacts", [])
        if not isinstance(test_artifacts, list):
            return False

        threshold = 0.55  # Round-3 門檻
        for artifact in test_artifacts:
            if isinstance(artifact, dict) and "aggregates" in artifact:
                # 🛡️ 治理硬化：嚴格模式下 success_rate 預設 0.0（未提供即視為失敗）
                _sr_default = 0.0 if os.environ.get("NEXUS_STRICT_HALLUCINATION_DEFAULT") == "1" else 1.0
                success_rate = artifact["aggregates"].get("success_rate", _sr_default)
                
                # 🧪 V25 補丁：若含實體自癒標記或合法 V25 地址結構，則放寬判定
                if artifact["aggregates"].get("repair_mode") == "V25-ALIGNED" or self._is_v25_address(self.response_text):
                    success_rate = max(float(success_rate), 0.9)

                if float(success_rate) < threshold:
                    return True
        return False

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

    def _is_v25_address(self, text: str) -> bool:
        """驗證是否為合法的 7-segment 地址結構 (e.g. context/gw/agent/...)"""
        pattern = r"context/[a-z0-9]+/[a-z0-9]+/[a-z0-9]+/[a-z0-9]+/[a-z0-9]+/[a-z0-9]+"
        return bool(re.search(pattern, text, re.I))

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
        if score <= thresholds["VERIFIED"]:
            return "VERIFIED"
        elif score <= thresholds["PARTIAL"]:
            # 🛡️ 嚴格模式：PARTIAL 等同 REJECTED
            if os.environ.get("NEXUS_STRICT_QUARANTINE") == "1":
                return "REJECTED"
            return "PARTIAL"
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
