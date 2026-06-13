from __future__ import annotations

import hashlib
import json
import datetime
from dataclasses import dataclass
from pathlib import Path

from nexus.contracts.s2t_policy import S2TCandidate, S2TSelector, S2TStrictGate


@dataclass(frozen=True)
class S2TStrictDecision:
    passed: bool
    selected_candidate_id: str
    failure_reason: str = ""
    reason_codes: tuple[str, ...] = ()
    advisor_used: bool = False
    advisor_selected_candidate_id: str = ""
    advisor_outcome_status: str = "not_run"

def robust_json_parse(response: str) -> dict:
    """Robustly parse Qwen model response, translating between JSON/Python dict and handling null/None/true/False."""
    # 1. 嘗試直接 json.loads
    try:
        return json.loads(response)
    except Exception:
        pass

    import re

    # 2. 轉換為 JSON 標準格式 (最優解：單引號轉雙引號，以標準 JSON parser 解析，防止破壞字串內部的關鍵詞)
    try:
        cleaned = response.replace("'", '"')
        cleaned = re.sub(r'\bNone\b', 'null', cleaned)
        cleaned = re.sub(r'\bTrue\b', 'true', cleaned)
        cleaned = re.sub(r'\bFalse\b', 'false', cleaned)
        return json.loads(cleaned)
    except Exception:
        pass

    # 3. 作為 fallback，使用 ast.literal_eval
    try:
        import ast
        py_str = response
        py_str = re.sub(r'\bnull\b', 'None', py_str)
        py_str = re.sub(r'\btrue\b', 'True', py_str)
        py_str = re.sub(r'\bfalse\b', 'False', py_str)
        parsed = ast.literal_eval(py_str)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("Parsed object is not a dictionary")
    except Exception as e:
        raise ValueError(f"Failed to parse response: {e}")


def _verify_adapter_provenance(adapter_path: str) -> None:
    path = Path(adapter_path).resolve()
    adapter_id = path.name
    
    # 尋找專案根目錄下的 registry
    project_root = Path(__file__).resolve().parents[2]
    registry_file = project_root / ".nexus" / "registry" / "s2t_adapters" / f"{adapter_id}.json"
    
    if not registry_file.exists():
        raise ValueError(f"Provenance Lock Fail: Adapter {adapter_id} is not registered in registry {registry_file}")
        
    with open(registry_file, "r", encoding="utf-8") as f:
        registry_data = json.load(f)
        
    for filename, file_meta in registry_data.get("files", {}).items():
        file_path = path / filename
        if not file_path.exists():
            raise FileNotFoundError(f"Provenance Lock Fail: Required registered file {filename} is missing in {path}")
            
        # 計算實體雜湊
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as bf:
            while chunk := bf.read(8192):
                sha256.update(chunk)
        real_hash = sha256.hexdigest()
        
        expected_hash = file_meta.get("sha256")
        if real_hash != expected_hash:
            raise ValueError(
                f"Provenance Lock Fail: Checksum mismatch for {filename}.\n"
                f"Expected: {expected_hash}\n"
                f"Got:      {real_hash}"
            )


class S2T3BAdvisor:
    """Interface for Qwen base + LoRA adapter inference."""

    def __init__(
        self,
        base_model_path: str = "Qwen/Qwen2.5-3B-Instruct",
        adapter_path: str = "training/adapters/qwen3b_s2t_adapter_v2",
        force_simulation: bool = False
    ) -> None:
        self.base_model_path = base_model_path
        self.adapter_path = adapter_path
        self.force_simulation = force_simulation
        self.model = None
        self.tokenizer = None
        self._is_loaded = False
        self._use_simulation = False
        self._load_error = ""

    def _lazy_load(self) -> None:
        if self._is_loaded or self._use_simulation:
            return
        if self.force_simulation:
            self._use_simulation = True
            return
            
        # 1. Kill Switch 檢查
        import os
        if os.environ.get("NEXUS_S2T_3B_ADVISOR_ENABLED") == "0":
            self._load_error = "advisor_disabled"
            return
            
        # 2. Provenance Lock 註冊與完整性檢查
        try:
            _verify_adapter_provenance(self.adapter_path)
        except Exception as prov_err:
            self._load_error = f"provenance_lock_failed: {prov_err}"
            return

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from peft import PeftModel
            
            if not Path(self.adapter_path).exists():
                raise FileNotFoundError(f"Adapter path {self.adapter_path} not found")

            self.tokenizer = AutoTokenizer.from_pretrained(self.base_model_path, trust_remote_code=True)
            self.model = AutoModelForCausalLM.from_pretrained(
                self.base_model_path,
                device_map="auto",
                torch_dtype=torch.float16,
                trust_remote_code=True
            )
            self.model = PeftModel.from_pretrained(self.model, self.adapter_path)
            self.model.eval()
            self._is_loaded = True
        except Exception as exc:
            self._load_error = str(exc)

    def advise(self, risk_tier: str, candidates: list[S2TCandidate]) -> dict:
        self._lazy_load()
        if self._use_simulation:
            if not candidates:
                return {"abstain_reason": "no_candidates"}
            return {
                "selected_candidate_id": candidates[0].candidate_id,
                "selection_reason_codes": ["matches_route_decision"]
            }

        if not self._is_loaded or self.model is None or self.tokenizer is None:
            reason = "model_not_loaded"
            if self._load_error:
                reason = f"model_not_loaded: {self._load_error}"
            return {"abstain_reason": reason}

        try:
            candidate_summaries = [
                {
                    "id": c.candidate_id,
                    "cost": c.selector_score,
                    "verifier_result": c.verifier_result,
                }
                for c in candidates
            ]
            input_str = f"Route Features: risk_tier={risk_tier}\nCandidates: {candidate_summaries}"
            system_prompt = (
                "You are a Nexus Routing Selector Assistant. Your task is to select the best candidate "
                "and provide selection reason codes and required verifiers based on the route features "
                "and candidate summaries.\n"
                "Safety Rule: You MUST NOT select any candidate with verifier_result='fail'. "
                "Prefer candidates with verifier_result='pass'. "
                "If there are no passing candidates or evidence is insufficient, you must abstain by "
                "setting selected_candidate_id to null and providing an abstain_reason.\n"
                "You must strictly output a valid JSON object. Do NOT wrap output in markdown blocks (e.g. ```json). "
                "Do NOT use single quotes for JSON keys or string values (do NOT output Python dict format). "
                "Every output MUST strictly contain all 4 required keys: 'selected_candidate_id', 'selection_reason_codes', "
                "'required_verifier', 'abstain_reason'. The 'required_verifier' field MUST be null or one of the following "
                "allowed verifiers: ['pytest', 'claim_gate', 'delivery_gate', 'hidden_verifier']."
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": input_str}
            ]
            text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            model_inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)
            
            import torch
            with torch.no_grad():
                generated_ids = self.model.generate(**model_inputs, max_new_tokens=128)
            
            generated_ids = [
                output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
            ]
            response = self.tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
            
            # 剔除可能存在的 markdown
            if response.startswith("```json"):
                response = response.split("```json")[1].split("```")[0].strip()
            elif response.startswith("```"):
                response = response.split("```")[1].split("```")[0].strip()
            
            try:
                response_json = robust_json_parse(response)
            except Exception:
                return {"abstain_reason": "fail_parse"}

            if not isinstance(response_json, dict) or "selected_candidate_id" not in response_json:
                return {"abstain_reason": "invalid_schema"}
            return response_json
        except Exception as e:
            return {"abstain_reason": f"generation_or_parse_failed: {e}"}


class S2TStrictRuntimeGate:
    """Fail-closed S2T gate for claim and delivery-sensitive nodes with 3B advisor routing."""

    def __init__(
        self,
        *,
        selector: S2TSelector | None = None,
        gate: S2TStrictGate | None = None,
        advisor_enabled: bool = True,
        advisor: S2T3BAdvisor | None = None,
        evidence_log_path: str | Path = ".nexus/metrics/s2t_runtime_adoption_evidence.jsonl"
    ) -> None:
        self.selector = selector or S2TSelector()
        self.gate = gate or S2TStrictGate()
        self.advisor_enabled = advisor_enabled
        self.advisor = advisor or S2T3BAdvisor()
        self.evidence_log_path = Path(evidence_log_path)

    def evaluate(
        self,
        *,
        task_id: str = "",
        risk_tier: str,
        candidates: list[S2TCandidate],
        verifier_result: str,
        verifier_evidence_ref: str = "",
    ) -> S2TStrictDecision:
        # 1. 執行 baseline rule selection
        selection = self.selector.select(candidates)
        gate_result = self.gate.evaluate(
            risk_tier=risk_tier,
            decision=selection,
            verifier_result=verifier_result,
            verifier_evidence_ref=verifier_evidence_ref,
        )
        
        # 2. 顧問分流與環境策略讀取 (Rollout Control)
        import os

        # 模式列舉與初始狀態
        # [off, observation, dry_run, low_risk, medium_observation]
        assisted_mode = os.environ.get("NEXUS_S2T_3B_ASSISTED_MODE", "0").lower()
        if assisted_mode in ("0", "false"): assisted_mode = "off"
        elif assisted_mode in ("1", "true"): assisted_mode = "low_risk"

        canary_rate = int(os.environ.get("NEXUS_S2T_3B_CANARY_RATE", "10"))
        env_enabled = os.environ.get("NEXUS_S2T_3B_ADVISOR_ENABLED") != "0"
        env_force = os.environ.get("NEXUS_S2T_3B_ADVISOR_FORCE") == "1"

        run_advisor = False
        advisor_selected_id = ""
        advisor_verdict = "not_run"
        advisor_status = "not_run"

        # 決定是否啟動 Advisor 推理
        if env_enabled and (task_id or env_force):
            is_in_rate_bucket = False
            if task_id:
                h_val = int(hashlib.md5(task_id.encode('utf-8')).hexdigest(), 16)
                if (h_val % 100) < canary_rate:
                    is_in_rate_bucket = True

            # 觸發條件：強制、在採樣率內、或特定模式需求
            should_trigger = env_force or is_in_rate_bucket

            if should_trigger:
                if assisted_mode == "off":
                    advisor_status = "advisor_disabled_by_mode"
                else:
                    run_advisor = True

        if run_advisor:
            # 3. 調用 3B 學生模型顧問進行輔助決策
            res = self.advisor.advise(risk_tier, candidates)
            if res.get("abstain_reason") is not None:
                advisor_selected_id = ""
                advisor_verdict = res["abstain_reason"]
                advisor_status = f"abstained: {res['abstain_reason']}"
            else:
                raw_id = res.get("selected_candidate_id", "")
                if raw_id:
                    # 🔍 Phase A3: Post-processing Semantic Safety Gate
                    matched_cand = next((c for c in candidates if str(c.candidate_id) == str(raw_id)), None)

                    # 嚴格校驗：必須存在、必須通過、必須有證據
                    is_safe = (
                        matched_cand is not None 
                        and matched_cand.verifier_result == "pass" 
                        and bool(matched_cand.evidence_refs)
                    )

                    if not is_safe:
                        advisor_selected_id = ""
                        advisor_verdict = "advisor_semantic_rejected"
                        advisor_status = "abstained: advisor_semantic_rejected"
                    else:
                        advisor_selected_id = str(raw_id)
                        advisor_verdict = "pass"
                        advisor_status = "active_advising"
                else:
                    advisor_selected_id = ""
                    advisor_verdict = "fail_schema"
                    advisor_status = "abstained: missing_selected_candidate_id"

        # 4. 決策融合與風險限制 (Assisted Mode Decision)
        final_selected_id = selection.selected_candidate_id
        assisted_decision_applied = False

        # 風控邊界
        allowed_risk = os.environ.get("NEXUS_S2T_3B_ALLOWED_RISK", "low")

        # 決策執行邏輯
        if run_advisor and advisor_selected_id:
            # A. 針對 low_risk 模式且風險符合
            if assisted_mode == "low_risk" and risk_tier == "low":
                final_selected_id = advisor_selected_id
                assisted_decision_applied = True

            # B. 針對 dry_run (不限風險，僅紀錄意向)
            elif assisted_mode == "dry_run":
                assisted_decision_applied = False

            # C. 針對 medium_observation (僅紀錄意向)
            elif assisted_mode == "medium_observation" and risk_tier == "medium":
                assisted_decision_applied = False

            # D. observation 模式 (全風險紀錄，不執行)
            elif assisted_mode == "observation":
                assisted_decision_applied = False

        # 5. 記錄 Per-row Evidence (B0 Monitoring)
        if run_advisor or (task_id and (env_force or (int(hashlib.md5(task_id.encode('utf-8')).hexdigest(), 16) % 100) < canary_rate)):
            trust_mismatch = (verifier_result != "pass")
            evidence_row = {
                "task_id": task_id,
                "risk_tier": risk_tier,
                "baseline_selected_id": selection.selected_candidate_id,
                "advisor_selected_id": advisor_selected_id,
                "advisor_parse_schema_verdict": advisor_verdict,
                "verifier_result": verifier_result,
                "trust_mismatch": trust_mismatch,
                "advisor_status": advisor_status,
                "gate_passed": gate_result.gate_passed,
                "assisted_mode": assisted_mode,
                "canary_rate": canary_rate,
                "assisted_decision_applied": assisted_decision_applied,
                "final_selected_id": final_selected_id,
                "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            try:
                self.evidence_log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.evidence_log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(evidence_row) + "\n")
            except Exception:
                pass
                
        return S2TStrictDecision(
            passed=gate_result.gate_passed,
            selected_candidate_id=final_selected_id,
            failure_reason=gate_result.failure_reason,
            reason_codes=tuple(selection.reason_codes),
            advisor_used=run_advisor,
            advisor_selected_candidate_id=advisor_selected_id,
            advisor_outcome_status=advisor_status,
        )
