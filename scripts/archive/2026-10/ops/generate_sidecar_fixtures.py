
import json
from pathlib import Path

BASE_DIR = Path("tests/fixtures/s2t_memory_sidecar")

def write_fixture(subdir, receipt=None, log="", diff="", test_out="", plan=""):
    d = BASE_DIR / subdir
    d.mkdir(parents=True, exist_ok=True)
    if receipt is not None:
        (d / "receipt.json").write_text(json.dumps(receipt, indent=2))
    if log: (d / "execution.log").write_text(log)
    if diff: (d / "git_diff.stat").write_text(diff)
    if test_out: (d / "pytest.log").write_text(test_out)
    if plan: (d / "plan.md").write_text(plan)

def main():
    # 1. Success + Ready
    write_fixture("f1_success_ready", 
                  receipt={"passed": True, "task_id": "T1"},
                  log="All steps finished. Running tests...",
                  test_out="12 PASSED",
                  plan="1. Implement A\n2. Test A")

    # 2. Tests Red
    write_fixture("f2_tests_red",
                  receipt={"passed": False, "failure_reason": "test_failure"},
                  log="Finished implementation. Found regression.",
                  test_out="FAILED tests/test_core.py::test_repro",
                  diff="M core.py")

    # 3. Missing Task List
    write_fixture("f3_missing_tasklist",
                  receipt={"passed": False, "failure_reason": "task_not_found"},
                  log="Error: Specified task list 'tasks.json' is missing.")

    # 4. Model Not Called
    write_fixture("f4_model_not_called",
                  receipt={"model_calls": 0, "token_total": 0, "passed": False},
                  log="Skipping model call due to deterministic rescue.")

    # 5. Receipt Mismatch (e.g. log says fail, receipt says pass - though unlikely in Nexus)
    write_fixture("f5_receipt_mismatch",
                  receipt={"passed": True},
                  log="Critical error detected during execution. Phase failed.",
                  test_out="Error: process died")

    # 6. Dirty Workspace Unrelated
    write_fixture("f6_dirty_workspace",
                  receipt={"passed": False},
                  log="Cannot start task. Workspace has unrelated modified files.",
                  diff="M README.md (unrelated)")

    # 7. Verifier False Reject Suspected
    write_fixture("f7_false_reject",
                  receipt={"passed": False, "verifier_result": "fail"},
                  log="Implementing fix. Tests passed locally but verifier failed.",
                  test_out="PASSED Locally")

    # 8. 3B Advisor Semantic Rejected
    write_fixture("f8_semantic_rejected",
                  receipt={"passed": False, "advisor_outcome_status": "abstained: advisor_semantic_rejected"},
                  log="Advisor recommended a failed candidate.")

    # 9. Rollback Required
    write_fixture("f9_rollback",
                  receipt={"passed": False, "recovery_directive": "rollback"},
                  log="Breaking change detected. Rolling back changes.")

    # 10. Insufficient Evidence
    write_fixture("f10_insufficient_evidence",
                  log="Session started but no output generated.")

if __name__ == "__main__":
    main()
