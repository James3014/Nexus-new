#!/usr/bin/env python3
"""
🧬 Nexus Tactical Drone Engine (Hardenized - Correction v0.9.21)
修正契約斷裂、例外處理錯誤與假陽性成功判定邏輯。
"""
import os
import json
import logging
import subprocess
import time
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger("nexus.drone")

class LocalBonsaiBrain:
    """[P0] Dedicated Brain for Bonsai-1.7B using Custom llama-server."""
    def __init__(self, api_url: str = "http://localhost:11435"):
        self.api_url = api_url

    def ask_structured(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        text = "" # 修正 UnboundLocalError: 預先定義變數
        try:
            prompt = ""
            for m in messages:
                role = m["role"]
                content = m["content"]
                prompt += f"<|im_start|>{role}\n{content}<|im_end|>\n"
            prompt += "<|im_start|>assistant\n"

            grammar = r'''
                root   ::= object
                object ::= "{" space pair ( "," space pair )* "}" space
                pair   ::= string ":" space value
                string ::= "\"" [^"]* "\""
                value  ::= string | number | object | array | "true" | "false" | "null"
                number ::= [0-9]+
                array  ::= "[" space ( value ( "," space value )* )? "]" space
                space  ::= [ \t\n\r]*
            '''

            res = requests.post(
                f"{self.api_url}/completion",
                json={
                    "prompt": prompt,
                    "stop": ["<|im_end|>"],
                    "temperature": 0.0,
                    "n_predict": 512,
                    "grammar": grammar
                },
                timeout=60
            )
            if res.status_code == 200:
                text = res.json().get("content", "").strip()
                try:
                    return json.loads(text)
                except:
                    # [Hardening] 更安全的 JSON Repair
                    if not text.startswith("{"): return {"action": "FAIL", "reasoning": "Malformed output"}
                    if not text.endswith("}"): text += '"}' if text.endswith('"') else '" }'
                    return json.loads(text)
            return {"action": "FAIL", "error": f"Server status {res.status_code}"}
        except Exception as e:
            return {"action": "FAIL", "error": f"Inference crash: {str(e)}", "partial_text": text}

class DroneToolBox:
    def __init__(self, sandbox_dir: Path):
        self.sandbox_dir = sandbox_dir

    def bash_exec(self, command: str) -> Dict[str, Any]:
        try:
            res = subprocess.run(command, shell=True, cwd=self.sandbox_dir, capture_output=True, text=True, timeout=30)
            return {"exit_code": res.returncode, "stdout": res.stdout, "stderr": res.stderr}
        except Exception as e:
            return {"exit_code": -1, "stderr": str(e)}

    def file_edit(self, target: str, content: str) -> Dict[str, Any]:
        try:
            path = (self.sandbox_dir / target).resolve()
            if not str(path).startswith(str(self.sandbox_dir.resolve())):
                return {"status": "FAIL", "error": "Path traversal blocked"}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return {"status": "SUCCESS"}
        except Exception as e:
            return {"status": "FAIL", "error": str(e)}

class TacticalDrone:
    def __init__(self, drone_id: str, project_root: Path, belief_score: float = 1.0, max_rounds: int = 3, timeout_sec: int = 300):
        self.drone_id = drone_id
        self.project_root = project_root
        self.belief_score = belief_score
        self.max_rounds = max_rounds
        self.timeout_sec = timeout_sec
        self.tracelog = []
        self.status = "INIT"
        self.local_brain = LocalBonsaiBrain()

    def sense_think_act(self, task_intent: str, tools: List[Any] = None) -> Dict[str, Any]:
        """[A] 契約對齊：接受 task_intent 與可選 tools 參數。"""
        logger.info(f"🐝 [Drone:{self.drone_id}] Starting cycle (Hardened-Logic)")
        start_time = time.time()
        
        sandbox_dir = self.project_root / ".nexus/tmp" / self.drone_id
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        toolbox = DroneToolBox(sandbox_dir)
        
        messages = [
            {"role": "system", "content": "You are a Nexus Drone. Follow MUSE_PROTO. Must return explicit action: BASH | EDIT | DONE."},
            {"role": "user", "content": task_intent}
        ]

        outcome = "FAIL" # [B] 預設為 FAIL，防範假陽性

        for r in range(self.max_rounds):
            if time.time() - start_time > self.timeout_sec:
                self._log_trace("ERROR", "Timeout")
                outcome = "TIMEOUT"
                break

            self._log_trace("THINK", f"Round {r+1} reasoning...")
            resp = self.local_brain.ask_structured(messages)
            
            action = resp.get("action", "UNKNOWN") # 禁止預設 DONE
            reasoning = resp.get("reasoning", "No reasoning")
            self._log_trace("DECISION", f"{action}: {reasoning}")
            
            if action == "BASH":
                res = toolbox.bash_exec(resp.get("command", "ls"))
                self._log_trace("SENSE", f"BASH Result: {res}")
                messages.append({"role": "assistant", "content": json.dumps(resp)})
                messages.append({"role": "user", "content": f"BASH Result: {res}"})
                if res["exit_code"] != 0: 
                    self._log_trace("SELF-HEAL", "Detected mismatch. Initiating recursive correction...")
                    self.belief_score *= 0.8
            elif action == "EDIT":
                res = toolbox.file_edit(resp.get("target_file", "out.txt"), resp.get("content", ""))
                self._log_trace("SENSE", f"EDIT Result: {res}")
                messages.append({"role": "assistant", "content": json.dumps(resp)})
                messages.append({"role": "user", "content": f"EDIT Result: {res}"})
                if res.get("status") == "FAIL": self.belief_score *= 0.5
            elif action == "DONE":
                # 只有明確 DONE 且信念足夠才算成功
                if self.belief_score > 0.5:
                    outcome = "SUCCESS"
                else:
                    outcome = "REPAIR_NEEDED"
                break
            else:
                # [B] 未知 Action 直接判 FAIL 並終止
                self._log_trace("ERROR", f"Invalid action: {action}")
                outcome = "FAIL"
                break
        
        self.status = outcome
        return {"drone_id": self.drone_id, "outcome": outcome, "belief_final": self.belief_score, "traces": self.tracelog}

    def _log_trace(self, phase: str, message: str):
        self.tracelog.append({"timestamp": time.time(), "phase": phase, "message": message})
        logger.info(f"   [{phase}] {message}")

    def save_evolution_crystal(self, output_path: Path):
        output_path.write_text(json.dumps({"drone_id": self.drone_id, "status": self.status, "belief_score": self.belief_score, "tracelog": self.tracelog}, indent=2))
