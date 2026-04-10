from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import subprocess
import json
import logging
import fcntl
import shutil
import re
import tempfile
import os
import sys

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

    def _build_error_result(self, summary, category="gateway_error"):
        return {
            "status": "FAIL",
            "summary": summary,
            "violations": [],
            "tokens_used": 0,
            "error_category": category,
        }

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
        max_retries = 3
        last_err = ""
        
        # 🧪 [Bayesian Timeout Adaptive]
        dynamic_timeout = int(60 + (complexity_score * 120))

        tmp_payload = self.project_root / f".nexus/payload_{os.getpid()}.txt"
        tmp_payload.parent.mkdir(parents=True, exist_ok=True)
        tmp_payload.write_text(content, encoding="utf-8")
        
        custom_env = os.environ.copy()
        custom_env["HOME"] = "/Users/jameschen"
        custom_env["PATH"] = f"/opt/homebrew/bin:/Users/jameschen/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:{custom_env.get('PATH', '')}"

        # Resolve binaries dynamically to avoid hard failure on host-specific paths.
        node_bin = self._resolve_binary(
            env=custom_env,
            env_key="NEXUS_NODE_BIN",
            candidates=(
                "/opt/homebrew/bin/node",
                "/usr/local/bin/node",
                "/usr/bin/node",
            ),
            binary_name="node",
        )
        gemini_entry = self._resolve_binary(
            env=custom_env,
            env_key="NEXUS_GEMINI_BIN",
            candidates=(
                "/Users/jameschen/.npm-global/bin/gemini",
                "/opt/homebrew/bin/gemini",
                "/usr/local/bin/gemini",
            ),
            binary_name="gemini",
        )
        if not gemini_entry:
            if tmp_payload.exists():
                tmp_payload.unlink()
            return self._build_error_result(
                "Gateway bootstrap failed: cannot locate 'gemini' binary",
                category="binary_missing",
            ), "gemini_missing"
        
        for attempt in range(max_retries):
            try:
                with open(tmp_payload, "rb") as f_in:
                    # Prefer direct CLI execution; fallback to explicit node runtime when needed.
                    cmd = [gemini_entry, "-m", model_name, "-p", sys_msg, "--output-format", "json"]
                    if node_bin:
                        cmd_with_node = [node_bin, gemini_entry, "-m", model_name, "-p", sys_msg, "--output-format", "json"]
                    else:
                        cmd_with_node = None
                    
                    res = subprocess.run(
                        cmd,
                        stdin=f_in,
                        capture_output=True,
                        text=True,
                        check=False,
                        env=custom_env,
                        cwd="/tmp",
                        timeout=dynamic_timeout
                    )
                
                # Retry with explicit node if gemini shim cannot find node runtime.
                stderr_lower = (res.stderr or "").lower()
                if res.returncode != 0 and cmd_with_node and "env: node: no such file or directory" in stderr_lower:
                    with open(tmp_payload, "rb") as f_in2:
                        res = subprocess.run(
                            cmd_with_node,
                            stdin=f_in2,
                            capture_output=True,
                            text=True,
                            check=False,
                            env=custom_env,
                            cwd="/tmp",
                            timeout=dynamic_timeout
                        )
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
                if tmp_payload.exists(): tmp_payload.unlink()

                try:
                    resp_json = json.loads(raw_stdout)
                    output_text = resp_json.get("output") or resp_json.get("response") or raw_stdout
                    
                    tokens_total = 0
                    stats = resp_json.get("stats", {}).get("models", {})
                    if isinstance(stats, dict):
                        for m_stats in stats.values():
                            if isinstance(m_stats, dict):
                                tokens_total += m_stats.get("tokens", {}).get("total", 0)
                                
                    return self._parse_json_result(output_text, tokens_total, "ok")
                except json.JSONDecodeError:
                    last_err = f"Malformed JSON: {raw_stdout[:100]}"
                    continue
            except subprocess.TimeoutExpired:
                logger.error("⏰ [Gateway] Dynamic timeout of %ss expired.", dynamic_timeout)
                last_err = "TIMEOUT"
            except Exception as e:
                last_err = str(e)
                
        if tmp_payload.exists(): tmp_payload.unlink()
        return self._build_error_result(f"Gateway Exhausted: {last_err}"), last_err

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
        found = shutil.which(binary_name, path=env.get("PATH", ""))
        if found:
            return found
        for candidate in candidates:
            if Path(candidate).exists():
                return candidate
        return None

    def _parse_json_result(self, raw_text, tokens_total, capture_status):
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
            
            return data, raw_text
            
        except Exception as e:
            return self._build_error_result(f"Parse Error: {str(e)}", category="parse_failure"), raw_text
