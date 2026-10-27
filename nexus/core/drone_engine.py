#!/usr/bin/env python3
"""
🧬 Nexus Tactical Drone Engine (Hardenized - Correction v0.9.22)
修正契約斷裂、例外處理錯誤與假陽性成功判定邏輯。
"""
import os
import json
import logging
import time
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional
from nexus.core.layer_ports import resolve_port
from nexus.core.drone_protocol import DroneProtocol

logger = logging.getLogger("nexus.drone")

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
# Admitted local model per docs/arch/MODEL_WORKFORCE_POLICY.md (local_qwen35_9b, L1 ceiling).
DRONE_ADMITTED_MODEL = "qwen3.5:9b"

_ACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["BASH", "EDIT", "DONE"]},
        "command": {"type": "string"},
        "target_file": {"type": "string"},
        "content": {"type": "string"},
        "reasoning": {"type": "string"},
    },
    "required": ["action"],
}


class LocalBonsaiBrain:
    """Drone brain backed by the Ollama chat API (M5 tunnel on NEXUS_OLLAMA_URL).

    Name kept for import compatibility; it no longer speaks the llama-server
    /completion protocol.
    """

    def __init__(self, api_url: Optional[str] = None, model: str = DRONE_ADMITTED_MODEL):
        self.api_url = (api_url or os.environ.get("NEXUS_OLLAMA_URL") or DEFAULT_OLLAMA_URL).rstrip("/")
        self.model = model
        self.last_unavailable_reason = ""

    def health_check(self) -> bool:
        """Pre-flight: Ollama reachable and the admitted model is installed."""
        try:
            res = requests.get(f"{self.api_url}/api/tags", timeout=5)
            if res.status_code != 200:
                self.last_unavailable_reason = f"ollama /api/tags returned HTTP {res.status_code}"
                return False
            names = {str(m.get("name", "")) for m in res.json().get("models", [])}
            if self.model not in names:
                self.last_unavailable_reason = f"model {self.model} not installed at {self.api_url}"
                return False
            return True
        except Exception as exc:
            self.last_unavailable_reason = f"ollama unreachable at {self.api_url}: {exc}"
            return False

    def ask_structured(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        text = ""
        try:
            res = requests.post(
                f"{self.api_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "think": False,
                    "format": _ACTION_SCHEMA,
                    "options": {"temperature": 0.0, "num_predict": 512},
                },
                timeout=120,
            )
            if res.status_code == 200:
                text = str(res.json().get("message", {}).get("content", "")).strip()
                try:
                    return json.loads(text)
                except (json.JSONDecodeError, ValueError):
                    return {"action": "FAIL", "reasoning": "Malformed output", "partial_text": text}
            return {"action": "FAIL", "error": f"Server status {res.status_code}"}
        except Exception as e:
            return {"action": "FAIL", "error": f"Inference crash: {str(e)}", "partial_text": text}

class DroneToolBox:
    def __init__(self, sandbox_dir: Path):
        self.sandbox_dir = sandbox_dir

    def bash_exec(self, command: str) -> Dict[str, Any]:
        # The command is local-model output: run it under the OS sandbox (no network, writes
        # only in sandbox_dir, allowlisted env). Without a barrier, or with the port unbound,
        # nothing runs (#2936).
        try:
            run_model_command_string = resolve_port("model_output.run_model_command_string")
            res = run_model_command_string(command, work_dir=self.sandbox_dir, timeout=30)
            return {"exit_code": res.returncode, "stdout": res.stdout, "stderr": res.stderr}
        except Exception as e:
            return {"exit_code": -1, "stderr": str(e)}

    def file_edit(self, target: str, content: str) -> Dict[str, Any]:
        try:
            path = (self.sandbox_dir / target).resolve()
            # Path containment, not a string prefix: "<dir>EXTRA" must not pass for "<dir>" (#2949).
            if not path.is_relative_to(self.sandbox_dir.resolve()):
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
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.task_intent = ""
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

    def sense_think_act(self, task_intent: str, tools: Optional[List[Any]] = None) -> Dict[str, Any]:
        """[A] 契約對齊：實施 Sprint 強化邏輯。"""
        logger.info(f"🐝 [Drone:{self.drone_id}] Starting cycle (Hardened-Logic v0.9.22)")
        start_time = time.time()
        self.started_at = start_time
        self.task_intent = task_intent
        
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

        # [NEW: R-2] Inject Claims Knowledge to provide priors
        try:
            from nexus.research.learn_mode import LearnModeService
            svc = LearnModeService(self.project_root)
            task_claims = svc.ask(
                topic="drone-tactics", question=task_intent, top_k=3
            )
            if task_claims.get("citations"):
                knowledge_block = "\n".join([
                    f"[Knowledge] {c['claim']}" 
                    for c in task_claims["citations"][:3]
                ])
                messages.insert(1, {
                    "role": "system",
                    "content": f"Historical Knowledge:\n{knowledge_block}"
                })
                self._log_trace("SENSE", f"Injected {len(task_claims['citations'])} historical claims.")
        except Exception as e:
            logger.debug(f"Drone knowledge injection skipped: {e}")


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

                from nexus.core.onebit_core import OneBitGate
                gate = OneBitGate()
                
                # Dynamic complexity: Drone interactions increase threshold rigor
                dynamic_complexity = 1.0 + (len(self.tracelog) * 0.02)
                
                decision = gate.evaluate(self.belief_score, "DONE action evaluated", task_complexity=dynamic_complexity)
                self._log_trace("1-BIT-CORE", f"Verdict: {decision.verdict}, Reasoning: {decision.reasoning}")
                if decision.verdict:
                    outcome = "SUCCESS"
                else:
                    outcome = "REPAIR_NEEDED"
                break
        
        self.status = outcome
        self._finish_mission()
        return {"drone_id": self.drone_id, "outcome": outcome, "belief_final": self.belief_score, "traces": self.tracelog, "metrics": metrics}

    def crystal_path(self) -> Path:
        return self.project_root / ".nexus" / "reports" / "drones" / f"{self.drone_id}_crystal.json"

    def _finish_mission(self) -> None:
        """Persist a real (non-synthetic) crystal for the HUD, on success or failure."""
        self.finished_at = time.time()
        try:
            self.save_evolution_crystal(self.crystal_path())
        except Exception as e:  # reporting must never mask the mission outcome
            logger.warning(f"Drone crystal write failed: {e}")

    def abort_unavailable(self, reason: str) -> Dict[str, Any]:
        """Fail closed without running a mission (e.g. LLM endpoint down); still records a FAIL crystal."""
        now = time.time()
        self.started_at = self.started_at or now
        self._log_trace("ERROR", reason)
        self.status = "FAIL"
        self._finish_mission()
        return {"drone_id": self.drone_id, "outcome": "FAIL", "belief_final": None, "traces": self.tracelog, "error": reason}

    def _log_trace(self, phase: str, message: str):
        self.tracelog.append({"timestamp": time.time(), "phase": phase, "message": message})
        logger.info(f"   [{phase}] {message}")

    def save_evolution_crystal(self, output_path: Path):
        semantic_status = "VERIFIED" if str(self.status).upper() == "SUCCESS" else "UNVERIFIED"
        # A confident score is only meaningful when the run succeeded on real evidence
        # (successful tool action + 1-bit gate verdict). Failed/unverified runs carry no score.
        if semantic_status == "VERIFIED":
            belief_score: Optional[float] = self.belief_score
            belief_reason = "computed from tool-action outcomes and 1-bit gate verdict"
        else:
            belief_score = None
            belief_reason = f"no verified evidence: run status {self.status}"
        payload = {
            "drone_id": self.drone_id,
            "status": self.status,
            "semantic_status": semantic_status,
            "runtime_classification": "verified_pass" if semantic_status == "VERIFIED" else "runtime_execution_failed",
            "belief_score": belief_score,
            "belief_score_reason": belief_reason,
            "synthetic": False,
            "task": self.task_intent,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "tracelog": self.tracelog,
            "artifact_path": str(output_path),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2))
