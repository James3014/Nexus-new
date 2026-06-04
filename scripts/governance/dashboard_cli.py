import sys
import os
from nexus.governance.domain.blocker_taxonomy import BlockerCode
from nexus.observability.domain.heatmap_builder import HeatmapSeriesBuilder
from nexus.observability.application.dashboard_view_model import DashboardAssembler, ReplayAuditRow
from nexus.evaluation.governance.metrics_collector import GovernanceMetricsReport
from nexus.observability.application.canary_view_model import CanaryPanelAssembler
from nexus.rollout.canary_guard import CanaryGuard

def render_dashboard():
    # 1. 模擬觀測數據
    events = [
        {"time": "06-01", "blocker": BlockerCode.SCHEMA_MISMATCH},
        {"time": "06-02", "blocker": BlockerCode.DRIFT_DETECTED},
        {"time": "06-02", "blocker": BlockerCode.DRIFT_DETECTED},
        {"time": "06-03", "blocker": BlockerCode.EVIDENCE_MISSING},
        {"time": "06-03", "blocker": BlockerCode.BASELINE_REGRESSION},
        {"time": "06-03", "blocker": BlockerCode.BASELINE_REGRESSION},
        {"time": "06-03", "blocker": BlockerCode.BASELINE_REGRESSION},
    ]
    
    metrics = GovernanceMetricsReport(
        timestamp="2026-06-03T10:00:00Z", manifest_pass_rate=0.98, promotion_success_rate=0.92,
        seal_integrity_rate=1.0, drift_incident_count=2, mean_time_to_convergence_ms=45000
    )
    heatmap = HeatmapSeriesBuilder.build_matrix(events)
    replay_logs = [
        ReplayAuditRow("R-abc12345", "APPROVED", "APPROVED", True),
        ReplayAuditRow("R-def67890", "REJECTED", "REJECTED", True),
        ReplayAuditRow("R-xyz99999", "APPROVED", "REJECTED", False),
    ]
    
    # Canary 狀態
    guard = CanaryGuard()
    if "NEXUS_GOVERNANCE_MODE" in os.environ:
        del os.environ["NEXUS_GOVERNANCE_MODE"]
    canary_vm = CanaryPanelAssembler.assemble(guard, rollout_fraction=0.15, recent_blocker_code=BlockerCode.BASELINE_REGRESSION)
    
    # 2. 組裝 ViewModel
    vm = DashboardAssembler.assemble(metrics, heatmap, replay_logs)
    
    # 3. 終端機渲染
    print("=" * 60)
    print(f" 🛡️  NEXUS GOVERNANCE DASHBOARD ({vm.version})")
    print("=" * 60)
    
    # --- [CANARY PANEL] ---
    print(f" 🐥 [CANARY POLICY] Mode: {canary_vm.mode} | Rollout: {canary_vm.rollout_percent}")
    c_icon = "🔴" if canary_vm.health_status == "CRITICAL" else "🟡" if canary_vm.health_status == "DEGRADED" else "🟢"
    print(f"    Health: {c_icon} {canary_vm.health_status}")
    print(f"    Latest Blocker: {canary_vm.latest_blocker}")
    print("-" * 60)
    
    # --- [KPI OVERVIEW] ---
    print(" 📊 [KPI OVERVIEW]")
    for card in vm.kpi_cards:
        status_icon = "🟢" if card.status == "HEALTHY" else "🔴" if card.status == "CRITICAL" else "🟡"
        print(f"    {status_icon} {card.title.ljust(20)} : {card.value}")
        
    print("-" * 60)
    
    # --- [BLOCKER HEATMAP] ---
    print(" 🌡️  [BLOCKER HEATMAP (Density)]")
    matrix_render = {y: {x: 0 for x in heatmap.x_axis_labels} for y in heatmap.y_axis_labels}
    for point in heatmap.data_points:
        matrix_render[point["y"]][point["x"]] = point["value"]
        
    header = " " * 22 + " ".join(f"{x:>6}" for x in heatmap.x_axis_labels)
    print(header)
    
    for y_label in heatmap.y_axis_labels:
        row_str = f"    {y_label[:18].ljust(18)} "
        for x_label in heatmap.x_axis_labels:
            val = matrix_render[y_label][x_label]
            icon = " .  " if val == 0 else f" {val:02d} " if val < 3 else f"*{val:02d}*"
            row_str += f"{icon}   "
        print(row_str)

    print("-" * 60)
    
    # --- [REPLAY AUDIT] ---
    print(" 🔄 [REPLAY AUDIT LOG]")
    print(f"    {'RECEIPT ID':<12} | {'ORIGINAL':<10} | {'REPLAY':<10} | {'MATCH'}")
    print("    " + "-"*45)
    for row in replay_logs:
        match_str = "✅" if row.matched else "❌"
        print(f"    {row.receipt_id:<12} | {row.original_verdict:<10} | {row.replay_verdict:<10} | {match_str}")
        
    print("=" * 60)

if __name__ == "__main__":
    render_dashboard()
