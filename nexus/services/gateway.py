from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
import subprocess
import json
import logging
import fcntl
import re
import tempfile
import os
import sys
import signal
import time
import urllib.request

from nexus.services.gemini_cli import (
    build_gemini_env,
    build_gemini_cli_invocation,
    extract_token_info,
    resolve_binary,
    DEFAULT_GEMINI_CANDIDATES,
    DEFAULT_NODE_CANDIDATES,
)

from nexus.engine.micro_swarm_trigger import MicroSwarmTrigger
from nexus.engine.micro_swarm_lane import MicroSwarmLane
from nexus.engine.swarm_compare import SwarmCompare
from nexus.engine.audit_rejection_receipt import AuditRejectionReceipt
from nexus.engine.repair_plan import RepairPlan
from nexus.engine.micro_oracle_runner import MicroOracleRunner

logger = logging.getLogger(__name__)



def _run_cli_with_hard_timeout(
    command: list[str],
    *,
    stdin_path: Path | None,
    env: dict[str, str],
    cwd: Path,
    timeout_sec: int,
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="nexus-gateway-") as tmp:
        stdout_path = Path(tmp) / "stdout.txt"
        stderr_path = Path(tmp) / "stderr.txt"
        with stdout_path.open("w+", encoding="utf-8") as stdout_file, stderr_path.open("w+", encoding="utf-8") as stderr_file:
            f_in = open(stdin_path, "rb") if stdin_path is not None else None
            try:
                proc = subprocess.Popen(
                    command,
                    stdin=f_in,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    text=True,
                    env=env,
                    cwd=cwd,
                    start_new_session=True,
                )
                deadline = time.monotonic() + max(1, int(timeout_sec))
                while True:
                    returncode = proc.poll()
                    if returncode is not None:
                        stdout_file.flush()
                        stderr_file.flush()
                        return subprocess.CompletedProcess(
                            command,
                            returncode,
                            stdout_path.read_text(encoding="utf-8", errors="replace"),
                            stderr_path.read_text(encoding="utf-8", errors="replace"),
                        )
                    if time.monotonic() >= deadline:
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            pass
                        stdout_file.flush()
                        stderr_file.flush()
                        raise subprocess.TimeoutExpired(
                            command,
                            timeout_sec,
                            output=stdout_path.read_text(encoding="utf-8", errors="replace"),
                            stderr=stderr_path.read_text(encoding="utf-8", errors="replace"),
                        )
                    time.sleep(0.1)
            finally:
                if f_in is not None:
                    f_in.close()

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

    def __init__(self, bin_path=None, lock_file=None, project_root=None, **kwargs):
        self.lock_file = lock_file or os.getenv("NEXUS_LOCK_FILE", "/tmp/nexus_battlesuit.lock")
        self.project_root = Path(project_root or ".")
        
        # 🐝 Governed Micro-Swarm (受控微蜂群)
        self.swarm_trigger = MicroSwarmTrigger()
        self.swarm_lane = MicroSwarmLane(self.project_root)
        self.swarm_compare = SwarmCompare()
        
        # 🧪 [v26.1] Feature Flags
        self.use_surgical_repair = os.getenv("NEXUS_USE_SURGICAL_REPAIR", "1") == "1"
        
        # 🛡️ Battlesuit Origin: 僅支援 OAuth CLI 與物理 Handoff
        self.use_oauth = True
        self.oauth_provider = (os.getenv("NEXUS_OAUTH_PROVIDER", "gemini").strip().lower() or "gemini")
        # 🛡️ Compatibility for legacy scripts
        self.llm_bin = self.oauth_provider
        self.enable_shadow_compaction = kwargs.get("enable_shadow_compaction", False)
        
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
            "Do not use tools, do not inspect files, and do not create an execution plan. "
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
            "has_infra_invalid": True,
            "infra_invalid_reason": f"gateway_{category}",
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
        if self.oauth_provider == "ollama":
            phase_upper = str(phase).upper()
            if phase_upper in {"P", "R", "X"}:
                return os.getenv("NEXUS_OLLAMA_SMALL_MODEL", "qwen2.5-coder:7b")
            else:
                return os.getenv("NEXUS_OLLAMA_MODEL", "qwen2.5-coder:14b")
        return "gemini-3-flash-preview" if phase in ["R", "A"] else "gemini-2.5-flash-lite"


    def surgical_ask(
        self, 
        task: str, 
        symbols: List[str], 
        phase: str = "R", 
        rejection_receipt: Optional[AuditRejectionReceipt] = None,
        attempt: int = 1
    ) -> tuple[Any, str]:
        """
        🛡️ Surgical Ask v4.5: 受控微蜂群探索
        """
        from nexus.engine.surgical_intel_service import SurgicalIntelligence
        intel = SurgicalIntelligence(self.project_root)
        
        surgical_context = []
        for sym in symbols:
            context = intel.provide_context(sym)
            if context:
                surgical_context.append(f"### [Surgical Context: {sym}]\n{context}")
        
        if rejection_receipt:
            surgical_context.append(rejection_receipt.format_as_constraint_prompt())
            
        combined_payload = "\n\n".join(surgical_context)

        # 🐝 蜂群觸發判定 (Governed Micro-Swarm)
        should_swarm = self.swarm_trigger.should_trigger(
            state_metadata={}, # TODO: 傳入真實 metadata
            rejection_receipt=rejection_receipt,
            attempt=attempt
        )
        
        if should_swarm:
            logger.info("🐝 [Gateway] Triggering Governed Micro-Swarm for deep exploration.")
            task_id = os.getenv("NEXUS_TASK_ID", "task")
            
            # 執行蜂群搜尋
            branches = self.swarm_lane.execute_governed_swarm(
                task_id=task_id,
                task_desc=task,
                base_prompt=task,
                context_payload=combined_payload,
                gateway_ask_fn=self.ask,
                state_metadata={}
            )
            
            if branches:
                best = self.swarm_compare.select_best(branches)
                
                # 產出微蜂群收據
                from nexus.engine.branch_receipt import MicroSwarmReceipt
                receipt = MicroSwarmReceipt(
                    task_id=task_id,
                    swarm_triggered=True,
                    trigger_reason=rejection_receipt.rejection_class if rejection_receipt else "forced",
                    branch_count=len(branches),
                    selected_candidate=best["branch_id"],
                    branches=branches
                )
                
                # 影子模式日誌 (Shadow Mode Logging)
                receipt_path = self.project_root / ".nexus" / "reports" / f"swarm_receipt_{task_id}.json"
                receipt_path.parent.mkdir(parents=True, exist_ok=True)
                receipt_path.write_text(receipt.to_json(), encoding="utf-8")
                logger.info("📦 [Gateway] Micro-Swarm Receipt saved to: %s", receipt_path)
                
                return best["data"], best["raw_text"]

        # 回退至單一路徑
        return self.ask(task, combined_payload, phase=phase)

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
                dynamic_timeout = max(5, int(timeout_override))
            except ValueError:
                pass
            except Exception:
                pass

        gateway_telemetry = {
            "gateway_prompt_chars": len(sys_msg),
            "gateway_payload_chars": len(content),
            "gateway_total_chars": len(sys_msg) + len(content),
            "gateway_timeout_sec": dynamic_timeout,
            "provider_path": self.oauth_provider,
        }
        
        # 🛡️ Task D.1: Shadow dual prompt rendering (純觀測實驗)
        enable_shadow_compaction = os.getenv("NEXUS_GATEWAY_SHADOW_COMPACTION", "0") == "1" or \
                                   getattr(self, "enable_shadow_compaction", False)
        if enable_shadow_compaction:
            orig_chars = len(sys_msg) + len(content)
            # 模擬壓縮運算
            compact_sys = sys_msg.replace("Do not use tools, do not inspect files, and do not create an execution plan.", "No tools/files/plans.")
            compact_content = re.sub(r"[ \t]+", " ", content)
            compact_content = re.sub(r"\n\n+", "\n", compact_content)
            compacted_chars = len(compact_sys) + len(compact_content)
            
            compaction_ratio = round(1.0 - (compacted_chars / orig_chars), 4) if orig_chars > 0 else 0.0
            schema_preserved = "required_governance_rules" in compact_sys or "required_governance_rules" in compact_content or \
                               "Required output shape" in compact_sys
                               
            gateway_telemetry.update({
                "shadow_compaction_ratio": compaction_ratio,
                "shadow_original_tokens": orig_chars // 4,
                "shadow_compacted_tokens": compacted_chars // 4,
                "shadow_schema_preserved": schema_preserved,
                "public_claim_safe": False, # STRICT CONTRACT: Must be False!
                "task_id": os.getenv("NEXUS_TASK_ID", "task_unknown"),
                "route": "gateway_completion",
                "final_verifier_result": True,
                "prompt_render_id": f"render_{model_name}_{int(time.time() * 1000)}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "run_id": os.getenv("NEXUS_RUN_ID", "run_unknown"),
                "task_kind": "gateway_completion",
                "provider_path": self.oauth_provider,
                "route_strategy": "shadow_compaction_only"
            })

            # Task A3: 寫入獨立的 shadow_telemetry.jsonl
            try:
                log_dir = Path(self.project_root) / ".nexus" / "reports"
                log_dir.mkdir(parents=True, exist_ok=True)
                log_file = log_dir / "shadow_telemetry.jsonl"
                with open(log_file, "a", encoding="utf-8") as h:
                    h.write(json.dumps(gateway_telemetry, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.debug("Failed to write compaction shadow telemetry: %s", e)



        
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

        # 🚀 [Compact Prompt Gateway] 壓縮 System Prompt 與 Context 以降低 Token 消耗與 Wall-time
        if os.getenv("NEXUS_GATEWAY_COMPACT_PROMPT", "0") == "1":
            sys_msg = sys_msg.replace("Do not use tools, do not inspect files, and do not create an execution plan.", "No tools/files/plans.")
            content = re.sub(r"[ \t]+", " ", content)
            content = re.sub(r"\n\n+", "\n", content)

        if self.oauth_provider == "ollama":
            return self._ask_via_ollama(
                content=content,
                model_name=model_name,
                sys_msg=sys_msg,
                timeout_sec=dynamic_timeout,
                gateway_telemetry=gateway_telemetry,
            )

        invocation_build_start = time.monotonic()
        invocation = build_gemini_cli_invocation(
            prompt=sys_msg,
            payload=content,
            model_name=model_name,
            gemini_entry=gemini_entry,
            node_bin=node_bin,
            env=custom_env,
            cwd=str(self.project_root.resolve()),
        )
        invocation_build_sec = round(time.monotonic() - invocation_build_start, 4)
        tmp_payload = None
        if invocation.prompt_stdin is not None:
            tmp_payload = (self.project_root / f".nexus/payload_{os.getpid()}.txt").resolve()
            tmp_payload.parent.mkdir(parents=True, exist_ok=True)
            tmp_payload.write_text(invocation.prompt_stdin, encoding="utf-8")
        gateway_telemetry["gateway_invocation_build_sec"] = invocation_build_sec
        
        for attempt in range(max_retries):
            try:
                process_start = time.monotonic()
                res = _run_cli_with_hard_timeout(
                    invocation.command,
                    stdin_path=tmp_payload,
                    env=invocation.env,
                    cwd=invocation.cwd,
                    timeout_sec=dynamic_timeout,
                )
                gateway_process_sec = round(time.monotonic() - process_start, 4)
                
                # Retry with explicit node if gemini shim cannot find node runtime.
                stderr_lower = (res.stderr or "").lower()
                if res.returncode != 0 and invocation.command_with_node and "env: node: no such file or directory" in stderr_lower:
                    process_start = time.monotonic()
                    res = _run_cli_with_hard_timeout(
                        invocation.command_with_node,
                        stdin_path=tmp_payload,
                        env=invocation.env,
                        cwd=invocation.cwd,
                        timeout_sec=dynamic_timeout,
                    )
                    gateway_process_sec = round(time.monotonic() - process_start, 4)
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
                    parse_start = time.monotonic()
                    try:
                        resp_json = json.loads(raw_stdout)
                    except json.JSONDecodeError:
                        resp_json, _ = json.JSONDecoder().raw_decode(raw_stdout)
                    output_text = resp_json.get("output") or resp_json.get("response") or raw_stdout
                    
                    token_info = extract_token_info(resp_json)
                    tokens_total = int(token_info["total_tokens"])
                    token_chars = int(gateway_telemetry.get("gateway_total_chars", 0) or 0) + len(str(output_text or ""))
                    if (
                        str(token_info.get("gateway_token_source") or "") == "stats"
                        and tokens_total > max(200000, token_chars * 40)
                    ):
                        raw_provider_total_tokens = tokens_total
                        tokens_total = max(1, token_chars // 4)
                        token_info = dict(token_info)
                        token_info["raw_provider_total_tokens"] = raw_provider_total_tokens
                        token_info["raw_provider_token_source"] = "stats"
                        token_info["total_tokens"] = tokens_total
                        token_info["gateway_token_source"] = "estimated_from_stats_outlier"
                        token_info["gateway_token_outlier_reason"] = "stats_outlier_possible_cumulative"
                        token_info["provider_stats_cumulative_suspected"] = True
                        token_info["token_accounting_failure_class"] = "provider_stats_outlier"
                        token_info["token_ledger_status"] = "normalized_from_cumulative_stats"
                        token_info["token_ledger_source"] = "prompt_output_char_estimate"
                        token_info["token_ledger_normalized_tokens"] = tokens_total
                        token_info["token_ledger_raw_provider_total_tokens"] = raw_provider_total_tokens
                    elif tokens_total > 0:
                        token_info = dict(token_info)
                        token_info["token_ledger_status"] = "provider_measured"
                        token_info["token_ledger_source"] = str(token_info.get("gateway_token_source") or "provider")
                        token_info["token_ledger_normalized_tokens"] = tokens_total
                        token_info["token_ledger_raw_provider_total_tokens"] = int(
                            token_info.get("raw_provider_total_tokens", 0) or 0
                        )
                                
                    capture_status = "measured" if tokens_total > 0 else "missing_gateway_stats"
                    if str(token_info.get("gateway_token_source") or "") == "estimated_from_stats_outlier":
                        capture_status = "estimated"
                    parse_sec = round(time.monotonic() - parse_start, 4)
                    gateway_telemetry["gateway_process_sec"] = gateway_process_sec
                    gateway_telemetry["gateway_provider_wait_sec"] = gateway_process_sec
                    gateway_telemetry["gateway_parse_sec"] = parse_sec
                    gateway_telemetry["gateway_total_sec"] = round(
                        invocation_build_sec + gateway_process_sec + parse_sec,
                        4,
                    )
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

    def _ollama_api_type(self, model_name: str) -> str:
        override = os.getenv("NEXUS_OLLAMA_API_TYPE", "").strip().lower()
        if override in {"generate", "chat"}:
            return override
        if str(model_name).startswith("gemma4"):
            return "chat"
        try:
            from nexus.engine.local_model_policy import LocalModelPolicy

            api_type = str(LocalModelPolicy.get_api_type(model_name) or "").strip().lower()
            if api_type in {"generate", "chat"}:
                return api_type
        except Exception:
            pass
        return "generate"

    def _ollama_options(self, model_name: str) -> Dict[str, Any]:
        try:
            from nexus.engine.local_model_policy import LocalModelPolicy

            options = dict(LocalModelPolicy.get_options(model_name) or {})
        except Exception:
            options = {}
        for env_key, option_key, caster in (
            ("NEXUS_OLLAMA_NUM_CTX", "num_ctx", int),
            ("NEXUS_OLLAMA_NUM_PREDICT", "num_predict", int),
            ("NEXUS_OLLAMA_TEMPERATURE", "temperature", float),
        ):
            raw = os.getenv(env_key)
            if raw is None or str(raw).strip() == "":
                continue
            try:
                options[option_key] = caster(raw)
            except ValueError:
                continue
        return options

    def _ask_via_ollama(
        self,
        *,
        content: str,
        model_name: str,
        sys_msg: str,
        timeout_sec: int,
        gateway_telemetry: Dict[str, Any],
    ) -> tuple[Any, str]:
        endpoint = os.getenv("NEXUS_OLLAMA_ENDPOINT", "http://localhost:11434").rstrip("/")
        api_type = self._ollama_api_type(model_name)
        options = self._ollama_options(model_name)
        invocation_build_start = time.monotonic()
        if api_type == "chat":
            path = "/api/chat"
            request_payload: Dict[str, Any] = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": content},
                ],
                "stream": False,
            }
        else:
            path = "/api/generate"
            request_payload = {
                "model": model_name,
                "system": sys_msg,
                "prompt": content,
                "stream": False,
            }
        if options:
            request_payload["options"] = options
        invocation_build_sec = round(time.monotonic() - invocation_build_start, 4)
        gateway_telemetry.update(
            {
                "gateway_invocation_build_sec": invocation_build_sec,
                "ollama_endpoint": endpoint,
                "ollama_api_type": api_type,
                "model_name": model_name,
                "provider": "ollama",
            }
        )

        req = urllib.request.Request(
            f"{endpoint}{path}",
            data=json.dumps(request_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        process_start = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=max(1, int(timeout_sec))) as resp:
                raw_body = resp.read().decode("utf-8", errors="replace")
            process_sec = round(time.monotonic() - process_start, 4)
            parse_start = time.monotonic()
            payload = json.loads(raw_body)
            if api_type == "chat":
                output_text = str(((payload.get("message") or {}) if isinstance(payload, dict) else {}).get("content") or "")
            else:
                output_text = str(payload.get("response") or "")
            prompt_tokens = int(payload.get("prompt_eval_count", 0) or 0)
            completion_tokens = int(payload.get("eval_count", 0) or 0)
            total_tokens = prompt_tokens + completion_tokens
            token_source = "ollama_eval_counts"
            capture_status = "measured"
            if total_tokens <= 0:
                total_tokens = max(1, (len(sys_msg) + len(content) + len(output_text)) // 4)
                token_source = "estimated_from_chars"
                capture_status = "estimated"
            token_info = {
                "total_tokens": total_tokens,
                "raw_provider_total_tokens": total_tokens,
                "raw_provider_token_source": token_source,
                "gateway_stats_present": token_source == "ollama_eval_counts",
                "gateway_usage_metadata_present": token_source == "ollama_eval_counts",
                "gateway_token_source": token_source,
                "provider_stats_cumulative_suspected": False,
                "token_ledger_status": "provider_measured" if capture_status == "measured" else "estimated",
                "token_ledger_source": token_source,
                "token_ledger_normalized_tokens": total_tokens,
                "token_ledger_raw_provider_total_tokens": total_tokens,
            }
            parse_sec = round(time.monotonic() - parse_start, 4)
            gateway_telemetry.update(
                {
                    "gateway_process_sec": process_sec,
                    "gateway_provider_wait_sec": process_sec,
                    "gateway_parse_sec": parse_sec,
                    "gateway_total_sec": round(invocation_build_sec + process_sec + parse_sec, 4),
                }
            )
            parsed_data, parsed_raw = self._parse_json_result(
                output_text,
                total_tokens,
                capture_status,
                token_info,
                gateway_telemetry,
            )
            if isinstance(parsed_data, dict):
                parsed_data["model_name"] = model_name
                parsed_data["provider"] = "ollama"
            return parsed_data, parsed_raw
        except Exception as exc:  # noqa: BLE001
            gateway_telemetry.update(
                {
                    "gateway_process_sec": round(time.monotonic() - process_start, 4),
                    "gateway_provider_wait_sec": round(time.monotonic() - process_start, 4),
                    "gateway_total_sec": round(invocation_build_sec + max(0.0, time.monotonic() - process_start), 4),
                }
            )
            result = self._build_error_result(
                f"Ollama gateway exhausted: {type(exc).__name__}: {exc}",
                category="ollama_gateway_error",
                telemetry=gateway_telemetry,
            )
            result["model_name"] = model_name
            result["provider"] = "ollama"
            return result, str(exc)

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
            if tokens_total <= 0:
                data["has_infra_invalid"] = True
                data["infra_invalid_reason"] = "token_cleanliness_missing_tokens"
            if isinstance(token_info, dict):
                data["gateway_stats_present"] = bool(token_info.get("gateway_stats_present", False))
                data["gateway_usage_metadata_present"] = bool(token_info.get("gateway_usage_metadata_present", False))
                data["gateway_token_source"] = str(token_info.get("gateway_token_source") or "missing")
                data["gateway_token_outlier_reason"] = str(token_info.get("gateway_token_outlier_reason") or "")
                data["raw_provider_total_tokens"] = int(token_info.get("raw_provider_total_tokens", 0) or 0)
                data["raw_provider_token_source"] = str(token_info.get("raw_provider_token_source") or "")
                data["provider_stats_cumulative_suspected"] = bool(
                    token_info.get("provider_stats_cumulative_suspected", False)
                )
                data["token_accounting_failure_class"] = str(token_info.get("token_accounting_failure_class") or "")
                data["token_ledger_status"] = str(token_info.get("token_ledger_status") or "")
                data["token_ledger_source"] = str(token_info.get("token_ledger_source") or "")
                data["token_ledger_normalized_tokens"] = int(token_info.get("token_ledger_normalized_tokens", 0) or 0)
                data["token_ledger_raw_provider_total_tokens"] = int(
                    token_info.get("token_ledger_raw_provider_total_tokens", 0) or 0
                )
            if isinstance(gateway_telemetry, dict):
                data.update(gateway_telemetry)
            
            return data, raw_text
            
        except Exception as e:
            return self._build_error_result(
                f"Parse Error: {str(e)}",
                category="parse_failure",
                telemetry=gateway_telemetry if isinstance(gateway_telemetry, dict) else None,
            ), raw_text
