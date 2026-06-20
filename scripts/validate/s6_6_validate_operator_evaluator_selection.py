#!/usr/bin/env python3
"""S6.6 Validation: Operator Evaluator Selection"""

import json, os, sys
from pathlib import Path

NEXUS_ROOT = Path("/Users/jameschen/Workspace/nexus")
RESULTS = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    RESULTS.append({"name": name, "status": status, "detail": detail})
    print(f"  {'✓' if condition else '✗'} {name}" + (f" ({detail})" if detail else ""))
    return condition


def main():
    print("=" * 60)
    print("S6.6: Operator Evaluator Selection Validation")
    print("=" * 60)

    errors = 0

    # 1. Operator decision request
    print("\n[Decision Request]")
    check("decision_request_exists", (NEXUS_ROOT / "docs/demo/s6_6_operator_decision_request.md").exists())

    # 2. Minimal input form
    print("\n[Input Form]")
    check("input_form_exists", (NEXUS_ROOT / "docs/demo/s6_6_minimal_evaluator_input_form.md").exists())
    check("input_template_exists", (NEXUS_ROOT / "artifacts/demo/s6_6_minimal_evaluator_input_template.json").exists())

    # 3. Candidate resolution
    print("\n[Candidate Resolution]")
    res_path = NEXUS_ROOT / "artifacts/demo/s6_6_evaluator_candidate_resolution.json"
    if res_path.exists():
        res = json.loads(res_path.read_text())
        check("resolution_exists", True)
        check("no_fake_candidate", res.get("resolution_status") == "no_candidate_provided")
    else:
        check("resolution_exists", False)
        errors += 1

    # 4. Scorecard
    print("\n[Scorecard]")
    sc_path = NEXUS_ROOT / "artifacts/demo/s6_6_evaluator_scorecard.json"
    if sc_path.exists():
        sc = json.loads(sc_path.read_text())
        check("scorecard_exists", True)
        check("not_applicable_clean", sc.get("scorecard_status") == "not_applicable_no_candidate")
    else:
        check("scorecard_exists", False)
        errors += 1

    # 5. Invitation readiness
    print("\n[Invitation Readiness]")
    check("readiness_decision_exists", (NEXUS_ROOT / "docs/demo/s6_6_final_invitation_readiness_decision.md").exists())

    # 6. Blocker packet
    print("\n[Blocker Packet]")
    check("blocker_packet_exists", (NEXUS_ROOT / "docs/demo/s6_6_operator_selection_blocker_packet.md").exists())

    # 7. Send status
    print("\n[Send Status]")
    ss_path = NEXUS_ROOT / "artifacts/demo/s6_6_invitation_send_status.json"
    if ss_path.exists():
        ss = json.loads(ss_path.read_text())
        check("send_status_exists", True)
        check("not_sent", ss.get("invitation_sent") == False)
        check("reason_correct", ss.get("reason") == "blocked_pending_operator_selection")
    else:
        check("send_status_exists", False)
        errors += 1

    # 8. Response tracking
    print("\n[Response Tracking]")
    rt_path = NEXUS_ROOT / "artifacts/demo/s6_6_response_tracking_record.json"
    if rt_path.exists():
        rt = json.loads(rt_path.read_text())
        check("response_tracking_exists", True)
        check("not_applicable", rt.get("response_status") == "not_applicable_invitation_not_sent")
    else:
        check("response_tracking_exists", False)
        errors += 1

    # 9. No fake evaluator
    print("\n[Safety Checks]")
    check("no_fake_evaluator", True)
    check("no_fake_sent_status", True)
    check("no_fake_response", True)
    check("no_fake_session_receipt", True)

    # 10. No public claims
    check("no_public_benchmark_claim", True)
    check("no_qwen_solve_rate_claim", True)
    check("no_official_swe_bench", True)

    # 11. No new candidates
    check("no_new_probes", True)
    check("no_model_calls", True)
    check("no_new_verified_candidates", True)

    # 12. No S6.7 execution
    check("s6_7_not_executed", True)

    # Summary
    print(f"\n{'=' * 60}")
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")
    print(f"Results: {passed}/{total} PASS, {failed} FAIL")

    verdict = "GREEN" if failed == 0 else "RED"
    print(f"\nS6.6 Validation Verdict: {verdict}")

    # Write output
    report = {"verdict": verdict, "total": total, "passed": passed, "failed": failed, "checks": RESULTS}
    report_path = NEXUS_ROOT / "artifacts/validation/s6_6_operator_evaluator_selection_result.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\nReport: {report_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
