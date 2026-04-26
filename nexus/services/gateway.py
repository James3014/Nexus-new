from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import subprocess
import json
import logging
import fcntl
import re
import tempfile
import os
import sys

from nexus.services.gemini_cli import (
    build_gemini_env,
    build_gemini_cli_invocation,
    extract_token_info,
    resolve_binary,
    DEFAULT_GEMINI_CANDIDATES,
    DEFAULT_NODE_CANDIDATES,
)

logger = logging.getLogger(__name__)

# 🛡️ Nexus v16 Battlesuit Gateway (De-LLM-ized Edition)
# This module is strictly PASSIVE. It handles physical handoffs to the agent.

try:
    from nexus.engine.phases.base import BasePhaseHandler
except ImportError:
    class BasePhaseHandler:
        def __init__(self, *args, **kwargs): pass

try:
    from nexus.core.state_contracts import NexusState
except ImportError:
    NexusState = Any


class BattlesuitGateway:
    """
    🛡️ Nexus Battlesuit Gateway (物理戰甲閘道)
    取代原有的 LLMClient。不具備主動推理能力，僅負責「物理交接 (Handoff)」。
    """

    def __init__(self, bin_path=None, lock_file=None, project_root=None):
        self.lock_file = lock_file or os.getenv("NEXUS_LOCK_FILE", "/tmp/nexus_battlesuit.lock")
        self.project_root = Path(project_root or ".")
        
        # 🛡️ Battlesuit Origin: 僅支援 OAuth CLI 與物理 Handoff
        self.use_oauth = True
        self.oauth_provider = os.getenv("NEXUS_OAUTH_PROVIDER", "gemini")
        # 🛡️ Compatibility for legacy scripts
        self.llm_bin = self.oauth_provider
        
        # ❌ OPENAI SDK REMOVED (De-LLM-ized)
        self.client = None

        try:
            from nexus.services.prompt_builder import PromptBuilder
            self.prompt_builder = PromptBuilder(str(self.project_root))
        except (ImportError, TypeError):
            self.prompt_builder = None # type: ignore

    def get_anti_token_estimate(self) -> int:
        """估計戰甲外部消耗量。"""
        try:
            log_folder = self.project_root / ".nexus" / "transcripts"
            total = 0
            for f in log_folder.glob("*.md"):
                total += len(f.read_text()) // 4
            return total
        except Exception as e:
            logger.debug("Token estimation failed: %s", e)
            return 0

    OUTPUT_SCHEMA = {
        "status": "APPROVED | REJECTED | FAIL",
        "summary": "Short explanation",
        "violations": ["list of rule violations"],
    }

    def _build_system_instruction(
        self,
        output_schema: Dict[str, Any],
        system_instruction: Optional[str] = None,
    ) -> str:
        base = system_instruction or "You are the pilot of the Nexus Battlesuit v16."
        return (
            f"{base} "
            "Return ONLY valid JSON. Do not wrap the answer in markdown. "
            f"Required output shape: {json.dumps(output_schema, ensure_ascii=False)}"
        )

    def _build_error_result(self, summary, category="gateway_error", telemetry: Optional[Dict[str, Any]] = None):
        result = {
            "status": "FAIL",
            "summary": summary,
            "violations": [],
            "tokens_used": 0,
            "error_category": category,
        }
        if isinstance(telemetry, dict):
            result.update(telemetry)
        return result

    def ask_with_template(
        self, task: str, diff: str, task_id: str = "unknown", model_hint: str = "flash", phase: str = "R"
    ) -> tuple[Any, str]:
        """產出交接 Payload (支援 v23 橋接回饋)。"""
        if self.prompt_builder:
            full_payload = self.prompt_builder.build_full_payload(
                phase, task, diff, task_id, model_hint
            )
            return self.ask(full_payload, "", phase=phase)
        return self.ask(task, diff, phase=phase)

    def model_selector(self, phase: str) -> str:
        """被動映射模型名稱。"""
        return "gemini-3-flash-preview" if phase in ["R", "A"] else "gemini-2.5-flash-lite"

    def ask(self, prompt, payload, phase="P", second_opinion=False):
        """
        執行物理交接 (Handoff)。
        Nexus 作為戰甲，將請求轉發給外部 CLI 或產出 Handoff 文件。
        """
        model_name = self.model_selector(phase)
        full_content = f"{prompt}\n\n[PAYLOAD/DIFF]\n{payload}"
        
        # 🛡️ 核心邏輯：僅允許透過 CLI 路徑進行通訊
        sys_msg = self._build_system_instruction(self.OUTPUT_SCHEMA)
        return self._ask_via_cli(full_content, model_name, sys_msg)

    def ask_structured(
        self,
        prompt: str,
        payload: str,
        *,
        phase: str = "R",
        output_schema: Optional[Dict[str, Any]] = None,
        system_instruction: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> tuple[Any, str]:
        """Night Shift / automation path: request arbitrary structured JSON through the battlesuit."""
        selected_model = model_name or self.model_selector(phase)
        full_content = f"{prompt}\n\n[PAYLOAD]\n{payload}"
        schema = output_schema or self.OUTPUT_SCHEMA
        sys_msg = self._build_system_instruction(schema, system_instruction)
        return self._ask_via_cli(full_content, selected_model, sys_msg)

    def _ask_via_cli(self, content: str, model_name: str, sys_msg: str, complexity_score: float = 0.5):
        """🛡️ Battlesuit Forwarding (v24.0 Enhanced - Bayesian Adaptive)"""
        import time
        max_retries = int(os.getenv("NEXUS_GATEWAY_MAX_RETRIES", "3"))
        last_err = ""
        
        # 🧪 [Bayesian Timeout Adaptive]
        dynamic_timeout = int(60 + (complexity_score * 120))
        timeout_override = os.getenv("NEXUS_GATEWAY_TIMEOUT_SEC")
        if timeout_override:
            try:
                dynamic_timeout = min(dynamic_timeout, max(5, int(timeout_override)))
            except ValueError:
                pass

        gateway_telemetry = {
            "gateway_prompt_chars": len(sys_msg),
            "gateway_payload_chars": len(content),
            "gateway_total_chars": len(sys_msg) + len(content),
            "gateway_timeout_sec": dynamic_timeout,
        }
        
        custom_env = build_gemini_env(os.environ.copy())

        # Resolve binaries dynamically to avoid hard failure on host-specific paths.
        node_bin = resolve_binary(
            env=custom_env,
            env_key="NEXUS_NODE_BIN",
            candidates=DEFAULT_NODE_CANDIDATES,
            binary_name="node",
        )
        gemini_entry = resolve_binary(
            env=custom_env,
            env_key="NEXUS_GEMINI_BIN",
            candidates=DEFAULT_GEMINI_CANDIDATES,
            binary_name="gemini",
        )
        if not gemini_entry:
            return self._build_error_result(
                "Gateway bootstrap failed: cannot locate 'gemini' binary",
                category="binary_missing",
            ), "gemini_missing"

        invocation = build_gemini_cli_invocation(
            prompt=sys_msg,
            payload=content,
            model_name=model_name,
            gemini_entry=gemini_entry,
            node_bin=node_bin,
            env=custom_env,
        )
        tmp_payload = None
        if invocation.prompt_stdin is not None:
            tmp_payload = (self.project_root / f".nexus/payload_{os.getpid()}.txt").resolve()
            tmp_payload.parent.mkdir(parents=True, exist_ok=True)
            tmp_payload.write_text(invocation.prompt_stdin, encoding="utf-8")
        
        for attempt in range(max_retries):
            try:
                f_in = open(tmp_payload, "rb") if tmp_payload is not None else None
                try:
                    res = subprocess.run(
                        invocation.command,
                        stdin=f_in,
                        capture_output=True,
                        text=True,
                        check=False,
                        env=invocation.env,
                        cwd=invocation.cwd,
                        timeout=dynamic_timeout
                    )
                finally:
                    if f_in is not None:
                        f_in.close()
                
                # Retry with explicit node if gemini shim cannot find node runtime.
                stderr_lower = (res.stderr or "").lower()
                if res.returncode != 0 and invocation.command_with_node and "env: node: no such file or directory" in stderr_lower:
                    f_in2 = open(tmp_payload, "rb") if tmp_payload is not None else None
                    try:
                        res = subprocess.run(
                            invocation.command_with_node,
                            stdin=f_in2,
                            capture_output=True,
                            text=True,
                            check=False,
                            env=invocation.env,
                            cwd=invocation.cwd,
                            timeout=dynamic_timeout
                        )
                    finally:
                        if f_in2 is not None:
                            f_in2.close()
                    stderr_lower = (res.stderr or "").lower()

                if "login" in stderr_lower:
                    logger.warning("⚙️ [Gateway] OAuth session expired. Please re-run 'gemini login'.")
                    time.sleep(2)
                    continue

                if res.returncode != 0:
                    last_err = res.stderr or res.stdout
                    time.sleep(1.2 ** attempt)
                    continue
                
                raw_stdout = res.stdout.strip()

                try:
                    try:
                        resp_json = json.loads(raw_stdout)
                    except json.JSONDecodeError:
                        resp_json, _ = json.JSONDecoder().raw_decode(raw_stdout)
                    output_text = resp_json.get("output") or resp_json.get("response") or raw_stdout
                    
                    token_info = extract_token_info(resp_json)
                    tokens_total = int(token_info["total_tokens"])
                                
                    capture_status = "measured" if tokens_total > 0 else "missing_gateway_stats"
                    parsed = self._parse_json_result(output_text, tokens_total, capture_status, token_info, gateway_telemetry)
                    if tmp_payload is not None and tmp_payload.exists():
                        tmp_payload.unlink()
                    return parsed
                except (json.JSONDecodeError, ValueError):
                    last_err = f"Malformed JSON: {raw_stdout[:100]}"
                    continue
            except subprocess.TimeoutExpired:
                logger.error("⏰ [Gateway] Dynamic timeout of %ss expired.", dynamic_timeout)
                last_err = "TIMEOUT"
            except Exception as e:
                last_err = str(e)
                
        if tmp_payload is not None and tmp_payload.exists():
            tmp_payload.unlink()
        category = "timeout" if str(last_err).strip().upper() == "TIMEOUT" else "gateway_error"
        return self._build_error_result(f"Gateway Exhausted: {last_err}", category=category, telemetry=gateway_telemetry), last_err

    def _resolve_binary(
        self,
        *,
        env: Dict[str, str],
        env_key: str,
        candidates: tuple[str, ...],
        binary_name: str,
    ) -> Optional[str]:
        env_override = env.get(env_key)
        if env_override and Path(env_override).exists():
            return env_override
        return resolve_binary(env=env, env_key=env_key, candidates=candidates, binary_name=binary_name)

    def _extract_token_info(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return extract_token_info(payload)

    def _parse_json_result(self, raw_text, tokens_total, capture_status, token_info=None, gateway_telemetry=None):
        """解析模型產出的 JSON 內容。"""
        try:
            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                match = re.search(r"```json\s*(.*?)\s*```", raw_text, re.DOTALL)
                if match:
                    data = json.loads(match.group(1).strip())
                else:
                    start = raw_text.find("{")
                    end = raw_text.rfind("}")
                    if start != -1 and end != -1:
                        data = json.loads(raw_text[start:end+1])
                    else:
                        raise ValueError("No JSON block found")

            data.setdefault("status", "FAIL")
            data.setdefault("summary", "No summary provided")
            data.setdefault("violations", [])
            data["tokens_used"] = tokens_total
            data["token_capture_status"] = capture_status
            if isinstance(token_info, dict):
                data["gateway_stats_present"] = bool(token_info.get("gateway_stats_present", False))
                data["gateway_usage_metadata_present"] = bool(token_info.get("gateway_usage_metadata_present", False))
                data["gateway_token_source"] = str(token_info.get("gateway_token_source") or "missing")
            if isinstance(gateway_telemetry, dict):
                data.update(gateway_telemetry)
            
            return data, raw_text
            
        except Exception as e:
            return self._build_error_result(
                f"Parse Error: {str(e)}",
                category="parse_failure",
                telemetry=gateway_telemetry if isinstance(gateway_telemetry, dict) else None,
            ), raw_text
