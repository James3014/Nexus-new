#!/usr/bin/env python3
"""
🧬 Nexus Tactical Drone Engine (Hardenized - Correction v0.9.22)
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
from nexus.core.drone_protocol import DroneProtocol

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

class TacticalDrone(DroneProtocol):
    def __init__(self, drone_id: str, project_root: Path, belief_score: float = 1.0, max_rounds: int = 3, timeout_sec: int = 300):
        self.drone_id = drone_id
        self.project_root = project_root
        self.belief_score = belief_score
        self.max_rounds = max_rounds
        self.timeout_sec = timeout_sec
        self.tracelog = []
        self.status = "INIT"
        self.local_brain = LocalBonsaiBrain()

    def normalize_action(self, raw: str) -> str:
        if not raw:
            return "UNKNOWN"
        raw_upper = str(raw).strip().upper()
        # [Task A] Expanded aliases for legal actions
        if raw_upper in ["CREATE", "WRITE", "PATCH", "EDIT", "ADD", "UPDATE", "MODIFY", "SAVE"]:
            return "EDIT"
        if raw_upper in ["SHELL", "CMD", "EXEC", "BASH", "RUN", "SEARCH", "FIND", "READ", "LS", "CAT", "PWD", "COMMAND", "READ_FILE", "MKDIR", "RM", "MV", "CP", "GIT", "DELETE", "REMOVE"]:
            return "BASH"
        if raw_upper in ["FINISH", "COMPLETE", "DONE", "EXIT", "STOP", "SUCCESS", "END", "QUIT"]:
            return "DONE"
        return "UNKNOWN"

    def repair_response_schema(self, resp: Dict[str, Any]) -> Dict[str, Any]:
        """[Task B] Action Repair Layer"""
        if not isinstance(resp, dict):
            return resp
        raw_action = str(resp.get("action", "")).upper()
        
        # 1. CREATE/WRITE with target/content -> EDIT
        if raw_action in ["CREATE", "WRITE", "PATCH", "ADD", "SAVE"]:
            target = resp.get("target") or resp.get("target_file")
            content = resp.get("content")
            if target and content is not None:
                resp["action"] = "EDIT"
                resp["target_file"] = target
                
        # 2. SHELL/CMD/EXEC with command -> BASH
        elif raw_action in ["SHELL", "CMD", "EXEC", "RUN", "READ_FILE"]:
            command = resp.get("command") or resp.get("cmd")
            if command:
                resp["action"] = "BASH"
                resp["command"] = command
                
        # 3. DONE without reasoning -> DONE with "completed"
        elif raw_action in ["FINISH", "COMPLETE", "DONE", "STOP"]:
            resp["action"] = "DONE"
            if "reasoning" not in resp:
                resp["reasoning"] = "completed"
                
        return resp

    def sense_think_act(self, task_intent: str, tools: List[Any] = None) -> Dict[str, Any]:
        """[A] 契約對齊：實施 Sprint 強化邏輯。"""
        logger.info(f"🐝 [Drone:{self.drone_id}] Starting cycle (Hardened-Logic v0.9.22)")
        start_time = time.time()
        
        sandbox_dir = self.project_root / ".nexus/tmp" / self.drone_id
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        toolbox = DroneToolBox(sandbox_dir)
        
        system_prompt = (
            "You are a Nexus Drone. Follow MUSE_PROTO. Must return strict JSON.\n"
            "Contract: action MUST be BASH, EDIT, or DONE.\n"
            "Allowed actions only: BASH, EDIT, DONE. Do NOT output DONE unless you have used BASH or EDIT to satisfy the request.\n"
            "- BASH requires 'command'.\n"
            "- EDIT requires 'target_file' and 'content'.\n"
            "- DONE requires 'reasoning'.\n"
            "Examples:\n"
            '{"action": "EDIT", "target_file": "main.py", "content": "print(1)", "reasoning": "Creating file"}\n'
            '{"action": "BASH", "command": "ls -l", "reasoning": "Listing files"}\n'
            '{"action": "DONE", "reasoning": "Task completed successfully"}'
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task_intent}
        ]

        outcome = "FAIL"
        consecutive_invalid_count = 0
        has_successful_tool_action = False
        last_tool_action_successful = False
        
        metrics = {
            "invalid_before_repair_count": 0,
            "invalid_after_repair_count": 0,
            "repair_applied_count": 0,
            "action_histogram": {"BASH": 0, "EDIT": 0, "DONE": 0, "UNKNOWN": 0}
        }

        for r in range(self.max_rounds):
            if time.time() - start_time > self.timeout_sec:
                self._log_trace("ERROR", "Timeout")
                outcome = "TIMEOUT"
                break

            self._log_trace("THINK", f"Round {r+1} reasoning...")
            
            loop_messages = list(messages)
            last_msg = loop_messages[-1].copy()
            last_msg["content"] = last_msg["content"] + "\nCurrent objective: produce ONE valid tool action now. You must BASH or EDIT to make progress before DONE."
            loop_messages[-1] = last_msg
            
            resp = self.local_brain.ask_structured(loop_messages)
            
            original_raw = str(resp.get("action", ""))
            original_action = self.normalize_action(original_raw)
            if original_action == "UNKNOWN":
                metrics["invalid_before_repair_count"] += 1
                
            original_resp = dict(resp) if isinstance(resp, dict) else resp
            resp = self.repair_response_schema(resp)
            
            if isinstance(resp, dict) and (resp != original_resp or str(resp.get("action", "")).upper() != str(original_raw).upper()):
                metrics["repair_applied_count"] += 1
                
            raw_action = resp.get("action", "UNKNOWN") if isinstance(resp, dict) else "UNKNOWN"
            action = self.normalize_action(raw_action)
            reasoning = resp.get("reasoning", "No reasoning") if isinstance(resp, dict) else "No reasoning"
            
            if action not in metrics["action_histogram"]:
                metrics["action_histogram"][action] = 0
            metrics["action_histogram"][action] += 1
            
            self._log_trace("DECISION", f"{action}: {reasoning} (raw: {raw_action})")
            
            missing_fields = False
            if action == "BASH" and not resp.get("command"):
                missing_fields = True
            elif action == "EDIT" and (not resp.get("target_file") or "content" not in resp):
                missing_fields = True
                
            # [Task C] 3-Strike Policy
            if action == "UNKNOWN" or missing_fields:
                self.belief_score *= 0.5
                metrics["invalid_after_repair_count"] += 1
                consecutive_invalid_count += 1
                
                if consecutive_invalid_count == 1:
                    self._log_trace("WARN", "Invalid action 1st attempt. Retrying with schema feedback.")
                    messages.append({"role": "assistant", "content": json.dumps(resp) if isinstance(resp, dict) else str(resp)})
                    messages.append({"role": "user", "content": "Invalid schema: require action=BASH|EDIT|DONE with required fields. Return JSON only. Allowed actions only: BASH, EDIT, DONE."})
                    continue
                elif consecutive_invalid_count == 2:
                    self._log_trace("WARN", "Invalid action 2nd attempt. Fallback to safe BASH: pwd.")
                    if not isinstance(resp, dict): resp = {}
                    action = "BASH"
                    resp["action"] = "BASH"
                    resp["command"] = "pwd"
                    missing_fields = False
                    # Do not reset count yet, let it run pwd and see next round
                else:
                    self._log_trace("ERROR", "Invalid action 3rd attempt. Forcing FAIL as per protocol.")
                    outcome = "FAIL"
                    break
            else:
                # Valid action from model, reset strike count
                consecutive_invalid_count = 0

            if action == "BASH":
                res = toolbox.bash_exec(resp.get("command", ""))
                self._log_trace("SENSE", f"BASH Result: {res}")
                messages.append({"role": "assistant", "content": json.dumps(resp)})
                messages.append({"role": "user", "content": f"BASH Result: {res}"})
                if res["exit_code"] != 0: 
                    self._log_trace("SELF-HEAL", "Detected mismatch. Initiating recursive correction...")
                    self.belief_score *= 0.8
                    last_tool_action_successful = False
                else:
                    has_successful_tool_action = True
                    last_tool_action_successful = True
            elif action == "EDIT":
                res = toolbox.file_edit(resp.get("target_file", ""), resp.get("content", ""))
                self._log_trace("SENSE", f"EDIT Result: {res}")
                messages.append({"role": "assistant", "content": json.dumps(resp)})
                messages.append({"role": "user", "content": f"EDIT Result: {res}"})
                if res.get("status") == "FAIL": 
                    self._log_trace("SELF-HEAL", "Detected mismatch. Initiating recursive correction...")
                    self.belief_score *= 0.5
                    last_tool_action_successful = False
                else:
                    has_successful_tool_action = True
                    last_tool_action_successful = True
            elif action == "DONE":
                # [Task A] DONE Gate: Check for successful tool action first
                if not (has_successful_tool_action and last_tool_action_successful):
                    self._log_trace("WARN", "DONE rejected: perform a valid BASH/EDIT action with successful result first.")
                    messages.append({"role": "assistant", "content": json.dumps(resp) if isinstance(resp, dict) else str(resp)})
                    messages.append({"role": "user", "content": "DONE rejected: perform a valid BASH/EDIT action with successful result first."})
                    outcome = "REPAIR_NEEDED"
                    continue

                if self.belief_score > 0.5:
                    outcome = "SUCCESS"
                else:
                    outcome = "REPAIR_NEEDED"
                break
        
        self.status = outcome
        return {"drone_id": self.drone_id, "outcome": outcome, "belief_final": self.belief_score, "traces": self.tracelog, "metrics": metrics}

    def _log_trace(self, phase: str, message: str):
        self.tracelog.append({"timestamp": time.time(), "phase": phase, "message": message})
        logger.info(f"   [{phase}] {message}")

    def save_evolution_crystal(self, output_path: Path):
        output_path.write_text(json.dumps({"drone_id": self.drone_id, "status": self.status, "belief_score": self.belief_score, "tracelog": self.tracelog}, indent=2))
