from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple
from datetime import datetime, timezone
import subprocess
import json
import logging
import fcntl
import re
import shutil
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
from nexus.engine.patch.apply_engine import PatchApplyEngine

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
        self.patch_engine = PatchApplyEngine(self.project_root)
        
        # 🧪 [v26.1] Feature Flags
        self.use_surgical_repair = os.getenv("NEXUS_USE_SURGICAL_REPAIR", "1") == "1"
        
        # 🛡️ Battlesuit Origin: 僅支援 OAuth CLI 與物理 Handoff
        self.use_oauth = True
        self.oauth_provider = (os.getenv("NEXUS_OAUTH_PROVIDER", "auto").strip().lower() or "auto")
        if self.oauth_provider == "auto":
            if self._ollama_available():
                self.oauth_provider = "ollama"
            else:
                self.oauth_provider = "gemini"
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

    def _ollama_available(self) -> bool:
        """偵測本地 Ollama 是否可用。"""
        endpoint = os.getenv("NEXUS_OLLAMA_ENDPOINT", "http://localhost:11434").rstrip("/")
        try:
            req = urllib.request.Request(f"{endpoint}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        return False

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
        "rejection_contract": {
            "rejection_class": "test_regression_risk | style_contract_violation | semantic_incomplete | api_breakage | semantic_reasoning_ceiling",
            "minimal_counterexample": "Smallest failing code snippet or scenario",
            "repair_constraint": "Specific hard constraint for the next retry",
            "forbidden_repeat_signature": "Identifier for the rejected logic"
        }
    }
    GATEWAY_INVOCATION_AUTHORITY_SCHEMA = "nexus.gateway_invocation_authority.v1"

    PATCH_SCHEMA_INSTRUCTION = (
        "You are a code repair agent. Generate a patch using Aider-style Search/Replace blocks. "
        "Output format: <<<<<<< SEARCH\\n<exact lines to find>\\n=======\\n<replacement lines>\\n>>>>>>> REPLACE\\n\\n"
        "Rules:\n"
        "- Include enough context lines to make the search block unique\n"
        "- Preserve exact whitespace and indentation\n"
        "- Return ONLY the Search/Replace blocks, no explanations, no comments\n"
        "- Do NOT add comments like '# add this line' or '# <<<...>>>' inside the patch\n"
        "- If multiple changes needed, use multiple blocks\n"
    )

    def _build_system_instruction(
        self,
        output_schema: Optional[Dict[str, Any]],
        system_instruction: Optional[str] = None,
    ) -> str:
        base = system_instruction or "You are the pilot of the Nexus Battlesuit v16."
        parts = [
            f"{base}",
            "Do not use tools, do not inspect files, and do not create an execution plan.",
        ]
        if output_schema is not None:
            parts.append("Return ONLY valid JSON. Do not wrap the answer in markdown.")
            parts.append(f"Required output shape: {json.dumps(output_schema, ensure_ascii=False)}")
        return " ".join(parts)

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
        🛡️ Surgical Ask v4.5: 受控微蜂群探索與語義升階
        """
        from nexus.engine.surgical_intel_service import SurgicalIntelligence
        from nexus.engine.direct_mode import extract_target_files
        intel = SurgicalIntelligence(self.project_root)
        
        surgical_context = []
        for sym in symbols:
            context = intel.provide_context(sym)
            if context:
                surgical_context.append(f"### [Surgical Context: {sym}]\n{context}")
        
        if rejection_receipt:
            surgical_context.append(rejection_receipt.format_as_constraint_prompt())
        
        # For R phase, include target file content so model can generate accurate patches
        if phase == "R":
            target_files = extract_target_files(task)
            for tf in target_files[:1]:  # First target file
                file_path = self.project_root / tf
                if file_path.exists():
                    try:
                        file_content = file_path.read_text(encoding="utf-8")
                        # Extract only the first 50 lines (imports section) for patch generation
                        lines = file_content.split('\n')
                        relevant_lines = lines[:50]  # Usually imports are in first 50 lines
                        truncated = '\n'.join(relevant_lines)
                        surgical_context.append(f"### [Target File (first 50 lines): {tf}]\n```\n{truncated}\n```")
                    except Exception:
                        pass
            
        combined_payload = "\n\n".join(surgical_context)

        # 1. 檢測語義推理上限 (Semantic Reasoning Ceiling)
        is_ceiling = rejection_receipt and rejection_receipt.rejection_class == "semantic_reasoning_ceiling"
        forced_model = None
        if is_ceiling and self.oauth_provider == "ollama":
            forced_model = os.getenv("NEXUS_OLLAMA_MODEL", "qwen2.5-coder:14b")
            logger.warning("🚀 [Gateway:Escalate] Semantic ceiling detected. Forcing 14b model for repair.")

        # 🐝 蜂群觸發判定 (Governed Micro-Swarm)
        should_swarm = self.swarm_trigger.should_trigger(
            state_metadata={},
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
                
                return best["data"], best["raw_text"]

        # 回退至單一路徑
        # For R phase, use patch generation instruction instead of rejection schema
        if phase == "R":
            return self.ask_structured(
                task, 
                combined_payload, 
                phase=phase, 
                model_name=forced_model,
                system_instruction=self.PATCH_SCHEMA_INSTRUCTION,
                output_schema=None,  # Let model produce free-form Search/Replace blocks
            )
        return self.ask_structured(task, combined_payload, phase=phase, model_name=forced_model)

    def apply_patch_v2(self, task_id: str, target_file: str, raw_patch: str) -> Dict[str, Any]:
        """
        🛡️ Patch Apply v2: 硬化套用接口
        """
        return self.patch_engine.apply_patch(task_id, target_file, raw_patch)

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
        gateway_invocation_authority: Mapping[str, Any] | None = None,
    ) -> tuple[Any, str]:
        """Night Shift / automation path: request arbitrary structured JSON through the battlesuit."""
        selected_model = model_name or self.model_selector(phase)
        full_content = f"{prompt}\n\n[PAYLOAD]\n{payload}"
        # Only use OUTPUT_SCHEMA if explicitly requested (not None)
        schema = output_schema if output_schema is not None else (self.OUTPUT_SCHEMA if system_instruction is None else None)
        sys_msg = self._build_system_instruction(schema, system_instruction)
        if gateway_invocation_authority is None:
            return self._ask_via_cli(full_content, selected_model, sys_msg)
        return self._ask_via_cli(
            full_content,
            selected_model,
            sys_msg,
            gateway_invocation_authority=gateway_invocation_authority,
        )

    def ask_unified(
        self,
        request: Any,
        *,
        local_service: Any = None,
        capability_invokers: Mapping[str, Any] | None = None,
        verifier: Any = None,
        learning: Any = None,
        receipt_path: Any = None,
        online_invoker: Any = None,
    ) -> dict[str, Any]:
        """Run a task through the canonical task-scoped runtime seam.

        Existing ``ask`` and ``ask_structured`` remain compatibility
        forwarders.  New callers that need Planner/Local/Verifier/Learning
        lineage must use this method; absent stage callbacks remain incomplete
        in the unified receipt rather than being inferred as success.
        """
        from nexus.services.online_execution_policy import (
            decision_from_context,
            resolve_online_execution_decision,
        )
        from nexus.services.unified_runtime import (
            _capability_evidence_summary,
            build_registered_online_invoker,
            normalize_online_invoker_payload,
            resolve_online_transport_binding,
        )

        route = getattr(request, "route", {})
        if not isinstance(route, Mapping):
            route = {}
        route = dict(route)
        requested_provider = str(route.get("provider", "") or "").strip().lower()
        gateway_provider = str(self.oauth_provider or "").strip().lower()
        bound_transport = getattr(self.ask_structured, "__func__", None)
        structured_injected = bound_transport is not self.__class__.ask_structured
        defer_workforce_transport = (
            online_invoker is None
            and not requested_provider
            and isinstance(route.get("workforce_bindings"), Mapping)
            and bool(getattr(request, "online_enabled", True))
        )
        binding = resolve_online_transport_binding(
            has_explicit_invoker=online_invoker is not None,
            structured_transport_injected=structured_injected,
            route_provider=requested_provider,
            gateway_provider=gateway_provider,
        )
        # Mark fixture transports for authorization resolution (not real CLI).
        if structured_injected:
            route["injected_transport"] = True
        # Explicit scenario/online_command injectors are also non-live when flagged.
        if route.get("live_provider_claim") is False or route.get("selection_source") == "injected_transport":
            route["injected_transport"] = True
        # Resolve and bind product Online authorization once for this call.
        prior = decision_from_context(route)
        if prior is None:
            prior = resolve_online_execution_decision(
                task_online_policy=str(route.get("online_policy") or ""),
                project_root=str(
                    route.get("workspace_root")
                    or getattr(self, "project_root", ".")
                    or "."
                ),
                planner_online_needed=True,
                injected_transport=bool(route.get("injected_transport")),
                requested_provider=(
                    requested_provider
                    if defer_workforce_transport
                    else requested_provider or gateway_provider
                ),
            )
        route["online_execution_decision"] = prior.to_dict()
        route["online_policy"] = prior.online_policy
        had_bound_decision = hasattr(self, "_online_execution_decision")
        previous_bound_decision = getattr(self, "_online_execution_decision", None)
        self._online_execution_decision = prior
        try:
            object.__setattr__(request, "route", route)
        except Exception:
            try:
                request.route = route  # type: ignore[misc]
            except Exception:
                pass

        def gateway_online_invoker(context: dict[str, Any]) -> dict[str, Any]:
            task_id = str(context.get("task_id", ""))
            # Bind UR decision onto this Gateway before any physical CLI path.
            from nexus.services.online_execution_policy import (
                decision_from_context,
                physical_online_authorized,
            )

            ctx_decision = decision_from_context(context if isinstance(context, Mapping) else {})
            if ctx_decision is not None:
                self.bind_online_execution_decision(ctx_decision)
            # Provider/transport identity comes from the resolved binding, not
            # from raw oauth_provider auto-detect (which may be local-only).
            provider_identity = binding.provider if binding.provider not in {"", "gateway"} else (
                "injected" if structured_injected else (gateway_provider or "gateway")
            )
            if binding.selection_source == "injected_transport":
                provider_identity = "injected"
            # Injected structured transports skip physical gate; real CLI requires
            # physical_invocation_allowed from the bound decision.
            if bound_transport is self.__class__.ask_structured and not (
                structured_injected
                or self._online_physical_allowed()
                or physical_online_authorized(
                    context if isinstance(context, Mapping) else {},
                    injected_transport=structured_injected,
                )
            ):
                return normalize_online_invoker_payload(
                    provider=provider_identity,
                    task_id=task_id,
                    invoked=False,
                    output_delivered=False,
                    gate_passed=False,
                    provider_call_count=0,
                    response="",
                    raw_response="",
                    usage={},
                    error="online_execution_not_authorized",
                    evidence_refs=[f"gateway:{task_id}:authorization_required"],
                    transport=binding.transport or "gateway_compatibility",
                    selection_source=binding.selection_source or "compatibility_default",
                )
            local_stage = context.get("local", {}) if isinstance(context, dict) else {}
            local_response = local_stage.get("response", {}) if isinstance(local_stage, dict) else {}
            local_outputs = local_response.get("local_outputs", {}) if isinstance(local_response, dict) else {}
            local_context = ""
            capability_context_forwarded = False
            if local_outputs:
                local_context = "\n\n[LOCAL_ASSIST_CONTEXT]\n" + json.dumps(
                    local_outputs,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
            capability_results = context.get("capability_results", {}) if isinstance(context, dict) else {}
            if capability_results:
                compressed = bool(context.get("capability_context_compressed"))
                local_context += (
                    "\n\n[CAPABILITY_EVIDENCE_SUMMARY]\n"
                    if compressed
                    else "\n\n[CAPABILITY_CONTEXT]\n"
                ) + json.dumps(
                    _capability_evidence_summary(capability_results)
                    if compressed
                    else capability_results,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
                capability_context_forwarded = True
            structured_kwargs = {
                "phase": str(context.get("online_phase") or "R"),
                "output_schema": context.get("online_output_schema") or None,
                "model_name": context.get("online_model_name") or None,
            }
            if isinstance(context, Mapping) and "gateway_invocation_authority" in context:
                structured_kwargs["gateway_invocation_authority"] = context.get(
                    "gateway_invocation_authority"
                )
            result, raw_text = self.ask_structured(
                str(context.get("online_prompt") or context.get("task_statement") or "") + local_context,
                str(context.get("online_payload") or ""),
                **structured_kwargs,
            )
            result_mapping = result if isinstance(result, dict) else {}
            route_error = str(raw_text or "").strip().lower() in {"gemini_missing", "error", "failed"}
            delivered = bool(raw_text or result_mapping) and not route_error
            usage: dict[str, Any] = {}
            if result_mapping:
                maybe_usage = result_mapping.get("usage")
                if isinstance(maybe_usage, Mapping):
                    usage = dict(maybe_usage)
                for key in ("tokens_used", "token_capture_status", "gateway_token_source"):
                    if key in result_mapping and key not in usage:
                        usage[key] = result_mapping.get(key)
            error = ""
            if route_error:
                error = "gateway_transport_error"
            elif not delivered:
                error = "gateway_empty_response"
            refs = (
                [f"gateway:{task_id}:provider_call"]
                + ([f"gateway:{task_id}:local_context_forwarded"] if local_outputs else [])
                + ([f"gateway:{task_id}:capability_context_forwarded"] if capability_context_forwarded else [])
                + ([f"gateway:{task_id}:compressed_context_applied"] if context.get("capability_context_compressed") else [])
                if delivered
                else []
            )

            return normalize_online_invoker_payload(
                provider=provider_identity,
                task_id=task_id,
                invoked=bool(delivered),
                output_delivered=bool(delivered),
                gate_passed=bool(delivered),
                provider_call_count=1 if delivered else 0,
                response=result_mapping or raw_text,
                raw_response=str(raw_text or ""),
                usage=usage,
                error=error,
                evidence_refs=refs,
                transport=binding.transport or "gateway_compatibility",
                selection_source=binding.selection_source or "compatibility_default",
            )

        gateway_online_invoker.provider = (
            binding.provider
            if binding.provider not in {"", "gateway"}
            else ("injected" if structured_injected else (gateway_provider or "gateway"))
        )  # type: ignore[attr-defined]
        gateway_online_invoker.online_invoker_provider = gateway_online_invoker.provider  # type: ignore[attr-defined]

        def workforce_admitted_online_invoker(context: Mapping[str, Any]) -> dict[str, Any]:
            authority = context.get("gateway_invocation_authority")
            if not isinstance(authority, Mapping) or authority.get("gate_passed") is not True:
                return normalize_online_invoker_payload(
                    provider="",
                    task_id=str(context.get("task_id", "")),
                    invoked=False,
                    output_delivered=False,
                    gate_passed=False,
                    provider_call_count=0,
                    response="",
                    error="workforce_admission_missing",
                    evidence_refs=[f"gateway:{context.get('task_id')}:workforce_admission_missing"],
                    transport="workforce_deferred",
                    selection_source="workforce_admission",
                )
            admitted_provider = str(authority.get("resolved_provider") or "").strip().lower()
            admitted_model = str(authority.get("resolved_model") or "").strip()
            admitted_binding = resolve_online_transport_binding(
                has_explicit_invoker=False,
                structured_transport_injected=structured_injected,
                route_provider=admitted_provider,
                gateway_provider=gateway_provider,
            )
            if not admitted_binding.use_registered_cli:
                return normalize_online_invoker_payload(
                    provider=admitted_provider,
                    task_id=str(context.get("task_id", "")),
                    invoked=False,
                    output_delivered=False,
                    gate_passed=False,
                    provider_call_count=0,
                    response="",
                    error=admitted_binding.resolution_error or "admitted_transport_not_supported",
                    evidence_refs=[f"gateway:{context.get('task_id')}:admitted_transport_not_supported"],
                    transport=admitted_binding.transport,
                    selection_source="workforce_admission",
                )
            try:
                admitted_invoker = build_registered_online_invoker(
                    admitted_provider,
                    command=route.get("online_command") or route.get("command"),
                    model_name=admitted_model,
                    timeout_sec=float(route.get("timeout_sec", 120.0)),
                )
            except (TypeError, ValueError, OSError) as exc:
                return normalize_online_invoker_payload(
                    provider=admitted_provider,
                    task_id=str(context.get("task_id", "")),
                    invoked=False,
                    output_delivered=False,
                    gate_passed=False,
                    provider_call_count=0,
                    response="",
                    error="provider_adapter_resolution_failed",
                    evidence_refs=[f"gateway:{context.get('task_id')}:provider_adapter_resolution_failed"],
                    transport="registered_cli",
                    selection_source="workforce_admission",
                    extra={"reason": f"{exc.__class__.__name__}:{exc}"},
                )
            return admitted_invoker(context)

        workforce_admitted_online_invoker.workforce_dispatcher = True  # type: ignore[attr-defined]

        runtime_online_invoker = online_invoker
        # P4: World A mainchain — optional with_nexus Online armor (no new topology).
        from nexus.services.mainchain_entry import (
            with_nexus_armor_enabled,
        )

        armor_on = with_nexus_armor_enabled(route)
        if runtime_online_invoker is None:
            if defer_workforce_transport:
                runtime_online_invoker = workforce_admitted_online_invoker
            elif binding.use_registered_cli:
                command = None
                if isinstance(route, Mapping):
                    command = route.get("online_command") or route.get("command")
                try:
                    runtime_online_invoker = build_registered_online_invoker(
                        binding.provider,
                        command=command,
                        model_name=request.online_model_name,
                        timeout_sec=(
                            float(route.get("timeout_sec", 120.0))
                            if isinstance(route, Mapping)
                            else 120.0
                        ),
                    )
                except (TypeError, ValueError, OSError) as exc:
                    resolution_error = f"{exc.__class__.__name__}:{exc}"

                    def unresolved_provider_cli(
                        _context: Mapping[str, Any],
                        *,
                        _reason: str = resolution_error,
                        _provider: str = binding.provider,
                        _selection: str = binding.selection_source,
                    ) -> dict[str, Any]:
                        return normalize_online_invoker_payload(
                            provider=_provider,
                            task_id=str(_context.get("task_id", "")),
                            invoked=False,
                            output_delivered=False,
                            gate_passed=False,
                            provider_call_count=0,
                            response="",
                            raw_response="",
                            usage={},
                            error="provider_adapter_resolution_failed",
                            evidence_refs=[
                                f"gateway:{_context.get('task_id')}:provider_adapter_resolution_failed"
                            ],
                            transport="registered_cli",
                            selection_source=_selection,
                            extra={"reason": _reason},
                        )

                    runtime_online_invoker = unresolved_provider_cli
            elif binding.resolution_error:
                def unresolved_provider(
                    _context: Mapping[str, Any],
                    *,
                    _reason: str = binding.resolution_error,
                    _provider: str = binding.provider,
                    _selection: str = binding.selection_source,
                ) -> dict[str, Any]:
                    return normalize_online_invoker_payload(
                        provider=_provider,
                        task_id=str(_context.get("task_id", "")),
                        invoked=False,
                        output_delivered=False,
                        gate_passed=False,
                        provider_call_count=0,
                        response="",
                        raw_response="",
                        usage={},
                        error="provider_adapter_resolution_failed",
                        evidence_refs=[
                            f"gateway:{_context.get('task_id')}:provider_adapter_resolution_failed"
                        ],
                        transport="unresolved",
                        selection_source=_selection,
                        extra={"reason": _reason},
                    )

                runtime_online_invoker = unresolved_provider
            else:
                # Injected structured transport or gateway compatibility path.
                # Local Ollama discovery must not fail Online when the caller
                # bound ask_structured or when no Online CLI identity was set.
                runtime_online_invoker = gateway_online_invoker

        final_online = runtime_online_invoker or gateway_online_invoker
        # Canonical formal entry: MainchainEntry → CapabilityPlanner → UnifiedRuntime.
        # No direct UnifiedRuntime fallback as an alternate product path.
        try:
            from nexus.services.mainchain_entry import run_mainchain

            return run_mainchain(
                request,
                online_invoker=final_online,
                local_service=local_service,
                capability_invokers=capability_invokers,
                verifier=verifier,
                learning=learning,
                receipt_path=receipt_path,
                with_nexus_armor=bool(armor_on),
            )
        finally:
            if had_bound_decision:
                self._online_execution_decision = previous_bound_decision
            else:
                self.__dict__.pop("_online_execution_decision", None)

    def bind_online_execution_decision(self, decision: Any) -> None:
        """Bind a previously resolved OnlineExecutionDecision for physical CLI paths.

        Repair / UnifiedRuntime must call this before surgical_ask/ask_structured
        so Gateway does not re-resolve policy independently (e.g. workspace deny
        must not override task auto already authorized on the decision).
        """
        self._online_execution_decision = decision

    def _online_physical_allowed(self) -> bool:
        """Enforce Nexus OnlineExecutionDecision for physical Gateway CLI paths.

        Bound decision from UnifiedRuntime/repair wins. Unbound paths fail-closed
        (env emergency override only when no workspace policy file exists).
        Never re-resolve with empty task policy in a way that drops a bound grant.
        """
        from nexus.services.online_execution_policy import (
            OnlineExecutionDecision,
            decision_from_context,
            physical_online_authorized,
            resolve_online_execution_decision,
        )

        bound = getattr(self, "_online_execution_decision", None)
        if bound is not None:
            if isinstance(bound, OnlineExecutionDecision):
                return bool(bound.online_execution_authorized and bound.physical_invocation_allowed)
            if isinstance(bound, Mapping):
                # Prefer explicit physical flag from the attached decision dict.
                if "physical_invocation_allowed" in bound:
                    return bool(bound.get("online_execution_authorized")) and bool(
                        bound.get("physical_invocation_allowed")
                    )
                return physical_online_authorized(bound, injected_transport=False)
        # Unbound product path: fail closed. Do not re-resolve from workspace/env
        # alone — callers must bind via guard_physical_online / bind_online_execution_decision.
        return False

    def _ask_via_registered_print_cli(
        self,
        *,
        content: str,
        sys_msg: str,
        provider: str,
        model_name: str,
        timeout_sec: int,
        gateway_telemetry: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        """Invoke a registered print-mode Online CLI with bound authorization."""
        from nexus.services.unified_runtime import build_registered_online_invoker

        invoker = build_registered_online_invoker(
            provider,
            model_name=model_name,
            timeout_sec=float(timeout_sec),
        )
        prompt = f"{sys_msg}\n\n{content}" if sys_msg else content
        context = {
            "task_id": str(os.getenv("NEXUS_TASK_ID") or "gateway-print"),
            "online_prompt": prompt,
            "online_payload": "",
            "online_model_name": model_name,
            "online_execution_decision": (
                self._online_execution_decision.to_dict()
                if hasattr(self._online_execution_decision, "to_dict")
                else getattr(self, "_online_execution_decision", None)
            ),
            "injected_transport": False,
        }
        # Ensure decision is a dict for decision_from_context
        if context["online_execution_decision"] is not None and not isinstance(
            context["online_execution_decision"], Mapping
        ):
            d = self._online_execution_decision
            if d is not None and hasattr(d, "to_dict"):
                context["online_execution_decision"] = d.to_dict()
            elif isinstance(d, Mapping):
                context["online_execution_decision"] = dict(d)
        payload = invoker(context)
        raw = str(payload.get("raw_response") or payload.get("response") or "")
        if not payload.get("output_delivered"):
            err = {
                "status": "FAILED",
                "error": payload.get("error") or "online_non_delivery",
                "error_category": str(payload.get("error") or "provider_error"),
                "provider": provider,
                "provider_call_count": int(payload.get("provider_call_count") or 0),
                "invoked": bool(payload.get("invoked")),
                "usage": payload.get("usage") or {},
                **gateway_telemetry,
            }
            return err, raw or str(payload.get("error") or "online_non_delivery")
        ok = {
            "status": "APPROVED",
            "provider": provider,
            "provider_call_count": int(payload.get("provider_call_count") or 1),
            "invoked": True,
            "output_delivered": True,
            "usage": payload.get("usage") or {},
            "raw_response": raw,
            **gateway_telemetry,
        }
        return ok, raw

    def _gateway_authority_failure(
        self,
        reason: str,
        *,
        supplied_authority: Any,
        model_name: str,
        admitted_provider: Any = "",
        admitted_model: Any = "",
    ) -> tuple[dict[str, Any], str]:
        if isinstance(supplied_authority, Mapping):
            authority_evidence: Any = dict(supplied_authority)
        else:
            authority_evidence = {
                "supplied_type": type(supplied_authority).__name__,
                "supplied_value": repr(supplied_authority),
            }
        failure_evidence = {
            "reason": reason,
            "actual_provider": str(self.oauth_provider or ""),
            "actual_model": str(model_name or ""),
            "admitted_provider": str(admitted_provider or ""),
            "admitted_model": str(admitted_model or ""),
        }
        result = {
            "status": "FAILED",
            "summary": reason,
            "error": reason,
            "error_category": "gateway_invocation_authority",
            "invoked": False,
            "output_delivered": False,
            "gate_passed": False,
            "provider_call_count": 0,
            "provider": str(self.oauth_provider or ""),
            "model_name": str(model_name or ""),
            "response": "",
            "raw_response": "",
            "usage": {},
            "gateway_invocation_authority": authority_evidence,
            "normalized_failure_evidence": failure_evidence,
        }
        return result, reason

    def _validate_gateway_invocation_authority(
        self,
        authority: Any,
        *,
        model_name: str,
    ) -> tuple[dict[str, Any], str] | None:
        """Validate one per-call T3A1 identity before any physical edge work."""
        if authority is None:
            return None
        if not isinstance(authority, Mapping):
            return self._gateway_authority_failure(
                "gateway_invocation_authority_malformed",
                supplied_authority=authority,
                model_name=model_name,
            )
        if authority.get("schema") != self.GATEWAY_INVOCATION_AUTHORITY_SCHEMA:
            return self._gateway_authority_failure(
                "gateway_invocation_authority_malformed",
                supplied_authority=authority,
                model_name=model_name,
            )
        if authority.get("status") != "ALLOW":
            return self._gateway_authority_failure(
                "gateway_invocation_authority_status_not_allow",
                supplied_authority=authority,
                model_name=model_name,
                admitted_provider=authority.get("resolved_provider"),
                admitted_model=authority.get("resolved_model"),
            )
        if authority.get("gate_passed") is not True:
            return self._gateway_authority_failure(
                "gateway_invocation_authority_gate_not_passed",
                supplied_authority=authority,
                model_name=model_name,
                admitted_provider=authority.get("resolved_provider"),
                admitted_model=authority.get("resolved_model"),
            )
        admitted_provider = authority.get("resolved_provider")
        if not isinstance(admitted_provider, str) or not admitted_provider.strip():
            return self._gateway_authority_failure(
                "gateway_invocation_authority_provider_missing",
                supplied_authority=authority,
                model_name=model_name,
                admitted_provider=admitted_provider,
                admitted_model=authority.get("resolved_model"),
            )
        admitted_model = authority.get("resolved_model")
        if not isinstance(admitted_model, str) or not admitted_model.strip():
            return self._gateway_authority_failure(
                "gateway_invocation_authority_model_missing",
                supplied_authority=authority,
                model_name=model_name,
                admitted_provider=admitted_provider,
                admitted_model=admitted_model,
            )

        actual_provider = str(self.oauth_provider or "")
        if actual_provider != admitted_provider:
            return self._gateway_authority_failure(
                "gateway_invocation_authority_provider_mismatch",
                supplied_authority=authority,
                model_name=model_name,
                admitted_provider=admitted_provider,
                admitted_model=admitted_model,
            )
        if str(model_name or "") != admitted_model:
            return self._gateway_authority_failure(
                "gateway_invocation_authority_model_mismatch",
                supplied_authority=authority,
                model_name=model_name,
                admitted_provider=admitted_provider,
                admitted_model=admitted_model,
            )
        from nexus.services.unified_runtime import (
            REGISTERED_CLI_MODEL_BINDING_UNSUPPORTED_PROVIDERS,
        )

        if actual_provider in REGISTERED_CLI_MODEL_BINDING_UNSUPPORTED_PROVIDERS:
            return self._gateway_authority_failure(
                "gateway_invocation_authority_model_binding_unsupported",
                supplied_authority=authority,
                model_name=model_name,
                admitted_provider=admitted_provider,
                admitted_model=admitted_model,
            )
        if actual_provider not in {"ollama", "gemini", "grok", "agy", "codex", "openai", "opencode"}:
            return self._gateway_authority_failure(
                "gateway_invocation_authority_provider_unsupported",
                supplied_authority=authority,
                model_name=model_name,
                admitted_provider=admitted_provider,
                admitted_model=admitted_model,
            )
        return None

    def _ask_via_cli(
        self,
        content: str,
        model_name: str,
        sys_msg: str,
        complexity_score: float = 0.5,
        gateway_invocation_authority: Mapping[str, Any] | None = None,
    ):
        """🛡️ Battlesuit Forwarding (v24.0 Enhanced - Bayesian Adaptive)"""
        import time

        authority_failure = self._validate_gateway_invocation_authority(
            gateway_invocation_authority,
            model_name=model_name,
        )
        if authority_failure is not None:
            return authority_failure

        if not self._online_physical_allowed():
            # Fail closed for direct physical Online paths (surgical/ask/structured).
            err = {
                "status": "FAILED",
                "error": "online_execution_not_authorized",
                "error_category": "online_execution_not_authorized",
                "provider_call_count": 0,
                "invoked": False,
            }
            return err, "online_execution_not_authorized"

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

        # Multi-provider Online path: grok/agy/codex use registered print-mode CLIs.
        # Do NOT route every Online provider through the Gemini binary (discovery bug).
        provider_key = str(self.oauth_provider or "").strip().lower()
        if provider_key in {"grok", "agy", "codex", "openai", "opencode"}:
            return self._ask_via_registered_print_cli(
                content=content,
                sys_msg=sys_msg,
                provider=provider_key,
                model_name=model_name,
                timeout_sec=dynamic_timeout,
                gateway_telemetry=gateway_telemetry,
            )
        # Prefer Antigravity (agy) when available — Gemini Code Assist individual tier is blocked.
        if (
            gateway_invocation_authority is None
            and provider_key in {"gemini", "auto", ""}
            and shutil.which("agy")
            and os.getenv("NEXUS_PREFER_AGY", "1") == "1"
        ):
            return self._ask_via_registered_print_cli(
                content=content,
                sys_msg=sys_msg,
                provider="agy",
                model_name=model_name,
                timeout_sec=dynamic_timeout,
                gateway_telemetry=gateway_telemetry,
            )

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
            from nexus.engine.local_model_policy import ModelProfile

            options = dict(ModelProfile.get_options(model_name) or {})
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
                val = caster(raw)
                if option_key == "num_ctx" and option_key in options:
                    options[option_key] = max(options[option_key], val)
                else:
                    options[option_key] = val
            except ValueError:
                continue
        # Default num_predict limit to prevent excessive generation
        if "num_predict" not in options:
            options["num_predict"] = 512
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
                "keep_alive": "30m",
            }
        else:
            path = "/api/generate"
            request_payload = {
                "model": model_name,
                "system": sys_msg,
                "prompt": content,
                "stream": False,
                "keep_alive": "30m",
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
        """解析模型產出的 JSON 內容，或直接回傳 Search/Replace 格式。"""
        # Check if output is Search/Replace format (for R phase patch generation)
        if "<<<<<<< SEARCH" in raw_text and ">>>>>>> REPLACE" in raw_text:
            data = {
                "status": "APPROVED",
                "summary": "Patch generated in Search/Replace format",
                "violations": [],
                "patch_raw": raw_text,
            }
            data["tokens_used"] = tokens_total
            data["token_capture_status"] = capture_status
            if isinstance(token_info, dict):
                data.update(token_info)
            if isinstance(gateway_telemetry, dict):
                data.update(gateway_telemetry)
            return data, raw_text
        
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
                # Don't let gateway_telemetry override tokens_used
                telemetry_copy = {k: v for k, v in gateway_telemetry.items() if k != "tokens_used"}
                data.update(telemetry_copy)
            
            return data, raw_text
            
        except Exception as e:
            return self._build_error_result(
                f"Parse Error: {str(e)}",
                category="parse_failure",
                telemetry=gateway_telemetry if isinstance(gateway_telemetry, dict) else None,
            ), raw_text
