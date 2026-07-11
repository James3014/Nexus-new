"""N30R-V3.1 Phase 1: FULL profile multi-candidate lifecycle proof.

Proves that with execution_topology='local_committee_only' and FULL armor profile:
  - LocalCommitteeCandidateProvider generates >= 2 distinct candidates
  - DDTreeLocalExecutor is invoked and participates in selection
  - AutoreasonLocalExecutor is invoked and participates in selection
  - Winner is isolated and verifier is reached

Uses InjectedLocalModelProvider (no Ollama) to return distinct patches for each
proposer in the committee, with judge providing ranking evidence.
"""
import os
import tempfile


GREET_ORIG   = 'def greet(name)\n    return f"Hello, {name}!"\n'
GREET_SEARCH = 'def greet(name)\n    return f"Hello, {name}!"'

GOOD_REPLACE  = 'def greet(name):\n    return f"Hello, {name}!"'
WRONG_REPLACE = 'def greet(name):\n    return "WRONG_CANDIDATE_2"'

VERIFIER_CMD = ("python3", "-c",
                "from f import greet; assert greet('world') == 'Hello, world!'")


def _make_ssrp(search: str, replace: str, filename: str = "f.py") -> str:
    return (
        f"FILE: {filename}\n"
        f"<<<<<<< SEARCH\n{search}\n"
        f"=======\n{replace}\n"
        f">>>>>>> REPLACE"
    )


def test_full_multi_candidate_lifecycle():
    """
    FULL profile multi-candidate lifecycle (local_committee_only topology).

    Asserts:
      - initial_execution_profile = FULL (NEXUS_FORCE_FULL_ARMOR=1)
      - committee_candidate_count >= 2
      - distinct candidate hashes >= 2
      - DDTree invoked (selected_candidate_ids populated)
      - Autoreason invoked
      - Winner isolated: candidate_isolated = True
      - Verifier reached: verifier_result != 'not_run'
    """
    from nexus.services.local_heal.local_model_executor import (
        LocalModelExecutor,
        LocalModelExecutorRequest,
    )
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider

    call_log: list[str] = []

    def gen(req):
        p = req.prompt
        call_log.append(p[:80])

        # Judge prompt (no SEARCH/REPLACE needed — it's evaluation only)
        if "judge" in p.lower() or "ranking" in p.lower() or "evaluating" in p.lower():
            return "Candidate 1 is better: it uses f-string and returns the correct greeting."

        # Proposer 1 — correct patch
        if "proposer_1" in p or "Proposer 1" in p or call_log.count(p[:80]) == 1:
            return _make_ssrp(GREET_SEARCH, GOOD_REPLACE)

        # Proposer 2 — incorrect patch (distinct hash)
        return _make_ssrp(GREET_SEARCH, WRONG_REPLACE)

    provider = InjectedLocalModelProvider(generate_fn=gen)

    route_context = {
        "signal_snapshot": {
            "execution_topology":   "local_committee_only",
            "protocol_mode":        "anchored_edit",
            "provider_timeout_sec": 30.0,
            "mutation_allowed":     True,
            "verifier_allowed":     True,
            "routing_tier":         "L3_swarm_deep",
            # Committee configuration — 2 proposers + 1 judge
            "proposer_specs": [
                {"role": "primary",   "model": "proposer-model-1"},
                {"role": "secondary", "model": "proposer-model-2"},
            ],
            "judge_model":  "judge-model",
            "executor_model": "proposer-model-1",
            "reasoning_mode": "DEEP",
        },
        "verifier_command": list(VERIFIER_CMD),
        "target_file":   "f.py",
        "locked_search": GREET_SEARCH,
        "python_executable": "python3",
    }

    os.environ["NEXUS_FORCE_FULL_ARMOR"] = "1"
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "f.py"), "w") as fh:
                fh.write(GREET_ORIG)

            req = LocalModelExecutorRequest(
                task_id="full-multi-candidate-proof",
                problem_statement="Fix the greet function to return the correct greeting.",
                repo_root=tmpdir,
                target_file="f.py",
                selected_capabilities=("repair_loop", "ddtree", "autoreason"),
                evidence_refs=("evidence-1",),
                route_context=route_context,
                mutation_allowed=True,
                verifier_allowed=True,
                dry_run=False,
                execution_topology="local_committee_only",
            )

            resp = LocalModelExecutor.run(req, provider=provider)
    finally:
        os.environ.pop("NEXUS_FORCE_FULL_ARMOR", None)

    raw = resp.raw_model_metadata or {}

    # ── Profile check ──────────────────────────────────────────────────────
    initial = raw.get("initial_execution_profile", "UNKNOWN")
    assert initial == "FULL", (
        f"Expected FULL profile (NEXUS_FORCE_FULL_ARMOR=1), got {initial!r}"
    )

    # ── Multi-candidate check ──────────────────────────────────────────────
    # committee_candidate_receipts lists each candidate envelope
    attempt_receipt = raw.get("local_armor_attempt_receipt", {})
    cand_receipts = attempt_receipt.get("committee_candidate_receipts", [])
    cand_count = len(cand_receipts)

    # Fallback: check committee_candidates_info in raw_meta directly
    if cand_count == 0:
        cand_info = raw.get("committee_candidates_info", [])
        cand_count = len(cand_info)

    assert cand_count >= 2, (
        f"Expected >= 2 committee candidates, got {cand_count}.\n"
        f"raw_keys={list(raw.keys())}"
    )

    # ── Distinct hash check ────────────────────────────────────────────────
    # At least 2 non-empty, distinct candidate hashes
    hashes = set()
    for c in cand_receipts:
        h = c.get("candidate_patch_hash", "")
        if h and h != ("0" * 64):   # exclude empty/zero hashes
            hashes.add(h)
    if len(hashes) < 2:
        # Try committee_candidates_info
        for c in raw.get("committee_candidates_info", []):
            h = c.get("candidate_hash", "")
            if h:
                hashes.add(h)

    assert len(hashes) >= 2, (
        f"Expected >= 2 distinct candidate hashes, got {hashes}\n"
        f"cand_receipts={cand_receipts}"
    )

    # ── DDTree invoked ─────────────────────────────────────────────────────
    ddtree_inv = raw.get("ddtree_invoked", False)
    assert ddtree_inv, (
        f"DDTree must be invoked for FULL multi-candidate selection.\n"
        f"ddtree_invoked={ddtree_inv}  raw_keys={list(raw.keys())}"
    )

    # ── Autoreason invoked ─────────────────────────────────────────────────
    autoreason_inv = raw.get("autoreason_invoked", False)
    assert autoreason_inv, (
        f"Autoreason must be invoked for FULL multi-candidate selection.\n"
        f"autoreason_invoked={autoreason_inv}"
    )

    # ── Winner isolated ────────────────────────────────────────────────────
    cand_isolated = raw.get("candidate_isolated", False)
    assert cand_isolated, (
        f"Winner candidate must be isolated (applied to workspace).\n"
        f"candidate_isolated={cand_isolated}  "
        f"patch_lifecycle_state={raw.get('patch_lifecycle_state')}"
    )

    # ── Verifier reached ──────────────────────────────────────────────────
    verifier_result = raw.get("isolated_verifier_status", "not_run")
    assert verifier_result != "not_run", (
        f"Verifier must be reached for FULL committee path.\n"
        f"isolated_verifier_status={verifier_result!r}"
    )

    # ── Authoritative Ledger Check ───────────────────────────────────────
    ledger = raw.get("llm_call_ledger", {})
    assert ledger.get("authoritative") is True, f"Ledger should be authoritative: {ledger}"
    assert ledger.get("phase_complete") is True, f"Ledger phase complete: {ledger}"
    assert ledger.get("attempt_context_complete") is True, f"Attempt complete: {ledger}"
    assert ledger.get("profile_context_complete") is True, f"Profile complete: {ledger}"

    by_phase = ledger.get("by_phase", {})
    assert by_phase.get("judge", 0) == 1, f"Expected 1 judge call, got: {by_phase}"
    assert by_phase.get("proposer", 0) == 2, f"Expected 2 proposer calls, got: {by_phase}"

    records = raw.get("llm_call_ledger_records", [])
    assert len(records) == 3
    for r in records:
        assert r["attempt_id"] == "attempt-1"
        assert r["execution_profile"] == "FULL"
        assert r["phase"] in ("judge", "proposer")
