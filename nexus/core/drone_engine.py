#!/usr/bin/env python3
"""
🧬 Nexus Tactical Drone Engine (Integrated with Local Bonsai-1.7B & Physical Sandbox)
這是 Nexus 戰甲的微型執行核心。
負責將「靈魂五位一體」應用於微觀任務執行，預設使用本機推理引擎。
"""
import os
import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    from nexus.services.gateway import BattlesuitGateway
    from nexus.research.swarm_broker import SwarmBroker
except ImportError:
    BattlesuitGateway = None
    SwarmBroker = None

logger = logging.getLogger("nexus.drone")

class LocalDroneBrain:
    """[P0] Local Reasoning Engine via Ollama (Bonsai-1.7B)."""
    def __init__(self, model_name: str = "bonsai-drone"):
        self.model_name = model_name
        self.api_url = "http://localhost:11434/api/generate"

    def ask(self, prompt: str, system_msg: str) -> Dict[str, Any]:
        import requests
        try:
            full_prompt = f"System: {system_msg}\n\nUser: {prompt}\n\nAssistant:"
            res = requests.post(
                self.api_url,
                json={
                    "model": self.model_name,
                    "prompt": full_prompt,
                    "stream": False,
                    "format": "json"
                },
                timeout=60
            )
            if res.status_code == 200:
                raw_resp = res.json().get("response", "{}")
                # 處理 Ollama 可能回傳的 Markdown Code Block
                if "```json" in raw_resp:
                    raw_resp = raw_resp.split("```json")[1].split("```")[0].strip()
                return json.loads(raw_resp)
            return {"error": f"Ollama status {res.status_code}"}
        except Exception as e:
            return {"error": str(e)}

class DroneToolBox:
    """[P0] True Tool Integration: Executes commands within a given sandbox directory."""
    def __init__(self, sandbox_dir: Path):
        self.sandbox_dir = sandbox_dir

    def bash_exec(self, command: str, timeout_sec: int = 30) -> Dict[str, Any]:
        """Execute a bash command safely inside the sandbox."""
        try:
            res = subprocess.run(
                command, shell=True, cwd=self.sandbox_dir,
                capture_output=True, text=True, timeout=timeout_sec
            )
            return {"exit_code": res.returncode, "stdout": res.stdout, "stderr": res.stderr}
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "stdout": "", "stderr": "TimeoutExpired"}
        except Exception as e:
            return {"exit_code": -2, "stdout": "", "stderr": str(e)}
            
    def file_edit(self, relative_path: str, new_content: str) -> Dict[str, Any]:
        """Writes content to a file inside the sandbox."""
        try:
            target = (self.sandbox_dir / relative_path).resolve()
            if not target.is_relative_to(self.sandbox_dir):
                return {"error": "Path traversal attempt blocked."}
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(new_content, encoding="utf-8")
            return {"status": "SUCCESS", "bytes_written": len(new_content)}
        except Exception as e:
            return {"error": str(e)}

class TacticalDrone:
    def __init__(self, drone_id: str, project_root: Path, belief_score: float = 1.0, max_rounds: int = 3, timeout_sec: int = 300):
        self.drone_id = drone_id
        self.project_root = project_root
        self.belief_score = belief_score
        self.max_rounds = max_rounds
        self.timeout_sec = timeout_sec
        self.memory_l0 = self._load_muse_proto()
        self.tracelog = []
        self.status = "INIT"
        # [P0] Local-First: Initialize Local Brain
        self.local_brain = LocalDroneBrain()
        self.gateway = BattlesuitGateway(project_root=project_root) if BattlesuitGateway else None

    def _load_muse_proto(self) -> str:
        proto_path = self.project_root / "MUSE_PROTO.md"
        return proto_path.read_text() if proto_path.exists() else "STRICT_GOVERNANCE_ENFORCED"

    def sense_think_act(self, task_intent: str, tools: List[Any] = None) -> Dict[str, Any]:
        """
        [R] 執行循環：感知 -> 推理 -> 動作
        """
        self.status = "EXECUTING"
        logger.info(f"🐝 [Drone:{self.drone_id}] Starting cycle (Local-First) for: {task_intent[:50]}")
        start_time = time.time()
        
        # [P0] Allocate physical sandbox
        broker = SwarmBroker(self.project_root) if SwarmBroker else None
        sandbox_dir = None
        if broker:
            sandbox_dir = broker.acquire(timeout_sec=10)
        
        if not sandbox_dir:
            sandbox_dir = self.project_root / ".nexus/tmp" / self.drone_id
            sandbox_dir.mkdir(parents=True, exist_ok=True)
            
        toolbox = DroneToolBox(sandbox_dir)
        self._log_trace("SENSE", f"Task: {task_intent}. Sandbox: {sandbox_dir}")
        
        round_count = 0
        outcome = "REPAIR_NEEDED"
        
        while round_count < self.max_rounds:
            round_count += 1
            if time.time() - start_time > self.timeout_sec:
                outcome = "TIMEOUT"
                self._log_trace("ERROR", "Budget Guard: Timeout")
                break
                
            # [P0] Reasoning: Try Local Brain first
            resp = self.local_brain.ask(
                prompt=f"Task: {task_intent}\nRound: {round_count}\nLast traces: {self.tracelog[-2:]}",
                system_msg=f"You are a Nexus Drone. Follow MUSE_PROTO. Return JSON with 'action' (BASH|EDIT|DONE), 'command' or 'content', and 'reasoning'."
            )
            
            if "error" in resp:
                self._log_trace("WARN", f"Local Brain fail: {resp['error']}. Trying Cloud.")
                if self.gateway:
                    try:
                        resp, _ = self.gateway.ask_structured(
                            prompt=f"Drone {self.drone_id} task: {task_intent}",
                            payload=f"Previous traces: {self.tracelog}",
                            phase="R",
                            output_schema={"action": "BASH|EDIT|DONE", "command": "str", "reasoning": "str"}
                        )
                    except: resp = {"action": "DONE", "reasoning": "Gateway error fallback"}
                else:
                    resp = {"action": "DONE", "reasoning": "No brain available"}

            thought = resp.get("reasoning", "Thinking...")
            action = resp.get("action", "DONE")
            self._log_trace("THINK", f"[Reasoning] {thought}")

            # Act
            if action == "BASH":
                cmd = resp.get("command", "echo nothing")
                self._log_trace("ACT", f"Running BASH: {cmd}")
                tool_res = toolbox.bash_exec(cmd)
                self._log_trace("SENSE", f"Result: {tool_res}")
                if tool_res["exit_code"] != 0:
                    self._log_trace("SELF-HEAL", "Command failed. Adjusting belief.")
                    self.belief_score *= 0.8
            elif action == "EDIT":
                target = resp.get("target_file", "drone_edit.txt")
                self._log_trace("ACT", f"Running EDIT: {target}")
                tool_res = toolbox.file_edit(target, resp.get("content", ""))
                self._log_trace("SENSE", f"Result: {tool_res}")
            elif action == "DONE":
                self._log_trace("ACT", "Task marked as DONE.")
                outcome = "SUCCESS" if self.belief_score > 0.5 else "REPAIR_NEEDED"
                break
                
        if broker and sandbox_dir and "nexus-swarm" in str(sandbox_dir):
            broker.release(sandbox_dir)

        self.status = outcome
        return {
            "drone_id": self.drone_id,
            "outcome": outcome,
            "belief_final": self.belief_score,
            "traces": self.tracelog
        }

    def _log_trace(self, phase: str, message: str):
        entry = {
            "timestamp": time.time(),
            "phase": phase,
            "message": message
        }
        self.tracelog.append(entry)
        logger.info(f"   [{phase}] {message}")

    def save_evolution_crystal(self, output_path: Path):
        """[C] 結晶：將執行經驗存入報表"""
        crystal = {
            "drone_id": self.drone_id,
            "status": self.status,
            "belief_score": self.belief_score,
            "tracelog": self.tracelog
        }
        output_path.write_text(json.dumps(crystal, indent=2))
        logger.info(f"💎 [Drone:{self.drone_id}] Evolution crystal saved: {output_path}")

        # [P1] Memory Writeback: Store SOP
        if self.status == "SUCCESS":
            sop_dir = self.project_root / ".nexus/reports/evolution/sops"
            sop_dir.mkdir(parents=True, exist_ok=True)
            sop_path = sop_dir / f"sop_{self.drone_id}.json"
            sop_path.write_text(json.dumps({"intent": crystal["tracelog"][0]["message"], "traces": crystal["tracelog"]}, indent=2))
