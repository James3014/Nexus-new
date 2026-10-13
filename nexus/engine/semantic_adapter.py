import ast
import json
import re
from typing import Any, Tuple

from nexus.engine.capability_contracts import FlowState
from nexus.engine.governance_bridge import GovernanceBridge


class ModelOutputParseError(ValueError):
    """Raw model output could not be parsed into a JSON object (fail-closed)."""


class ModelOutputNotObjectError(ModelOutputParseError):
    """Raw model output parsed, but to something other than a JSON object."""


def parse_model_json_object(raw_output: str) -> dict[str, Any]:
    """Sanctioned parser for model output that is expected to be one JSON object.

    Every ``json.loads`` on raw model text belongs here, not at the call site
    (tests/integration/test_legacy_path_blocked.py enforces this). Accepts
    strict JSON, then the Python-dict dialect small local models emit
    (single quotes, None/True/False), then ``ast.literal_eval``. Anything that
    is not a dict raises: callers must treat a raise as "no decision".
    """
    if not isinstance(raw_output, str):
        raise ModelOutputParseError(f"model output must be str, got {type(raw_output).__name__}")

    parsed: Any = None
    parsed_ok = False
    # 1. Strict JSON.
    try:
        parsed = json.loads(raw_output)
        parsed_ok = True
    except Exception:
        pass

    # 2. Python-dict dialect mapped onto strict JSON.
    if not parsed_ok:
        try:
            cleaned = raw_output.replace("'", '"')
            cleaned = re.sub(r"\bNone\b", "null", cleaned)
            cleaned = re.sub(r"\bTrue\b", "true", cleaned)
            cleaned = re.sub(r"\bFalse\b", "false", cleaned)
            parsed = json.loads(cleaned)
            parsed_ok = True
        except Exception:
            pass

    # 3. Python literal fallback.
    if not parsed_ok:
        try:
            py_str = re.sub(r"\bnull\b", "None", raw_output)
            py_str = re.sub(r"\btrue\b", "True", py_str)
            py_str = re.sub(r"\bfalse\b", "False", py_str)
            parsed = ast.literal_eval(py_str)
        except Exception as exc:
            raise ModelOutputParseError(f"Failed to parse response: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ModelOutputNotObjectError(
            f"model output is a {type(parsed).__name__}, not a JSON object"
        )
    return parsed


class SemanticAdapter:
    """
    [NEXUS v26] Semantic Adapter (Hybrid Governance 2.0)
    負責接收模型的字串輸出，呼叫 Rust Normalizer，若不合規一律回退至 ESCALATE。
    """

    def __init__(self):
        self.bridge = GovernanceBridge()

    parse_json_object = staticmethod(parse_model_json_object)

    _ROUTE_CODES = {
        "0": "LOCAL",
        "1": "LARGE",
        "2": "HYBRID",
        "3": "REMOTE",
    }
    _DECISION_CODES = {
        "0": "ALLOW",
        "1": "REVIEW",
        "2": "STOP",
        "3": "STOP",
    }
    _PHASE_CODES = {
        "0": FlowState.INTAKE,
        "1": FlowState.PLAN,
        "2": FlowState.VERIFY,
        "3": FlowState.EXECUTE,
        "4": FlowState.CLOSE,
    }
    _CONFIDENCE_CODES = {"0": "HIGH", "1": "MEDIUM", "2": "LOW"}

    @classmethod
    def _decode_label(cls, value: str, mapping: dict[str, str], default: str) -> str:
        normalized = str(value or "").strip()
        return mapping.get(normalized, normalized.upper() or default)

    def process_model_output(self, raw_output: str) -> Tuple[str, str, FlowState, str]:
        """
        將模型輸出轉為 (Route, Decision, FlowState, Confidence)。
        如果模型吐出自然語言或格式錯誤，Rust 將回傳 None，這裡直接捕捉並 Escalation。
        """
        normalized = self.bridge.normalize_intent(raw_output)

        if normalized is None:
            # 觸發 Fail-Closed 安全網：模型格式錯誤，不允許推進
            return ("LARGE", "STOP", FlowState.ESCALATE, "LOW")

        route_raw, decision_raw, phase_raw, confidence_raw = normalized
        route_str = self._decode_label(route_raw, self._ROUTE_CODES, "LARGE")
        decision_str = self._decode_label(decision_raw, self._DECISION_CODES, "STOP")
        confidence_str = self._decode_label(confidence_raw, self._CONFIDENCE_CODES, "LOW")

        # 簡單映射回 Python 的 FlowState Enum
        try:
            phase_key = str(phase_raw).strip()
            phase = self._PHASE_CODES.get(phase_key)
            if phase is None:
                phase = FlowState(phase_key.upper())
        except ValueError:
            phase = FlowState.UNKNOWN

        # 🛡️ [NEXUS v2.4] EscalationPolicy
        # 若狀態為 UNKNOWN 或決策為 STOP/REJECT，一律強制降級為 ESCALATE
        if phase == FlowState.UNKNOWN or decision_str in ["STOP", "REJECT"]:
            return ("LARGE", "STOP", FlowState.ESCALATE, "LOW")

        return (route_str, decision_str, phase, confidence_str)


if __name__ == "__main__":
    adapter = SemanticAdapter()

    # 測試合法輸入
    print("Valid:", adapter.process_model_output("r:0,d:0,p:1,c:0"))

    # 測試非法輸入 (回聲效應/自然語言)
    print("Invalid:", adapter.process_model_output("I think we should proceed to Phase R"))
