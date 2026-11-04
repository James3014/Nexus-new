from __future__ import annotations

import copy

from nexus.learning.zero_trust_v2_receipts import (
    REPORT_KIND_M45_M52,
    REPORT_KIND_MANUAL_TRIAL,
    REPORT_KIND_POST_APPLY_SMOKE,
    REPORT_KIND_ROLLOUT,
    REPORT_KIND_RUNTIME_APPLY,
    build_runtime_signed_receipt,
    sign_report,
    verify_runtime_signed_receipt,
)
from scripts.ops.build_zero_trust_v2_unified_mainline import build_zero_trust_v2_unified_mainline

KEY = "report-key"


def _chain() -> dict:
    return {
        "m45_m52": sign_report(
            {
                "summary": {"m45_clean_v2_receipt_count": 102, "m51_v2_ready_capability_count": 34},
                "m45_behavior_run_results": [{"blockers": []}],
            },
            kind=REPORT_KIND_M45_M52,
            secret=KEY,
        ),
        "manual_trial": sign_report(
            {"status": "PASS", "summary": {"manual_apply_trial_ready": True}},
            kind=REPORT_KIND_MANUAL_TRIAL,
            secret=KEY,
        ),
        "rollout": sign_report(
            {
                "status": "PASS",
                "summary": {"p0_rollout_complete": True, "p1_p2_rollout_complete": True},
            },
            kind=REPORT_KIND_ROLLOUT,
            secret=KEY,
        ),
        "runtime_apply": sign_report(
            {
                "status": "PASS",
                "summary": {"runtime_update_allowed": True, "v2_default_applied_count": 34},
            },
            kind=REPORT_KIND_RUNTIME_APPLY,
            secret=KEY,
        ),
        "post_apply_smoke": sign_report(
            {"status": "PASS", "summary": {"case_count": 34, "pass_count": 34}},
            kind=REPORT_KIND_POST_APPLY_SMOKE,
            secret=KEY,
        ),
    }


def _signed_m45(report: dict) -> dict:
    return sign_report(report, kind=REPORT_KIND_M45_M52, secret=KEY)


def _run(chain: dict, secret: str | None = KEY) -> dict:
    return build_zero_trust_v2_unified_mainline(signing_secret=secret, **chain)


def test_3374_signed_chain_passes() -> None:
    assert _run(_chain())["status"] == "PASS"


def test_3374_edited_count_does_not_pass() -> None:
    for name, path in (
        ("post_apply_smoke", ("summary", "pass_count")),
        ("runtime_apply", ("summary", "v2_default_applied_count")),
        ("rollout", ("summary", "p1_p2_rollout_complete")),
        ("manual_trial", ("summary", "manual_apply_trial_ready")),
        ("m45_m52", ("summary", "m45_clean_v2_receipt_count")),
    ):
        chain = _chain()
        chain[name] = copy.deepcopy(chain[name])
        original = chain[name][path[0]][path[1]]
        chain[name][path[0]][path[1]] = (
            0 if isinstance(original, int) and original else (not original)
        )
        result = _run(chain)
        assert result["status"] != "PASS", name
    # an edit that raises a count is caught too
    chain = _chain()
    chain["post_apply_smoke"] = {
        "status": "PASS",
        "summary": {"case_count": 34, "pass_count": 34},
        "report_signature": {
            **chain["post_apply_smoke"]["report_signature"],
            "fields": {"status": "PASS", "case_count": 34, "pass_count": 34},
        },
    }
    assert _run(chain)["status"] == "PASS"
    chain["post_apply_smoke"]["summary"]["pass_count"] = 35
    assert _run(chain)["status"] != "PASS"


def test_3374_missing_signature_does_not_pass() -> None:
    for name in ("m45_m52", "manual_trial", "rollout", "runtime_apply", "post_apply_smoke"):
        chain = _chain()
        chain[name] = {k: v for k, v in chain[name].items() if k != "report_signature"}
        result = _run(chain)
        assert result["status"] != "PASS", name


def test_3374_missing_key_blocks_every_segment() -> None:
    result = _run(_chain(), secret=None)
    assert result["status"] == "BLOCKED"
    assert result["summary"]["promotion_credit_allowed"] is False
    assert result["summary"]["milestone_pass_count"] < result["summary"]["milestone_count"]


def test_3374_receipt_signature_in_report_position_does_not_verify() -> None:
    receipt = build_runtime_signed_receipt(
        run_id="r",
        row_id="x",
        arm_id="a",
        capability_id="c",
        skill_id="s",
        artifact_hash="h",
        raw_observation={},
        secret=KEY,
    )
    chain = _chain()
    chain["post_apply_smoke"] = {**chain["post_apply_smoke"], "report_signature": receipt}
    assert _run(chain)["status"] != "PASS"


def test_3374_swapped_report_kind_does_not_verify() -> None:
    chain = _chain()
    chain["manual_trial"], chain["rollout"] = (
        {
            "status": "PASS",
            "summary": {
                "manual_apply_trial_ready": True,
                "p0_rollout_complete": True,
                "p1_p2_rollout_complete": True,
            },
            "report_signature": chain["rollout"]["report_signature"],
        },
        chain["manual_trial"],
    )
    assert _run(chain)["status"] != "PASS"


def test_3374_report_blockers_name_the_signature() -> None:
    chain = _chain()
    chain["post_apply_smoke"] = {"status": "PASS", "summary": {"case_count": 34, "pass_count": 34}}
    by_id = {item["milestone"]: item for item in _run(chain)["milestones"]}
    assert by_id["M64"]["blockers"] == ["post_apply_smoke_report_signature_not_verified"]


def test_unified_mainline_blocks_on_unclean_canary_receipts() -> None:
    result = build_zero_trust_v2_unified_mainline(
        signing_secret=KEY,
        m45_m52=_signed_m45({
            "summary": {"m45_clean_v2_receipt_count": 0, "m51_v2_ready_capability_count": 0},
            "m45_behavior_run_results": [
                {
                    "blockers": [
                        "missing_required_capability_receipts",
                        "missing_runtime_signed_v2_receipt",
                        "no_eligible_behavior_row",
                        "semantic_not_verified",
                    ]
                }
            ],
        }),
    )

    assert result["status"] == "BLOCKED"
    assert result["summary"]["v2_unification_complete"] is False
    assert result["summary"]["runtime_mutation_allowed"] is False
    by_id = {item["milestone"]: item for item in result["milestones"]}
    assert by_id["M53"]["status"] == "BLOCKED"
    assert by_id["M54"]["status"] == "BLOCKED"
    assert by_id["M56"]["blockers"] == ["clean_v2_receipt_count_lt_3"]
    assert "missing_runtime_signed_v2_receipt" in result["root_blockers"]


def test_unified_mainline_stays_blocked_until_apply_and_smoke() -> None:
    result = build_zero_trust_v2_unified_mainline(
        signing_secret=KEY,
        m45_m52=_signed_m45({
            "summary": {"m45_clean_v2_receipt_count": 3, "m51_v2_ready_capability_count": 34},
            "m45_behavior_run_results": [{"blockers": []}],
        }),
    )

    assert result["status"] == "BLOCKED"
    assert result["summary"]["v2_unification_complete"] is False
    assert result["summary"]["runtime_mutation_allowed"] is False
    by_id = {item["milestone"]: item for item in result["milestones"]}
    assert by_id["M57"]["status"] == "BLOCKED"
    assert by_id["M63"]["status"] == "BLOCKED"


def test_unified_mainline_can_pass_after_apply_and_post_smoke() -> None:
    result = build_zero_trust_v2_unified_mainline(
        signing_secret=KEY,
        m45_m52=_signed_m45({
            "summary": {"m45_clean_v2_receipt_count": 102, "m51_v2_ready_capability_count": 34},
            "m45_behavior_run_results": [{"blockers": []}],
        }),
        manual_trial=_chain()["manual_trial"],
        rollout=_chain()["rollout"],
        runtime_apply=_chain()["runtime_apply"],
        post_apply_smoke=_chain()["post_apply_smoke"],
    )

    assert result["status"] == "PASS"
    assert result["summary"]["v2_unification_complete"] is True
    assert result["summary"]["runtime_mutation_allowed"] is True
    assert all(item["status"] == "PASS" for item in result["milestones"])


def _failing_signed(name: str, failing: dict) -> dict:
    kinds = {
        "m45_m52": REPORT_KIND_M45_M52,
        "manual_trial": REPORT_KIND_MANUAL_TRIAL,
        "rollout": REPORT_KIND_ROLLOUT,
        "runtime_apply": REPORT_KIND_RUNTIME_APPLY,
        "post_apply_smoke": REPORT_KIND_POST_APPLY_SMOKE,
    }
    return sign_report(failing, kind=kinds[name], secret=KEY)


# (segment, signed failing report, edit applied afterwards, reason expected in the result)
_EDIT_CASES = {
    "rollout_p1_p2_flag": (
        "rollout",
        {
            "status": "PASS",
            "summary": {"p0_rollout_complete": True, "p1_p2_rollout_complete": False},
        },
        ("summary", "p1_p2_rollout_complete", True),
        "rollout_report_signature_not_verified",
    ),
    "rollout_p0_flag": (
        "rollout",
        {
            "status": "PASS",
            "summary": {"p0_rollout_complete": False, "p1_p2_rollout_complete": True},
        },
        ("summary", "p0_rollout_complete", True),
        "rollout_report_signature_not_verified",
    ),
    "rollout_status": (
        "rollout",
        {
            "status": "BLOCKED",
            "summary": {"p0_rollout_complete": True, "p1_p2_rollout_complete": True},
        },
        ("status", None, "PASS"),
        "rollout_report_signature_not_verified",
    ),
    "runtime_apply_flag": (
        "runtime_apply",
        {
            "status": "PASS",
            "summary": {"runtime_update_allowed": False, "v2_default_applied_count": 34},
        },
        ("summary", "runtime_update_allowed", True),
        "runtime_apply_report_signature_not_verified",
    ),
    "runtime_apply_count": (
        "runtime_apply",
        {
            "status": "PASS",
            "summary": {"runtime_update_allowed": True, "v2_default_applied_count": 3},
        },
        ("summary", "v2_default_applied_count", 34),
        "runtime_apply_report_signature_not_verified",
    ),
    "smoke_case_count": (
        "post_apply_smoke",
        {"status": "PASS", "summary": {"case_count": 3, "pass_count": 34}},
        ("summary", "case_count", 34),
        "post_apply_smoke_report_signature_not_verified",
    ),
    "smoke_pass_count": (
        "post_apply_smoke",
        {"status": "PASS", "summary": {"case_count": 34, "pass_count": 3}},
        ("summary", "pass_count", 34),
        "post_apply_smoke_report_signature_not_verified",
    ),
    "manual_trial_flag": (
        "manual_trial",
        {"status": "PASS", "summary": {"manual_apply_trial_ready": False}},
        ("summary", "manual_apply_trial_ready", True),
        "manual_apply_trial_report_signature_not_verified",
    ),
    "m45_clean_count": (
        "m45_m52",
        {
            "summary": {"m45_clean_v2_receipt_count": 2, "m51_v2_ready_capability_count": 34},
            "m45_behavior_run_results": [{"blockers": []}],
        },
        ("summary", "m45_clean_v2_receipt_count", 102),
        "m45_m52_report_signature_not_verified",
    ),
    "m45_ready_count": (
        "m45_m52",
        {
            "summary": {"m45_clean_v2_receipt_count": 102, "m51_v2_ready_capability_count": 3},
            "m45_behavior_run_results": [{"blockers": []}],
        },
        ("summary", "m51_v2_ready_capability_count", 34),
        "m45_m52_report_signature_not_verified",
    ),
    "m45_blockers": (
        "m45_m52",
        {
            "summary": {"m45_clean_v2_receipt_count": 102, "m51_v2_ready_capability_count": 34},
            "m45_behavior_run_results": [{"blockers": ["semantic_not_verified"]}],
        },
        ("m45_behavior_run_results", None, [{"blockers": []}]),
        "m45_m52_report_signature_not_verified",
    ),
}


def test_3374_signed_failing_report_edited_to_pass_is_blocked() -> None:
    import json

    for case_id, (name, failing, (top, sub, value), reason) in _EDIT_CASES.items():
        chain = _chain()
        report = _failing_signed(name, failing)
        # the unedited signed failing report must not pass either
        chain[name] = report
        assert _run(chain)["status"] != "PASS", case_id
        # edit one read field to its passing value, keep the original signature
        edited = copy.deepcopy(report)
        if sub is None:
            edited[top] = value
        else:
            edited[top][sub] = value
        chain[name] = edited
        result = _run(chain)
        assert result["status"] == "BLOCKED", case_id
        assert reason in json.dumps(result), case_id
        # control: the same edit signed with the key does pass, so the edit alone is not the cause
        chain[name] = _failing_signed(
            name, {k: v for k, v in edited.items() if k != "report_signature"}
        )
        assert _run(chain)["status"] == "PASS", case_id


def test_3374_non_ascii_signature_is_a_plain_mismatch() -> None:
    chain = _chain()
    for name in chain:
        edited = copy.deepcopy(chain[name])
        edited["report_signature"]["signature"] = "café-✓"
        chain[name] = edited
        assert _run(chain)["status"] == "BLOCKED", name
        chain[name] = _chain()[name]
    receipt = build_runtime_signed_receipt(
        run_id="r",
        row_id="x",
        arm_id="a",
        capability_id="c",
        skill_id="s",
        artifact_hash="h",
        raw_observation={},
        secret=KEY,
    )
    assert verify_runtime_signed_receipt(receipt, secret=KEY) is True
    receipt["receipt_signature"] = "café-✓"
    assert verify_runtime_signed_receipt(receipt, secret=KEY) is False
