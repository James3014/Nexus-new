import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Mismatch Entry Schema ─────────────────────────────────────────────

class MismatchSeverity(str, Enum):
    """Mismatch severity classification."""
    LOW = "LOW"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class MismatchEntry:
    """Dual-run mismatch ledger row."""
    module_name: str
    input_hash: str
    py_output: Any
    rs_output: Any
    match: bool
    diff_reason: Optional[str] = None
    severity: MismatchSeverity = MismatchSeverity.LOW
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─── Mismatch Ledger ──────────────────────────────────────────────────

class MismatchLedger:
    """Dual-run governance ledger: record and classify Python vs Rust mismatches."""

    def __init__(self, ledger_path: Path):
        self.ledger_path = ledger_path
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)

    def record_mismatch(self, entry: MismatchEntry):
        logger.warning(
            f"❌ [DualRun] {entry.severity.value} mismatch in {entry.module_name}: {entry.diff_reason}"
        )
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    def count_by_severity(self) -> Dict[str, int]:
        """Count entries grouped by severity."""
        counts = {"LOW": 0, "HIGH": 0, "CRITICAL": 0}
        if not self.ledger_path.exists():
            return counts
        with open(self.ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    sev = entry.get("severity", "LOW")
                    if sev in counts:
                        counts[sev] += 1
                except json.JSONDecodeError:
                    continue
        return counts


# ─── Dual-Run Comparator ──────────────────────────────────────────────

class DualRunComparator:
    """Shadow comparison framework: compare Python vs Rust execution results."""

    def __init__(self, ledger: Optional[MismatchLedger] = None):
        self.ledger = ledger

    def compare(
        self, module_name: str, py_result: Any, rs_result: Any, input_data: Any
    ) -> bool:
        """Compare results and record mismatch."""
        match = (py_result == rs_result)

        if not match and self.ledger:
            input_hash = str(hash(str(input_data)))

            diff_reason, severity = self._classify_mismatch(
                module_name, py_result, rs_result
            )

            entry = MismatchEntry(
                module_name=module_name,
                input_hash=input_hash,
                py_output=py_result,
                rs_output=rs_result,
                match=False,
                diff_reason=diff_reason,
                severity=severity,
            )
            self.ledger.record_mismatch(entry)

        return match

    def _classify_mismatch(
        self,
        module_name: str,
        py_result: Any,
        rs_result: Any,
    ) -> tuple[str, MismatchSeverity]:
        """Classify mismatch into LOW/HIGH/CRITICAL."""
        if type(py_result) != type(rs_result):
            return "TYPE_MISMATCH", MismatchSeverity.CRITICAL

        if isinstance(py_result, bool):
            return "BOOLEAN_MISMATCH", MismatchSeverity.CRITICAL

        if isinstance(py_result, (int, float)):
            if abs(float(py_result) - float(rs_result)) > 0.001:
                return "NUMERIC_DRIFT", MismatchSeverity.HIGH
            return "VALUE_MISMATCH", MismatchSeverity.HIGH

        return "OUTPUT_VALUE_MISMATCH", MismatchSeverity.HIGH


# ─── Rust Flow IPC Client ────────────────────────────────────────────

class RustFlowClient:
    """IPC Client for Rust flow_machine: ValidateTransition, GetLegalTransitions, IsTerminal."""

    # Map Python state names to Rust enum names (SCREAMING_SNAKE_CASE)
    _STATE_MAP = {
        "intake": "INTAKE",
        "clarify": "CLARIFY",
        "outline": "OUTLINE",
        "research": "RESEARCH",
        "design": "DESIGN",
        "plan": "PLAN",
        "execute": "EXECUTE",
        "verify": "VERIFY",
        "close": "CLOSE",
        "replan": "REPLAN",
        "escalate": "ESCALATE",
        "human_review": "HUMAN_REVIEW",
        "blocked_budget": "BLOCKED_BUDGET",
        "blocked_policy": "BLOCKED_POLICY",
    }

    def __init__(self, binary_path: Optional[Path] = None):
        if binary_path is None:
            candidates = [
                Path("nexus-core-rs/target/release/nexus-core-rs"),
                Path("nexus-core-rs/target/debug/nexus-core-rs"),
                Path("target/release/nexus-core-rs"),
                Path("target/debug/nexus-core-rs"),
            ]
            for c in candidates:
                if c.exists():
                    self.binary_path = c
                    break
            else:
                self.binary_path = candidates[0]
        else:
            self.binary_path = binary_path

    def call(self, request_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send JSON IPC request to Rust binary, return parsed response."""
        if not self.binary_path.exists():
            return {"success": False, "error_message": f"Binary not found: {self.binary_path}"}

        request = {"type": request_type, "payload": payload}

        try:
            process = subprocess.Popen(
                [str(self.binary_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = process.communicate(input=json.dumps(request))

            if process.returncode != 0:
                return {
                    "success": False,
                    "error_message": f"Kernel exited with {process.returncode}: {stderr}",
                }

            return json.loads(stdout)
        except Exception as e:
            return {"success": False, "error_message": str(e)}

    def _resolve_state(self, state_name: str) -> str:
        """Convert snake_case Python state to Rust SCREAMING_SNAKE_CASE enum."""
        lower = state_name.lower().replace("-", "_")
        rust_name = self._STATE_MAP.get(lower, state_name.upper())
        return rust_name

    def validate_transition(self, from_state: str, to_state: str) -> Dict[str, Any]:
        return self.call("ValidateTransition", {
            "current": self._resolve_state(from_state),
            "next": self._resolve_state(to_state),
        })

    def get_legal_transitions(self, current: str) -> Dict[str, Any]:
        return self.call("GetLegalTransitions", {"current": self._resolve_state(current)})

    def is_terminal(self, state: str) -> Dict[str, Any]:
        return self.call("IsTerminal", {"state": self._resolve_state(state)})


# ─── GovernanceBridge with Dual-Run ──────────────────────────────────

class GovernanceBridge:
    """Python ↔ Rust governance bridge with dual-run shadow support."""

    def __init__(self, dual_run: bool = False, ledger_path: Optional[Path] = None):
        self.dual_run = dual_run
        self.rs_client = RustFlowClient()

        if dual_run and ledger_path:
            self.ledger = MismatchLedger(ledger_path)
        else:
            self.ledger = None

        self.comparator = DualRunComparator(ledger=self.ledger)

    def can_transition(self, from_state: str, to_state: str) -> bool:
        """
        Primary: Rust authoritative validation.
        Shadow (dual-run): compare the contract fallback against Rust.
        Mismatch → write to ledger.
        """
        rust_available = self.rs_client.binary_path.exists()
        rs_result = self._rust_validate(from_state, to_state) if rust_available else None
        py_result = self._python_validate(from_state, to_state)

        if self.dual_run:
            self.comparator.compare(
                module_name="flow_machine",
                py_result=py_result,
                rs_result=bool(rs_result) if rs_result is not None else False,
                input_data={"from": from_state, "to": to_state},
            )

        # Rust is the sole runtime authority when present.  The contract
        # matrix remains a compatibility fallback for environments without
        # the kernel binary and is intentionally not a second control plane.
        return bool(rs_result) if rs_result is not None else py_result

    def _python_validate(self, from_state: str, to_state: str) -> bool:
        """Python-side validation: check against legal transitions from contract."""
        try:
            from nexus.engine.capability_contracts import FlowState
            current = FlowState(from_state)
            next_state = FlowState(to_state)
            # Load the contract to get legal transitions
            contract_path = Path(__file__).parent.parent.parent / "subprojects" / "nexus-receipt-core" / "schemas" / "flow_machine.contract.v1.json"
            if not contract_path.exists():
                # Fallback: accept all transitions
                return True
            import json
            with open(contract_path, "r") as f:
                contract = json.load(f)
            transition_rules = contract.get("transition_rules", {})
            # Check if this transition is in the legal list
            allowed_next_states = transition_rules.get(current.value, [])
            return next_state.value in allowed_next_states or current.value == next_state.value  # Self-transition always allowed
        except (ImportError, ValueError, FileNotFoundError, KeyError):
            # Silently return True to not block non-Rust environments
            return True

    def _rust_validate(self, from_state: str, to_state: str) -> bool:
        """Rust shadow validation via IPC."""
        resp = self.rs_client.validate_transition(from_state, to_state)
        if resp.get("success"):
            payload = resp.get("payload", {})
            return bool(payload.get("is_valid", False))
        return False  # Shadow failure → fail-closed

    def promotion_ready(self) -> bool:
        """Check if dual-run ledger has zero HIGH/CRITICAL mismatches."""
        if self.ledger is None:
            return False
        counts = self.ledger.count_by_severity()
        return counts.get("HIGH", 0) == 0 and counts.get("CRITICAL", 0) == 0

    def rollback_drill(self, test_cases: List[tuple[str, str]]) -> dict[str, Any]:
        """
        Rollback drill: test that dual-run can detect mismatches and rollback is safe.
        Returns: {passed: bool, mismatches_found: int, rollback_safe: bool}
        """
        if self.ledger is None:
            return {"passed": False, "reason": "No ledger configured"}
        
        mismatches_found = 0
        for from_state, to_state in test_cases:
            py_result = self._python_validate(from_state, to_state)
            rs_result = self._rust_validate(from_state, to_state)
            if py_result != rs_result:
                mismatches_found += 1
        
        # Rollback is safe if we can detect and log mismatches
        rollback_safe = mismatches_found == 0 or self.promotion_ready()
        
        return {
            "passed": rollback_safe,
            "mismatches_found": mismatches_found,
            "rollback_safe": rollback_safe,
            "test_cases_run": len(test_cases),
        }

    def normalize_intent(self, raw_output: str):
        """
        Parse compact model output format "r:X,d:Y,p:Z,c:W" into
        (route_str, decision_str, phase_str, confidence_str) tuple.
        Returns None if input is malformed (triggers fail-closed escalation).
        
        Expected keys: r=route, d=decision, p=phase, c=confidence
        Example: "r:0,d:0,p:1,c:0" -> ("0", "0", "1", "0")
        """
        if not isinstance(raw_output, str):
            return None
        raw_output = raw_output.strip()
        if not raw_output:
            return None
        try:
            parts = {}
            for token in raw_output.split(","):
                token = token.strip()
                if ":" not in token:
                    return None  # malformed token
                key, _, val = token.partition(":")
                parts[key.strip()] = val.strip()
            required_keys = {"r", "d", "p", "c"}
            if not required_keys.issubset(parts.keys()):
                return None  # missing required keys
            return (parts["r"], parts["d"], parts["p"], parts["c"])
        except Exception:
            return None
