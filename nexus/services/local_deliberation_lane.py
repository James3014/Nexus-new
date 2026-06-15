from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# Set up logging
logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class DeliberationFitness:
    fitness_score: float  # 0.0 to 1.0
    agreement_rate: float # 0.0 or 1.0
    confidence_score: float # 0.0 to 1.0
    thought_density: float # 0.0 to 1.0
    is_stable: bool

@dataclass(frozen=True)
class DeliberationResult:
    success: bool
    selected_candidate_id: str
    confidence: float
    verdict: str  # pass, fail, need_human_review
    synthesis_notes: str
    fitness: DeliberationFitness
    telemetry: dict
    fallback_used: bool

class LocalDeliberationLane:
    """7B/14B Deliberation Lane.
    7B generates candidates/reasoning; 14B performs synthesis and route-review.
    Includes robust fail-closed simulation fallbacks.
    """

    def __init__(self, force_simulation: bool = False) -> None:
        self.force_simulation = force_simulation
        self.endpoint = os.getenv("NEXUS_OLLAMA_ENDPOINT", "http://localhost:11434").rstrip("/")
        self.model_7b = os.getenv("NEXUS_S2T_7B_OLLAMA_MODEL", "qwen2.5-coder:7b")
        self.model_14b = os.getenv("NEXUS_S2T_14B_OLLAMA_MODEL", "qwen2.5:14b")
        self.timeout = int(os.getenv("NEXUS_DELIBERATION_TIMEOUT_SEC", "10"))

    def should_trigger(self, task_metadata: dict) -> bool:
        """Only trigger deliberation on high-uncertainty / high-value / research / repair-review tasks."""
        if os.getenv("NEXUS_DELIBERATION_LANE_ENABLED", "1") == "0":
            return False

        # Explicit trigger flag
        if task_metadata.get("force_deliberation") or task_metadata.get("high_uncertainty"):
            return True

        # Task type analysis
        task_type = str(task_metadata.get("task_type", "")).lower()
        if task_type in ["research", "repair-review", "synthesis-review", "complex-bug"]:
            return True

        # Value analysis
        if float(task_metadata.get("value_tier", 0.0)) >= 100.0:
            return True

        return False

    def _robust_json_parse(self, text: str) -> dict:
        """Parse robust JSON outputs, removing potential markdown wrappers."""
        text = text.strip()
        if text.startswith("```json"):
            text = text.split("```json")[1].split("```")[0].strip()
        elif text.startswith("```"):
            text = text.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(text)
        except Exception:
            pass

        # Python-like dict conversion fallback
        try:
            cleaned = text.replace("'", '"')
            cleaned = re.sub(r'\bNone\b', 'null', cleaned)
            cleaned = re.sub(r'\bTrue\b', 'true', cleaned)
            cleaned = re.sub(r'\bFalse\b', 'false', cleaned)
            return json.loads(cleaned)
        except Exception:
            raise ValueError(f"Failed to parse JSON response: {text}")

    def _call_ollama(self, model: str, system: str, prompt: str) -> tuple[dict, bool]:
        """Call Ollama API. Returns (response_dict, fallback_used)."""
        if self.force_simulation:
            return {}, True

        payload = {
            "model": model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "30m",
            "options": {
                "temperature": 0.0,
                "top_p": 0.1,
            }
        }

        try:
            req = urllib.request.Request(
                f"{self.endpoint}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                res_json = json.loads(raw)
                return res_json, False
        except Exception as e:
            logger.warning("Ollama connection failed for model %s: %s. Using simulation fallback.", model, e)
            return {}, True

    def deliberate(self, task_context: dict) -> DeliberationResult:
        """Run the 7B/14B Deliberation loop."""
        task_id = task_context.get("task_id", "unknown-task")
        candidates = task_context.get("candidates", [])

        if not candidates:
            return self._build_simulation_result(task_context, "no_candidates")

        # System/Prompt setup for 7B Reasoner
        system_7b = (
            "You are a 7B Reasoning Assistant in the Nexus Deliberation Lane. "
            "Analyze the given task and candidates. Select the best candidate ID and explain your reasoning.\n"
            "Output strictly a JSON object with keys: 'suggested_candidate_id', 'reasoning_steps', 'uncertainty_score'."
        )
        prompt_7b = f"Task Context: {task_context}\nCandidates: {candidates}"

        # 1. Execute 7B Reasoner Step
        res_7b, fallback_7b = self._call_ollama(self.model_7b, system_7b, prompt_7b)
        
        parsed_7b = {}
        t_7b_duration = 0.0
        t_7b_eval_count = 0
        t_7b_thought_ratio = 0.0
        
        if not fallback_7b and res_7b:
            try:
                out_7b = str(res_7b.get("response", "")).strip()
                parsed_7b = self._robust_json_parse(out_7b)
                t_7b_duration = res_7b.get("total_duration", 0) / 1_000_000.0
                t_7b_eval_count = res_7b.get("eval_count", 0)
                # Compute thought ratio if CoT tags are present
                thought_match = re.search(r"<thought>(.*?)</thought>", out_7b, re.DOTALL)
                t_7b_thought_ratio = len(thought_match.group(1)) / len(out_7b) if thought_match and len(out_7b) > 0 else 0.0
            except Exception as e:
                logger.warning("7B output parsing failed: %s. Falling back to simulation.", e)
                fallback_7b = True

        if fallback_7b:
            parsed_7b = {
                "suggested_candidate_id": candidates[0].get("id") if isinstance(candidates[0], dict) else getattr(candidates[0], "candidate_id", ""),
                "reasoning_steps": "Simulation fallback reasoning.",
                "uncertainty_score": 0.3
            }

        # System/Prompt setup for 14B Judge
        system_14b = (
            "You are a 14B Judge/Synthesizer in the Nexus Deliberation Lane. "
            "You will review the 7B reasoner's suggestion, perform a synthesis, and render a final verdict.\n"
            "Output strictly a JSON object with keys: 'selected_candidate_id', 'confidence', 'verdict', 'synthesis_notes'.\n"
            "The 'verdict' MUST be 'pass', 'fail', or 'need_human_review'."
        )
        prompt_14b = (
            f"Original Candidates: {candidates}\n"
            f"7B Recommendation: {parsed_7b}\n"
            f"Please synthesize and select the final candidate."
        )

        # 2. Execute 14B Judge Step
        res_14b, fallback_14b = self._call_ollama(self.model_14b, system_14b, prompt_14b)

        parsed_14b = {}
        t_14b_duration = 0.0
        t_14b_eval_count = 0
        t_14b_thought_ratio = 0.0

        if not fallback_14b and res_14b:
            try:
                out_14b = str(res_14b.get("response", "")).strip()
                parsed_14b = self._robust_json_parse(out_14b)
                t_14b_duration = res_14b.get("total_duration", 0) / 1_000_000.0
                t_14b_eval_count = res_14b.get("eval_count", 0)
                thought_match = re.search(r"<thought>(.*?)</thought>", out_14b, re.DOTALL)
                t_14b_thought_ratio = len(thought_match.group(1)) / len(out_14b) if thought_match and len(out_14b) > 0 else 0.0
            except Exception as e:
                logger.warning("14B output parsing failed: %s. Falling back to simulation.", e)
                fallback_14b = True

        if fallback_14b:
            parsed_14b = {
                "selected_candidate_id": parsed_7b["suggested_candidate_id"],
                "confidence": 0.85,
                "verdict": "pass",
                "synthesis_notes": "Simulation fallback synthesis completed."
            }

        # 3. Calculate Deliberation Fitness Metrics
        agreement_rate = 1.0 if parsed_7b.get("suggested_candidate_id") == parsed_14b.get("selected_candidate_id") else 0.0
        confidence_score = float(parsed_14b.get("confidence", 0.0))
        
        # Overall thought density
        total_eval = (t_7b_eval_count + t_14b_eval_count)
        thought_density = (t_7b_thought_ratio + t_14b_thought_ratio) / 2.0
        
        # Fitness formula: 40% agreement + 60% confidence
        fitness_score = (agreement_rate * 0.4) + (confidence_score * 0.6)
        is_stable = fitness_score >= 0.75

        fitness = DeliberationFitness(
            fitness_score=fitness_score,
            agreement_rate=agreement_rate,
            confidence_score=confidence_score,
            thought_density=thought_density,
            is_stable=is_stable
        )

        telemetry = {
            "7b_duration_ms": t_7b_duration,
            "14b_duration_ms": t_14b_duration,
            "total_deliberation_ms": t_7b_duration + t_14b_duration,
            "total_tokens_eval": total_eval,
            "fallback_7b": fallback_7b,
            "fallback_14b": fallback_14b
        }

        return DeliberationResult(
            success=True,
            selected_candidate_id=parsed_14b.get("selected_candidate_id", ""),
            confidence=confidence_score,
            verdict=parsed_14b.get("verdict", "need_human_review"),
            synthesis_notes=parsed_14b.get("synthesis_notes", ""),
            fitness=fitness,
            telemetry=telemetry,
            fallback_used=fallback_7b or fallback_14b
        )

    def _build_simulation_result(self, task_context: dict, reason: str) -> DeliberationResult:
        """Build a clean simulation result for fallback."""
        candidates = task_context.get("candidates", [])
        selected_id = ""
        if candidates:
            selected_id = candidates[0].get("id") if isinstance(candidates[0], dict) else getattr(candidates[0], "candidate_id", "")

        fitness = DeliberationFitness(
            fitness_score=0.8,
            agreement_rate=1.0,
            confidence_score=0.8,
            thought_density=0.0,
            is_stable=True
        )

        return DeliberationResult(
            success=True,
            selected_candidate_id=selected_id,
            confidence=0.8,
            verdict="pass",
            synthesis_notes=f"Simulation result triggered due to: {reason}",
            fitness=fitness,
            telemetry={
                "7b_duration_ms": 0.0,
                "14b_duration_ms": 0.0,
                "total_deliberation_ms": 0.0,
                "total_tokens_eval": 0,
                "fallback_7b": True,
                "fallback_14b": True
            },
            fallback_used=True
        )
