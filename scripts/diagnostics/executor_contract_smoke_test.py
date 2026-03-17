#!/usr/bin/env python3
"""
[Phase 4 Gate] Executor Contract Smoke Test
Verifies executor's protocol-level behavior based on ACTUAL current API:
  - _extract_marker_payload → returns tuple[Optional[dict], Optional[str]]
  - _classify_provider_error → returns ProviderErrorType Enum

Tests:
  1. Noisy stdout with valid marker → (dict payload, None)
  2. Missing marker → (None, "PROVIDER_CONTRACT_VIOLATION: ...")
  3. Truncated (begin but no end) → (None, "OUTPUT_TRUNCATED: ...")
  4. Tool call text → ProviderErrorType.AGENT_TOOL_INTERFERENCE
  5. Quota error in exception → ProviderErrorType.QUOTA_LIMIT

Final verdict: EXECUTOR_CONTRACT_READY | NOT_READY
"""
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

PASSES = []
FAILURES = []

def record(name, ok, reason=""):
    if ok:
        PASSES.append(name)
        print(f"✅ {name}")
    else:
        FAILURES.append(f"{name}: {reason}")
        print(f"❌ {name}: {reason}")

from nexus.executors.gemini import GeminiExecutor
from nexus.executors.protocol import ProviderErrorType

def make_executor():
    exec = GeminiExecutor.__new__(GeminiExecutor)
    exec.model = "gemini-2.0-flash"
    exec.llm = MagicMock()
    return exec

VALID_JSON = json.dumps({
    "status": "PASS", "violations": [], "patch_diff": "", "files_touched": []
})

def main():
    # ── T1: Noisy stdout — valid marker → dict payload ────────────────────────────
    try:
        noisy_output = (
            "Some log noise here\n"
            "More irrelevant lines\n"
            "<NEXUS_JSON_BEGIN>\n"
            + VALID_JSON + "\n"
            "<NEXUS_JSON_END>\n"
            "Trailing garbage"
        )
        executor = make_executor()
        payload, err = executor._extract_marker_payload(noisy_output)
        assert payload is not None, f"Payload is None, err={err}"
        assert isinstance(payload, dict), f"Payload is not dict: {type(payload)}"
        assert payload.get("status") == "PASS"
        assert err is None, f"Expected no error, got: {err}"
        record("T1: Noisy Stdout — Marker Extraction Returns Dict Payload", True)
    except Exception as e:
        record("T1: Noisy Stdout — Marker Extraction Returns Dict Payload", False, str(e))

    # ── T2: Missing marker → PROVIDER_CONTRACT_VIOLATION ──────────────────────────
    try:
        no_marker = "Just some random text without any marker at all."
        executor2 = make_executor()
        payload2, err2 = executor2._extract_marker_payload(no_marker)
        assert payload2 is None, f"Expected None payload, got: {payload2}"
        assert err2 is not None, "Expected error string"
        assert "PROVIDER_CONTRACT_VIOLATION" in err2, f"Expected PROVIDER_CONTRACT_VIOLATION in: {err2}"
        record("T2: Missing Marker → (None, PROVIDER_CONTRACT_VIOLATION)", True)
    except Exception as e:
        record("T2: Missing Marker → (None, PROVIDER_CONTRACT_VIOLATION)", False, str(e))

    # ── T3: Truncated output → OUTPUT_TRUNCATED ────────────────────────────────────
    try:
        truncated = "<NEXUS_JSON_BEGIN>\n" + '{"status":"PASS","patch_diff":"--- a/'
        # No <NEXUS_JSON_END>
        executor3 = make_executor()
        payload3, err3 = executor3._extract_marker_payload(truncated)
        assert payload3 is None, f"Expected None payload for truncated, got: {payload3}"
        assert err3 is not None
        assert "OUTPUT_TRUNCATED" in err3 or "PROVIDER_CONTRACT_VIOLATION" in err3, \
            f"Expected OUTPUT_TRUNCATED or PROVIDER_CONTRACT_VIOLATION in: {err3}"
        record("T3: Truncated Output → (None, truncation/contract error)", True)
    except Exception as e:
        record("T3: Truncated Output → (None, truncation/contract error)", False, str(e))

    # ── T4: Tool call text → AGENT_TOOL_INTERFERENCE ──────────────────────────────
    try:
        tool_text = 'I will use tool: {"type": "tool_use", "name": "bash", "input": {}}'
        executor4 = make_executor()
        err_type = executor4._classify_provider_error(tool_text, None)
        assert err_type == ProviderErrorType.AGENT_TOOL_INTERFERENCE, \
            f"Expected AGENT_TOOL_INTERFERENCE, got: {err_type}"
        record("T4: Tool Call Text → ProviderErrorType.AGENT_TOOL_INTERFERENCE", True)
    except Exception as e:
        record("T4: Tool Call Text → ProviderErrorType.AGENT_TOOL_INTERFERENCE", False, str(e))

    # ── T5: Quota exception → QUOTA_LIMIT ─────────────────────────────────────────
    try:
        quota_err = Exception("429 RESOURCE_EXHAUSTED: quota exceeded for this project")
        executor5 = make_executor()
        err_type = executor5._classify_provider_error("", quota_err)
        assert err_type == ProviderErrorType.QUOTA_LIMIT, \
            f"Expected QUOTA_LIMIT, got: {err_type}"
        record("T5: Quota Exception → ProviderErrorType.QUOTA_LIMIT", True)
    except Exception as e:
        record("T5: Quota Exception → ProviderErrorType.QUOTA_LIMIT", False, str(e))


    # ── Final Verdict ──────────────────────────────────────────────────────────────
    print("\n" + "─" * 60)
    print(f"PASS: {len(PASSES)} | FAIL: {len(FAILURES)}")
    if FAILURES:
        print("\nFailed checks:")
        for f in FAILURES:
            print(f"  ❌ {f}")
        print("\n🔴  EXECUTOR_CONTRACT_READY: NOT_READY")
        sys.exit(1)
    else:
        print("\n🟢  EXECUTOR_CONTRACT_READY: READY")
        sys.exit(0)

if __name__ == "__main__":
    main()
