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
    def __init__(self, task: str, skill_id: str, mode: str = "developer"):
        self.task = task
        self.skill_id = skill_id
        self.mode = mode
        self.project_root = Path.cwd()
        
        # 🛠️ Service Initialization
        self.git = GitManager()
        self.llm = LLMClient(project_root=str(self.project_root))
        self.linter = Linter()
        self.patcher = SafePatcher()
        self.reporter = Reporter()
        self.workspace = WorkspaceManager(str(self.project_root))
        self.router = SkillsRouter(project_root=str(self.project_root))
        self.commander = Commander(str(self.project_root))
        self.state_io = StateIO(str(self.project_root))
        
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
                if self._should_self_critique(data):
                    print("🔄 [FlashJudge] Self-critique triggered, retrying inner loop...")
                    continue

            if data.get("status") == "PASS":
                return True
            
            # 如果失敗，嘗試自癒或升級
            print(f"⚠️ Failed: {data.get('summary')}")
        return False

    def _should_self_critique(self, response_data: dict) -> bool:
        """FlashJudge 邏輯: 判斷是否需要自評再審。"""
        # 模擬 FlashJudge 7.5 門檻
        confidence = response_data.get("confidence", 1.0)
        return confidence < 0.75
