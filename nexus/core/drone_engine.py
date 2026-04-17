#!/usr/bin/env python3
"""
🧬 Nexus Tactical Drone Engine (Hardenized via PrismML Fork)
使用專屬編譯的 llama-server 對接 Bonsai-1.7B 1-bit 模型。
"""
import os
import json
import logging
import subprocess
import time
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    from nexus.services.gateway import BattlesuitGateway
    from nexus.research.swarm_broker import SwarmBroker
except ImportError:
    BattlesuitGateway = None
    SwarmBroker = None

logger = logging.getLogger("nexus.drone")

class LocalBonsaiBrain:
    """[P0] Dedicated Brain for Bonsai-1.7B using Custom llama-server."""
    def __init__(self, api_url: str = "http://localhost:11435"):
        self.api_url = api_url

    def ask_structured(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        try:
            # 轉換為 ChatML 模板
            prompt = ""
            for m in messages:
                role = m["role"]
                content = m["content"]
                prompt += f"<|im_start|>{role}\n{content}<|im_end|>\n"
            prompt += "<|im_start|>assistant\n"

            # GBNF Grammar (簡化版以提高速度)
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
                    "n_predict": 512, # 增加長度以防字串截斷
                    "grammar": grammar
                },
                timeout=60
            )
            if res.status_code == 200:
                text = res.json().get("content", "").strip()
                
                # [Hardening] 容錯解析邏輯
                try:
                    return json.loads(text)
                except:
                    # 嘗試手動修復不完整的 JSON
                    if not text.endswith("}"):
                        text += '"}' if text.endswith('"') else '" }'
                    if '"reasoning":' in text and not text.endswith('"}'):
                        text += '"}'
                    return json.loads(text)
                    
            return {"error": f"Server status {res.status_code}"}
        except Exception as e:
            # 最後的 Fallback: 若連修復都失敗，嘗試正則提取
            import re
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try: return json.loads(match.group())
                except: pass
            return {"error": str(e)}

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
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return {"status": "SUCCESS"}
        except Exception as e:
            return {"error": str(e)}

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

    def sense_think_act(self, task_intent: str) -> Dict[str, Any]:
        logger.info(f"🐝 [Drone:{self.drone_id}] Starting cycle (Custom-Core Integration)")
        start_time = time.time()
        
        sandbox_dir = self.project_root / ".nexus/tmp" / self.drone_id
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        toolbox = DroneToolBox(sandbox_dir)
        
        messages = [
            {"role": "system", "content": "You are a Nexus Drone. Use tools. Return JSON: {\"action\": \"BASH|EDIT|DONE\", \"command\": \"...\", \"reasoning\": \"...\"}"},
            {"role": "user", "content": task_intent}
        ]

        for r in range(self.max_rounds):
            if time.time() - start_time > self.timeout_sec:
                self._log_trace("ERROR", "Timeout exceeded")
                self.status = "TIMEOUT"
                break

            self._log_trace("THINK", f"Round {r+1}/{self.max_rounds} reasoning...")
            resp = self.local_brain.ask_structured(messages)
            
            if "error" in resp:
                self._log_trace("ERROR", resp["error"])
                break
            
            action = resp.get("action", "DONE")
            reasoning = resp.get("reasoning", "Thinking...")
            self._log_trace("DECISION", f"{action}: {reasoning}")
            
            if action == "BASH":
                res = toolbox.bash_exec(resp.get("command", "ls"))
                self._log_trace("SENSE", f"BASH Result: {res}")
                messages.append({"role": "assistant", "content": json.dumps(resp)})
                messages.append({"role": "user", "content": f"BASH Result: {res}"})
                if res["exit_code"] != 0: self.belief_score *= 0.8
            elif action == "EDIT":
                res = toolbox.file_edit(resp.get("target_file", "output.txt"), resp.get("content", ""))
                self._log_trace("SENSE", f"EDIT Result: {res}")
                messages.append({"role": "assistant", "content": json.dumps(resp)})
                messages.append({"role": "user", "content": f"EDIT Result: {res}"})
            else:
                self.status = "SUCCESS"
                break
        
        return {"drone_id": self.drone_id, "outcome": self.status, "traces": self.tracelog}

    def _log_trace(self, phase: str, message: str):
        self.tracelog.append({"timestamp": time.time(), "phase": phase, "message": message})
        logger.info(f"   [{phase}] {message}")

    def save_evolution_crystal(self, output_path: Path):
        output_path.write_text(json.dumps({"drone_id": self.drone_id, "tracelog": self.tracelog}, indent=2))
