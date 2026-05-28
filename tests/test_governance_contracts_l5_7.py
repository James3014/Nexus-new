"""
🛡️ Nexus L5.7 / v26.0 — 三類硬核回歸測試套件

覆蓋範圍：
1. Dashboard Downstream Boundary 回歸（L4）
2. Deterministic Rescue 因果完備性回歸（L2）
3. Wall-Ledger 殘差區分回歸（L4）
4. 偷渡阻斷單元測試（L2 + L4）
5. lane policy 與 winner 一致性驗證（L3）
"""

from __future__ import annotations

import pytest

from nexus.core.lane_capability_contract import LaneCapabilityContract
from nexus.core.receipt_causality_contract import ReceiptCausalityContract
from nexus.core.route_policy_evidence_contract import RoutePolicyEvidenceContract
from nexus.core.public_telemetry_boundary_contract import PublicTelemetryBoundaryContract


# ══════════════════════════════════════════════════════════════
# 共用 Fixtures
# ══════════════════════════════════════════════════════════════

@pytest.fixture
def l1() -> LaneCapabilityContract:
    return LaneCapabilityContract()


@pytest.fixture
def l2() -> ReceiptCausalityContract:
    return ReceiptCausalityContract()


@pytest.fixture
def l3() -> RoutePolicyEvidenceContract:
    return RoutePolicyEvidenceContract()


@pytest.fixture
def l4() -> PublicTelemetryBoundaryContract:
    return PublicTelemetryBoundaryContract()


@pytest.fixture
def clean_telemetry() -> dict:
    """符合所有 L4 gate 的最小有效遙測。"""
    return {
        "provider_token_completeness": 1.0,
        "wall_time_ms": 5000.0,
        "token_usage": 1200,
        "provider_costs": {"gemini": 0.0012},
        "overhead_ms": 200.0,
        "child_wall_times_ms": [4600.0],   # 殘差 = |5000 - (4600+200)| / 5000 = 4%
        "telemetry_source": "measured",
        "model_calls": 2,
    }


@pytest.fixture
def hardened_receipt() -> dict:
    """符合六大核心欄位的最小有效 receipt。"""
    return {
        "executor_id": "gemini-2.5-flash",
        "gate_passed": True,
        "invoked": True,
        "distinct_roles": ["LOGIC", "AUDIT"],
        "evidence_refs": ["mempalace_gate:ok", "claim_gate:ok"],
        "semantic_evidence_complete": True,
        "execution_source": "model",
    }


# ══════════════════════════════════════════════════════════════
# 1. L1: 路由准入契約
# ══════════════════════════════════════════════════════════════

class TestLaneCapabilityContract:
    def test_light_route_admitted_when_eligible(self, l1: LaneCapabilityContract):
        result = l1.admit(
            expected_capabilities=["mempalace", "belief"],
            executor_capabilities=["mempalace", "belief"],
            compact_mode=True,
            risk_level="LOW",
            impact_complexity=2.0,
        )
        assert result.lane == "light"
        assert result.status == "ADMITTED"
        assert "light_route_admission_granted" in result.reason_codes

    def test_hyper_route_when_high_risk(self, l1: LaneCapabilityContract):
        result = l1.admit(
            expected_capabilities=["mempalace", "belief"],
            executor_capabilities=["mempalace", "belief"],
            compact_mode=True,
            risk_level="HIGH",
            impact_complexity=2.0,
        )
        assert result.lane == "hyper"
        assert "light_route_ineligible_by_risk_or_complexity" in result.reason_codes

    def test_hyper_only_cap_forces_hyper_path(self, l1: LaneCapabilityContract):
        result = l1.admit(
            expected_capabilities=["mempalace", "ultra_review"],  # ultra_review = hyper-only
            executor_capabilities=["mempalace", "ultra_review"],
            compact_mode=True,
            risk_level="LOW",
            impact_complexity=1.0,
        )
        assert result.lane == "hyper"
        assert "hyper_only_capability_forces_full_path" in result.reason_codes

    def test_configured_but_blocked_is_not_active_rescue(self, l1: LaneCapabilityContract):
        """非白名單但非 HYPER_ONLY 的 cap 在 light route 中被過濾 → configured_but_blocked，非 active_rescue。"""
        # "codeintel" 不在 LIGHT_ROUTE_WHITELIST 也不在 HYPER_ONLY → 走到 Step3 whitelist 過濾
        result = l1.admit(
            expected_capabilities=["mempalace", "codeintel"],
            executor_capabilities=["mempalace", "codeintel"],
            compact_mode=True,
            risk_level="LOW",
            impact_complexity=1.5,
        )
        assert result.lane == "light"
        assert "codeintel" in result.blocked_capabilities
        assert result.is_active_rescue is False
        assert l1.is_configured_but_blocked(result) is True

    def test_active_rescue_when_all_caps_blocked(self, l1: LaneCapabilityContract):
        """所有 expected caps 均被阻斷 → active rescue 回退至 hyper。"""
        result = l1.admit(
            expected_capabilities=["ultra_review", "hyper_sprint"],  # both hyper-only
            executor_capabilities=[],
            compact_mode=True,
            risk_level="LOW",
            impact_complexity=1.0,
        )
        # ultra_review 是 hyper-only → 直接走 hyper path（hyper_only_capability_forces_full_path）
        assert result.lane == "hyper"


# ══════════════════════════════════════════════════════════════
# 2. L2: Receipt 因果完備性回歸
# ══════════════════════════════════════════════════════════════

class TestReceiptCausalityContract:
    def test_valid_receipt_passes(self, l2: ReceiptCausalityContract, hardened_receipt: dict):
        result = l2.validate_receipt(hardened_receipt)
        assert result.is_valid is True
        assert result.reason_code == "CAUSALITY_OK"

    def test_missing_executor_id_raises(self, l2: ReceiptCausalityContract, hardened_receipt: dict):
        bad = {k: v for k, v in hardened_receipt.items() if k != "executor_id"}
        with pytest.raises(ValueError, match="executor_id"):
            l2.validate_receipt(bad)

    def test_missing_semantic_evidence_complete_raises(self, l2: ReceiptCausalityContract, hardened_receipt: dict):
        bad = {k: v for k, v in hardened_receipt.items() if k != "semantic_evidence_complete"}
        with pytest.raises(ValueError, match="semantic_evidence_complete"):
            l2.validate_receipt(bad)

    def test_planner_only_smuggling_raises(self, l2: ReceiptCausalityContract, hardened_receipt: dict):
        """planner_only execution_source 嘗試偷渡 → ValueError。"""
        bad = {**hardened_receipt, "execution_source": "planner_only"}
        with pytest.raises(ValueError, match="Smuggling detected"):
            l2.validate_receipt(bad)

    def test_observation_only_smuggling_raises(self, l2: ReceiptCausalityContract, hardened_receipt: dict):
        bad = {**hardened_receipt, "execution_source": "observation_only"}
        with pytest.raises(ValueError, match="Smuggling detected"):
            l2.validate_receipt(bad)

    def test_backfill_complete_when_no_required_caps(self, l2: ReceiptCausalityContract, hardened_receipt: dict):
        result = l2.validate_backfill_completeness(
            receipts=[hardened_receipt],
            expected_capabilities=["autonomic_router"],  # 不在 backfill_required 集合中
        )
        assert result.is_valid is True
        assert result.reason_code == "BACKFILL_NOT_REQUIRED"

    def test_backfill_raises_when_gap_exists(self, l2: ReceiptCausalityContract, hardened_receipt: dict):
        """mempalace_gate 需要 backfill 但 receipt 中缺少 → ValueError。"""
        receipt_without_mempalace = {**hardened_receipt, "evidence_refs": ["claim_gate:ok"]}
        with pytest.raises(ValueError, match="backfill INCOMPLETE"):
            l2.validate_backfill_completeness(
                receipts=[receipt_without_mempalace],
                expected_capabilities=["mempalace_gate"],
            )

    def test_check_smuggling_raises_when_promoting_local_only(self, l2: ReceiptCausalityContract):
        with pytest.raises(ValueError, match="Smuggling BLOCKED"):
            l2.check_smuggling(execution_source="local_only", is_model_required_row=True)

    def test_check_smuggling_returns_observation_only_not_raise(self, l2: ReceiptCausalityContract):
        result = l2.check_smuggling(execution_source="local_only", is_model_required_row=False)
        assert result.is_valid is False
        assert result.reason_code == "OBSERVATION_ONLY"


# ══════════════════════════════════════════════════════════════
# 3. L3: Route Policy Evidence 一致性回歸
# ══════════════════════════════════════════════════════════════

class TestRoutePolicyEvidenceContract:
    def _make_admission_mock(self, lane="light", rescue=False, is_active_rescue=False, blocked=None):
        """建立最小 LaneAdmissionResult 模擬物件。"""
        from types import SimpleNamespace
        return SimpleNamespace(
            lane=lane,
            reason_codes=["expected_capability_protection", "light_route_admission_granted"],
            rescue_triggered=rescue,
            is_active_rescue=is_active_rescue,
            rescue_reason="all_expected_capabilities_blocked_from_light_route" if rescue else None,
            blocked_capabilities=blocked or [],
        )

    def test_evidence_eligible_for_clean_light_model(self, l3: RoutePolicyEvidenceContract):
        admission = self._make_admission_mock(lane="light")
        bundle = l3.serialize_route_evidence("task-test-01", admission, winner_source="model")
        assert bundle.is_public_audit_eligible is True
        assert bundle.policy_winner_consistent is True

    def test_evidence_blocked_when_reason_codes_empty(self, l3: RoutePolicyEvidenceContract):
        from types import SimpleNamespace
        admission = SimpleNamespace(
            lane="light",
            reason_codes=[],           # 空的 reason_codes → BLOCKED
            rescue_triggered=False,
            is_active_rescue=False,
            rescue_reason=None,
            blocked_capabilities=[],
        )
        bundle = l3.serialize_route_evidence("task-empty-rc", admission, winner_source="model")
        assert bundle.is_public_audit_eligible is False
        assert "EMPTY_REASON_CODES" in bundle.block_reason

    def test_evidence_blocked_when_policy_winner_inconsistent(self, l3: RoutePolicyEvidenceContract):
        admission = self._make_admission_mock(lane="light")
        # light lane + deterministic_local + no rescue reason code → inconsistent
        bundle = l3.serialize_route_evidence("task-incon", admission, winner_source="deterministic_local")
        assert bundle.is_public_audit_eligible is False
        assert "POLICY_WINNER_INCONSISTENT" in bundle.block_reason

    def test_rescue_guard_required_when_rescue_triggered(self, l3: RoutePolicyEvidenceContract):
        admission = self._make_admission_mock(lane="hyper", rescue=True, is_active_rescue=True)
        bundle = l3.serialize_route_evidence("task-rescue", admission, winner_source="model")
        assert bundle.rescue_guard is not None
        assert bundle.rescue_guard["rescue_reason"] != "unspecified"

    def test_blocked_lane_always_inconsistent(self, l3: RoutePolicyEvidenceContract):
        result = l3._check_policy_winner_consistency(
            lane="blocked", winner_source="model", reason_codes=[], rescue_triggered=False
        )
        assert result is False


# ══════════════════════════════════════════════════════════════
# 4. L4: Public Telemetry Boundary 回歸（含 Dashboard 防線）
# ══════════════════════════════════════════════════════════════

class TestPublicTelemetryBoundaryContract:
    def test_clean_telemetry_passes(self, l4: PublicTelemetryBoundaryContract, clean_telemetry: dict):
        result = l4.evaluate_promotion_boundary(clean_telemetry)
        assert result.promotion_status == "SOURCE_PROMOTION_READY"
        assert result.is_public_claim_safe is False   # 永遠 False（由下游決定）

    def test_incomplete_provider_token_blocked(self, l4: PublicTelemetryBoundaryContract, clean_telemetry: dict):
        bad = {**clean_telemetry, "provider_token_completeness": 0.85}
        result = l4.evaluate_promotion_boundary(bad)
        assert result.promotion_status == "BLOCKED"
        assert any("PROVIDER_TOKEN_INCOMPLETE" in f for f in result.block_flags)

    def test_observation_only_source_blocked(self, l4: PublicTelemetryBoundaryContract, clean_telemetry: dict):
        bad = {**clean_telemetry, "telemetry_source": "shadow"}
        result = l4.evaluate_promotion_boundary(bad)
        assert result.promotion_status == "BLOCKED"
        assert any("OBSERVATION_ONLY" in f for f in result.block_flags)

    def test_public_claim_safe_true_raises(self, l4: PublicTelemetryBoundaryContract, clean_telemetry: dict):
        """嘗試將 public_claim_safe=True 傳入 → ValueError（硬性物理阻隔）。"""
        bad = {**clean_telemetry, "public_claim_safe": True}
        with pytest.raises(ValueError, match="public_claim_safe=True is FORBIDDEN"):
            l4.evaluate_promotion_boundary(bad)

    def test_wall_ledger_residual_exceeds_tolerance(self, l4: PublicTelemetryBoundaryContract, clean_telemetry: dict):
        """殘差 > 5% → BLOCKED。"""
        bad = {**clean_telemetry, "child_wall_times_ms": [1000.0]}  # 殘差 = |5000-(1000+200)|/5000 = 76%
        result = l4.evaluate_promotion_boundary(bad)
        assert result.promotion_status == "BLOCKED"
        assert any("WALL_LEDGER_RESIDUAL_EXCEEDS_TOLERANCE" in f for f in result.block_flags)

    def test_infra_invalid_flag_blocked(self, l4: PublicTelemetryBoundaryContract, clean_telemetry: dict):
        bad = {**clean_telemetry, "has_infra_invalid": True}
        result = l4.evaluate_promotion_boundary(bad)
        assert result.promotion_status == "BLOCKED"
        assert "INFRA_INVALID_FLAG_SET" in result.block_flags

    def test_downstream_bypass_blocked_on_shadow_source(self, l4: PublicTelemetryBoundaryContract):
        """Dashboard 下游 bundle 含 shadow telemetry_sources → ValueError（防線）。"""
        bundle = {"telemetry_sources": ["shadow", "measured"], "public_claim_safe": False}
        with pytest.raises(ValueError, match="observation-only"):
            l4.assert_downstream_cannot_bypass(bundle)

    def test_downstream_bypass_blocked_on_public_claim_true(self, l4: PublicTelemetryBoundaryContract):
        bundle = {"telemetry_sources": ["measured"], "public_claim_safe": True}
        with pytest.raises(ValueError, match="boundary violation"):
            l4.assert_downstream_cannot_bypass(bundle)

    def test_wall_ledger_classify_included_in_parent(self, l4: PublicTelemetryBoundaryContract):
        entry = {"telemetry_source": "included_in_parent", "wall_time_ms": 0}
        assert l4.classify_wall_ledger_entry(entry) == "included_in_parent"

    def test_wall_ledger_classify_zero_fill(self, l4: PublicTelemetryBoundaryContract):
        entry = {"telemetry_source": "measured", "wall_time_ms": 0}
        assert l4.classify_wall_ledger_entry(entry) == "zero_fill"

    def test_wall_ledger_classify_measured(self, l4: PublicTelemetryBoundaryContract, clean_telemetry: dict):
        entry = {"telemetry_source": "measured", "wall_time_ms": 3200.0}
        assert l4.classify_wall_ledger_entry(entry) == "measured"
