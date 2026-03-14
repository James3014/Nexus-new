#!/usr/bin/env python3
import sys
import json
import os
import time
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from nexus.services.git import GitManager
from nexus.services.llm import LLMClient
from nexus.services.linter import Linter
from nexus.services.patcher import SafePatcher
from nexus.services.reporter import Reporter
from nexus.services.workspace import WorkspaceManager
from nexus.core.escalation import EscalationPolicy
from nexus.core.router import SkillsRouter
from nexus.core.commander import Commander
from nexus.core.context_hub import ContextHub
from nexus.core.state_io import StateIO

class NexusOrchestrator:
    """
    🎭 Nexus v9 Orchestrator
    負責編排 P-D-R-A-C 生命週期。
    """
    def __init__(
        self, 
        task: str, 
        skill_id: str, 
        mode: str = "developer",
        git=None,
        llm=None,
        linter=None,
        patcher=None,
        reporter=None,
        workspace=None,
        router=None,
        commander=None,
        context_hub=None,
        state_io=None
    ):
        self.task = task
        self.skill_id = skill_id
        self.mode = mode
        self.project_root = Path.cwd()
        
        # 🛠️ Service Injection (Provided by NexusContainer)
        self.git = git
        self.llm = llm
        self.linter = linter
        self.patcher = patcher
        self.reporter = reporter
        self.workspace = workspace
        self.router = router
        self.commander = commander
        self.context_hub = context_hub
        self.state_io = state_io
        
        self.total_tokens = 0
        self.max_strikes = 3 if mode != "audit" else 1

    def run_review(self) -> bool:
        """核心門禁審核邏輯"""
        print(f"🎭 [Orchestrator] Reviewing task: {self.task}")
        
        # 1. Setup Environment
        # 2. Strike Loop
        return self._do_loop()

    def _do_loop(self) -> bool:
        strike = 0
        while strike < self.max_strikes:
            strike += 1
            print(f"🚀 [Round {strike}/{self.max_strikes}] Running loop...")
            
            # 1. RAG 注入: 從 Context Hub 獲取 Crystal 結晶 (Lessons)
            lessons = self.commander.get_crystal_lessons(relevance=0.8)
            context_brief = "\n".join([f"💎 Lesson: {l}" for l in lessons[:3]])
            
            # 獲取變更
            files, diff = self.git.get_changes("staged")
            if not files and not diff.strip():
                return True
                
            # 2. 模型專屬 Prompt 與 LLM 審核
            data, raw = self.llm.ask_with_template(
                task=f"{self.task}\n{context_brief}", 
                diff=diff,
                model_hint="flash" if strike % 2 != 0 else "sonnet"
            )
            self.total_tokens += data.get("tokens_used", 0)
            
            # 3. 迭代自省 (Self-Critique)
            if self.mode != "audit" and data.get("status") != "PASS":
                self._save_reflection(data, strike)
                if self._should_self_critique(data):
                    print(f"🔄 [FlashJudge] Self-critique triggered (Confidence: {data.get('confidence')}), retrying inner loop...")
                    continue

            if data.get("status") == "PASS":
                return True
            
            # 如果失敗，嘗試自癒或升級
            print(f"⚠️ Failed: {data.get('summary')}")
        return False

    def _save_reflection(self, data: dict, strike: int):
        """將模型自省結果存入 reflection.jsonl"""
        reflection_file = self.project_root / "reflection.jsonl"
        payload = {
            "timestamp": datetime.now().isoformat(),
            "strike": strike,
            "status": data.get("status"),
            "confidence": data.get("confidence", 1.0),
            "summary": data.get("summary"),
            "skill_id": self.skill_id
        }
        with open(reflection_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _should_self_critique(self, response_data: dict) -> bool:
        """FlashJudge 邏輯: 判斷是否需要自評再審。"""
        # 模擬 FlashJudge 7.5 門檻
        confidence = response_data.get("confidence", 1.0)
        return confidence < 0.75
