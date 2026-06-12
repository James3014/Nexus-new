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


class S2T3BAdvisor:
    """Interface for Qwen base + LoRA adapter inference."""

    def __init__(
        self,
        base_model_path: str = "Qwen/Qwen2.5-3B-Instruct",
        adapter_path: str = "training/adapters/qwen3b_s2t_adapter",
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
                {"id": c.candidate_id, "cost": c.selector_score}
                for c in candidates
            ]
            input_str = f"Route Features: risk_tier={risk_tier}\nCandidates: {candidate_summaries}"
            messages = [
                {
                    "role": "system",
                    "content": "You are a S2T selection advisor. Output JSON with selected_candidate_id and selection_reason_codes."
                },
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
            
            if "```" in response:
                response = response.split("```")[1].split("```")[0].strip()
            
            response_json = json.loads(response)
            if "selected_candidate_id" not in response_json:
                return {"abstain_reason": "invalid_schema"}
            return response_json
        except json.JSONDecodeError:
            return {"abstain_reason": "fail_parse"}
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
        
        # 2. 10% 顧問分流判定 (基於 task_id hash)
        run_advisor = False
        advisor_selected_id = ""
        advisor_verdict = "not_run"
        advisor_status = "not_run"
        
        if self.advisor_enabled and task_id:
            # 取得 task_id hash
            h_val = int(hashlib.md5(task_id.encode('utf-8')).hexdigest(), 16)
            if (h_val % 100) < 10:
                run_advisor = True
                
        if run_advisor:
            # 3. 調用 3B 學生模型顧問進行輔助決策
            res = self.advisor.advise(risk_tier, candidates)
            if "abstain_reason" in res:
                advisor_selected_id = ""
                advisor_verdict = res["abstain_reason"]
                advisor_status = f"abstained: {res['abstain_reason']}"
            else:
                advisor_selected_id = res.get("selected_candidate_id", "")
                if advisor_selected_id:
                    advisor_verdict = "pass"
                    advisor_status = "active_advising"
                else:
                    advisor_selected_id = ""
                    advisor_verdict = "fail_schema"
                    advisor_status = "abstained: missing_selected_candidate_id"
                
        # 4. 記錄 Per-row Evidence
        if run_advisor:
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
            selected_candidate_id=selection.selected_candidate_id,
            failure_reason=gate_result.failure_reason,
            reason_codes=tuple(selection.reason_codes),
            advisor_used=run_advisor,
            advisor_selected_candidate_id=advisor_selected_id,
            advisor_outcome_status=advisor_status,
        )
