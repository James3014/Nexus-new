#!/usr/bin/env python3
"""
🧠 Nexus Hallucination Index Guard v1.0
自動標註 Agent 回覆的幻覺風險，綁定 CritiqueEngine。
"""

import re
import os
from typing import Dict, List
import json

class HallucinationGuard:
    def __init__(self):
        self.schema = self.load_schema()
        self.score = 0
        self.triggers: List[str] = []
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
                "evidence_gap": {"weight": 7}
            },
            "thresholds": {"VERIFIED": 2, "PARTIAL": 5, "REJECTED": 6},
            "output_template": "\n## 🧠 幻覺指數: {score}/10 ({status}) - {verdict}"
        }
    
    def analyze(self, response_text: str, evidence_bundle: Dict = None) -> Dict:
        """核心分析，0-10 分"""
        self.response_text = response_text
        self.evidence_bundle = evidence_bundle or {}
        self.score = 0
        self.triggers = []
        
        # 1. Restricted claims (高風險詞彙)
        metrics = self.schema.get("metrics", {})
        if "restricted_claims" in metrics:
            metric = metrics["restricted_claims"]
            for word in metric["keywords"]:
                if re.search(rf'\b{re.escape(word)}\b', response_text, re.I):
                    self.score += metric["weight"]
                    self.triggers.append(f"{word} (+{metric['weight']})")
        
        # 2. Evidence gap
        if "evidence_gap" in metrics:
            if not evidence_bundle or len(evidence_bundle.get("code_artifacts", [])) == 0:
                self.score += metrics["evidence_gap"]["weight"]
                self.triggers.append("evidence_gap (+7)")
        
        # 3. Self-grading (有證據的 mild overclaim)
        if "self_grading" in metrics:
            if re.search(r'100(?:/100|%)', response_text, re.I) and "pytest" in response_text.lower():
                self.score += metrics["self_grading"]["weight"]
                self.triggers.append("self_grading (+1)")
        
        # Cap score at 10
        if self.score > 10: self.score = 10.0
            
        status = self.get_status()
        return {
            "score": round(float(self.score), 1),
            "status": status,
            "triggers": ", ".join(self.triggers) if self.triggers else "None",
            "verdict": self.get_verdict(status)
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
