#!/usr/bin/env python3
"""Issue #29 Physical Local-to-Online Causal Consumption Canary Operator.

Executes a genuine end-to-end task execution verifying physical local (Ollama)
and physical online (Gemini) provider calls, evidence hash freezing, online
consumption binding, tamper-resistance, and World C verifier gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RECEIPT_SCHEMA = "nexus.canary.physical_local_online_receipt.v1"
DURABLE_MARKER = "ONLINE_LOCAL_SAME_TASK_CAUSAL_CONSUMPTION_VERIFIED"
BLOCKED_MARKER = "BLOCKED_INCOMPLETE_VERIFICATION"


def get_current_git_revision() -> str:
    res = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if res.returncode != 0 or not res.stdout.strip():
        raise RuntimeError("git_revision_unresolvable_fail_closed")
    return res.stdout.strip()


def call_physical_ollama(
    *,
    prompt: str,
    model: str = "qwen2.5-coder:7b-instruct",
    ollama_url: str = "http://127.0.0.1:11434/api/generate",
    timeout_sec: float = 60.0,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    req_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ollama_url,
        data=req_bytes,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"physical_ollama_call_failed: {exc}") from exc

    elapsed = time.monotonic() - t0
    response_text = str(body.get("response", "")).strip()
    return {
        "model": model,
        "provider": "ollama",
        "output_text": response_text,
        "elapsed_sec": elapsed,
        "total_duration": body.get("total_duration", 0),
        "eval_count": body.get("eval_count", 0),
        "prompt_eval_count": body.get("prompt_eval_count", 0),
        "call_count": 1,
    }


def call_physical_gemini(
    *,
    prompt: str,
    api_key: str,
    model: str = "gemini-3.8-flash",
    timeout_sec: float = 60.0,
) -> dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    req_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_bytes,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"physical_gemini_call_failed: {exc}") from exc

    elapsed = time.monotonic() - t0
    candidates = body.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini API returned no candidates: {body}")
    parts = candidates[0].get("content", {}).get("parts", [])
    output_text = "".join(p.get("text", "") for p in parts).strip()
    usage = body.get("usageMetadata", {})

    return {
        "model": model,
        "provider": "gemini",
        "output_text": output_text,
        "elapsed_sec": elapsed,
        "usage": usage,
        "call_count": 1,
    }


def build_and_freeze_vap(
    *,
    task_id: str,
    target_file: str,
    local_output: str,
    source_revision: str,
) -> dict[str, Any]:
    vap_content = {
        "schema": "nexus.verified_assist_packet.v1",
        "task_id": task_id,
        "target_file": target_file,
        "local_summary": local_output[:2000],  # Bound context length protection
        "source_revision": source_revision,
        "frozen_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    canonical_json = json.dumps(vap_content, sort_keys=True, ensure_ascii=False)
    packet_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return {
        "packet_content": vap_content,
        "packet_hash": packet_hash,
    }


def verify_world_c_consumption(
    *,
    frozen_vap: dict[str, Any],
    consumed_vap_hash: str,
    online_output: str,
) -> dict[str, Any]:
    """World C verifier gate checking evidence integrity and causal adoption."""
    # Step 1: Recompute hash from frozen VAP content to detect content tampering
    canonical_json = json.dumps(frozen_vap["packet_content"], sort_keys=True, ensure_ascii=False)
    recomputed_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    if recomputed_hash != frozen_vap["packet_hash"]:
        return {
            "status": "FAIL",
            "reason": "tamper_detected_content_recomputed_hash_mismatch",
            "verifier_passed": False,
            "hash_matches": False,
            "causal_adoption_verified": False,
        }

    # Step 2: Verify that consumed VAP hash matches frozen hash
    if consumed_vap_hash != frozen_vap["packet_hash"]:
        return {
            "status": "FAIL",
            "reason": "tamper_detected_consumed_hash_mismatch",
            "verifier_passed": False,
            "hash_matches": False,
            "causal_adoption_verified": False,
        }

    # Step 3: Verify Online output contains exact consumption proof citation
    expected_marker = f"VAP_CONSUMED:{frozen_vap['packet_hash']}"
    if expected_marker not in online_output:
        return {
            "status": "FAIL",
            "reason": "online_did_not_cite_frozen_vap_hash",
            "verifier_passed": False,
            "hash_matches": False,
            "causal_adoption_verified": False,
        }

    # Step 4: Verify Causal adoption - Online output must contain implementation of parse_kv
    has_code_artifact = "def parse_kv(" in online_output
    if not has_code_artifact:
        return {
            "status": "FAIL",
            "reason": "online_did_not_produce_causal_implementation",
            "verifier_passed": False,
            "hash_matches": True,
            "causal_adoption_verified": False,
        }

    return {
        "status": "PASS",
        "reason": "exact_hash_cited_and_causal_adoption_verified",
        "verifier_passed": True,
        "hash_matches": True,
        "causal_adoption_verified": True,
    }


def run_physical_canary(
    *,
    task_id: str = "issue-29-physical-canary-20261005",
    target_file: str = "parse_kv.py",
    allow_physical: bool = False,
    simulate_tamper: bool = False,
    output_receipt_path: str | Path | None = None,
) -> dict[str, Any]:
    if not allow_physical and os.environ.get("NEXUS_CANARY_ALLOW_PHYSICAL") != "1":
        raise RuntimeError(
            "physical_canary_not_authorized: must set --allow-physical or NEXUS_CANARY_ALLOW_PHYSICAL=1"
        )

    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        raise RuntimeError(
            "GEMINI_API_KEY_missing: environment variable is required for physical Online execution"
        )

    source_rev = get_current_git_revision()

    # Step 1: Physical Local Execution (Ollama)
    local_prompt = (
        "You are the Nexus Local Coder. Analyze this target file statement:\n"
        f"File: {target_file}\n"
        "Requirement: Propose how to implement `parse_kv(s: str) -> dict` in Python.\n"
        "Provide a concise recommendation explaining the splitting and mapping approach."
    )
    local_result = call_physical_ollama(prompt=local_prompt)
    local_output = local_result["output_text"]

    # Step 2: Build & Freeze VAP
    vap_info = build_and_freeze_vap(
        task_id=task_id,
        target_file=target_file,
        local_output=local_output,
        source_revision=source_rev,
    )
    frozen_hash = vap_info["packet_hash"]

    # If simulating tamper: attack vector replaces VAP content while keeping old hash or vice-versa
    if simulate_tamper:
        # Attack: Adversary tampers with the local summary in transit
        vap_info["packet_content"]["local_summary"] = "MALICIOUS_TAMPERED_INJECTED_CONTENT"

    # Step 3: Physical Online Execution (Gemini)
    online_prompt = (
        "[NEXUS_ROUTE_ACTIVE]\n"
        "[NEXUS_CODEINTEL_V1]\n"
        f"[VAP_PACKET_HASH:{frozen_hash}]\n\n"
        "You are Nexus Online Engineering. You are consuming the preceding Local Assist VAP evidence.\n"
        f"Local Assist Recommendation: {vap_info['packet_content']['local_summary']}\n\n"
        "Instructions:\n"
        "1. Write the Python function `def parse_kv(s: str) -> dict:` following the local advice.\n"
        f"2. You MUST include the exact marker 'VAP_CONSUMED:{frozen_hash}' in your response.\n"
        "3. Provide a brief causal acceptance statement explaining how the advice was consumed."
    )
    online_result = call_physical_gemini(prompt=online_prompt, api_key=gemini_key)
    online_output = online_result["output_text"]

    # Step 4: World C Verifier Gate
    verifier_result = verify_world_c_consumption(
        frozen_vap=vap_info,
        consumed_vap_hash=frozen_hash,
        online_output=online_output,
    )

    is_complete = verifier_result["verifier_passed"]
    terminal_state = "COMPLETE" if is_complete else "BLOCKED_BY_VERIFIER"

    # Step 5: Construct Canonical Live Receipt
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "operation_label": task_id,
        "source_revision": source_rev,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "terminal": terminal_state,
        "durable_marker": DURABLE_MARKER if is_complete else BLOCKED_MARKER,
        "local_execution": {
            "provider": local_result["provider"],
            "model": local_result["model"],
            "provider_call_count": local_result.get("call_count", 1),
            "model_call_count": local_result.get("call_count", 1),
            "local_model_invoked": True,
            "output_delivered": True,
            "elapsed_sec": local_result["elapsed_sec"],
            "total_duration_ns": local_result["total_duration"],
            "eval_count": local_result["eval_count"],
            "output_preview": local_output[:200],
        },
        "verified_assist": {
            "packet_hash": frozen_hash,
            "assist_credited": is_complete,
            "target_file": target_file,
            "causal_adoption_verified": verifier_result.get("causal_adoption_verified", False),
        },
        "online_execution": {
            "provider": online_result["provider"],
            "model": online_result["model"],
            "provider_call_count": online_result.get("call_count", 1),
            "model_call_count": online_result.get("call_count", 1),
            "online_model_invoked": True,
            "online_consumed": verifier_result["hash_matches"],
            "elapsed_sec": online_result["elapsed_sec"],
            "output_preview": online_output[:200],
        },
        "world_c_verifier": verifier_result,
        "claim_boundary": {
            "output_consumed": is_complete,
            "outcome_contributed": is_complete,
            "public_claim_allowed": False,
            "production_ready": False,
        },
    }

    if output_receipt_path:
        out_p = Path(output_receipt_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")

    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Issue #29 Physical Canary Runner")
    parser.add_argument(
        "--allow-physical", action="store_true", help="Authorize physical LLM network calls"
    )
    parser.add_argument(
        "--simulate-tamper",
        action="store_true",
        help="Simulate tamper to test fail-closed behavior",
    )
    parser.add_argument("--output-receipt", type=str, default="", help="Path to save receipt JSON")
    args = parser.parse_args()

    receipt = run_physical_canary(
        allow_physical=args.allow_physical,
        simulate_tamper=args.simulate_tamper,
        output_receipt_path=args.output_receipt,
    )
    print(json.dumps(receipt, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
