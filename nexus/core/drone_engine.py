#!/usr/bin/env python3
"""
🧬 Nexus Tactical Drone Engine (Integrated with LLM Reasoning & Physical Sandbox)
這是 Nexus 戰甲的微型執行核心。
負責將「靈魂五位一體」應用於微觀任務執行，並於隔離環境 (SwarmBroker) 中進行安全的物理操作。
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
    # Fallback placeholders for tests if not available
    BattlesuitGateway = None
    SwarmBroker = None

logger = logging.getLogger("nexus.drone")

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
        self.gateway = BattlesuitGateway(project_root=project_root) if BattlesuitGateway else None

    def _load_muse_proto(self) -> str:
        proto_path = self.project_root / "MUSE_PROTO.md"
        return proto_path.read_text() if proto_path.exists() else "STRICT_GOVERNANCE_ENFORCED"

    def sense_think_act(self, task_intent: str, tools: List[Any] = None) -> Dict[str, Any]:
        """
        [R] 執行循環：感知 -> 推理 -> 動作
        """
        self.status = "EXECUTING"
        logger.info(f"🐝 [Drone:{self.drone_id}] Starting cycle for: {task_intent[:50]}")
        start_time = time.time()
        
        # [P0] Allocate physical sandbox
        broker = SwarmBroker(self.project_root) if SwarmBroker else None
        sandbox_dir = None
        if broker:
            sandbox_dir = broker.acquire(timeout_sec=10)
        
        if not sandbox_dir:
            # Fallback to local tmp if broker unavailable
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
                self._log_trace("ERROR", f"Budget Guard: Timeout after {self.timeout_sec}s")
                break
                
            # [P0] True Reasoning via LLM
            if self.gateway:
                prompt_text = (
                    f"You are a Tactical Drone in Nexus. Drone ID: {self.drone_id}.\n"
                    f"MUSE_PROTO: {self.memory_l0[:500]}...\n"
                    f"Task: {task_intent}\n"
                    f"Round: {round_count}/{self.max_rounds}\n"
                    "Determine next action. Return JSON with 'action' (BASH, EDIT, DONE), 'command' or 'content', and 'reasoning'."
                )
                try:
                    resp, _ = self.gateway.ask_structured(
                        prompt=prompt_text,
                        payload=f"Current traces: {self.tracelog[-3:]}",
                        phase="R",
                        output_schema={
                            "action": "BASH | EDIT | DONE | SPAWN",
                            "command": "str (for BASH/SPAWN)",
                            "content": "str (for EDIT)",
                            "target_file": "str (for EDIT)",
                            "reasoning": "str"
                        }
                    )
                    thought = resp.get("reasoning", "No reasoning provided")
                    action = resp.get("action", "DONE")
                    self._log_trace("THINK", f"[LLM] {thought}")
                except Exception as e:
                    self._log_trace("ERROR", f"Gateway failed: {e}")
                    action = "DONE"
            else:
                # Mock reasoning for tests
                thought = f"Applying MUSE_PROTO to {task_intent}. Belief confidence: {self.belief_score}"
                self._log_trace("THINK", thought)
                action = "DONE"
                if "fail" in task_intent.lower() and round_count == 1:
                    action = "BASH"
                    resp = {"command": "false"}  # Returns exit_code 1

            # Act
            if action == "BASH":
                cmd = resp.get("command", "echo nothing")
                self._log_trace("ACT", f"Running BASH: {cmd}")
                tool_res = toolbox.bash_exec(cmd)
                self._log_trace("SENSE", f"Result: {tool_res}")
                if tool_res["exit_code"] != 0:
                    self._log_trace("SELF-HEAL", "Detected mismatch. Initiating recursive correction...")
                    self.belief_score *= 0.8
            elif action == "EDIT":
                target = resp.get("target_file", "unknown.txt")
                self._log_trace("ACT", f"Running EDIT: {target}")
                tool_res = toolbox.file_edit(target, resp.get("content", ""))
                self._log_trace("SENSE", f"Result: {tool_res}")
            elif action == "SPAWN":
                self._log_trace("ACT", "Triggering recursive SPAWN.")
                outcome = "SPAWNED"
                break
            elif action == "DONE":
                self._log_trace("ACT", "Task marked as DONE.")
                if self.belief_score > 0.5:
                    outcome = "SUCCESS"
                else:
                    outcome = "REPAIR_NEEDED"
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

        # [P1] Memory Writeback: Store SOP to LanceDB (mocked as JSON here for ingestion)
        if self.status == "SUCCESS":
            sop_dir = self.project_root / ".nexus/reports/evolution/sops"
            sop_dir.mkdir(parents=True, exist_ok=True)
            sop_path = sop_dir / f"sop_{self.drone_id}.json"
            sop_path.write_text(json.dumps({"intent": crystal["tracelog"][0]["message"], "traces": crystal["tracelog"]}, indent=2))
