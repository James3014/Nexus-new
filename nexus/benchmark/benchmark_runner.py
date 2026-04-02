from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import time
import logging

from nexus.benchmark.workspace import BenchmarkWorkspace
from nexus.benchmark.csv_reporter import BenchmarkCsvReporter

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    def __init__(
        self,
        project_root: Path,
        run_dir: Path,
        reporter,
        fast_mode: bool,
        audit_level: str,
    ):
        self.project_root = project_root
        self.run_dir = run_dir
        self.reporter = reporter
        self.fast_mode = fast_mode
        self.audit_level = audit_level

    def _voice_notify(self, message: str, urgency: str = "normal"):
        self.reporter.voice_notify(message, urgency=urgency)

    def run(
        self,
        framework: str,
        task_count: int = 10,
        output_csv: str = "nexus_benchmark.csv",
        model: str = None,
        target: str = None,
        dry_run: bool = False,
    ):
        logger.info(
            "[Nexus:Benchmark] Initializing real-world benchmark run for %s", framework
        )
        original_silent = self.reporter.silent
        if framework == "health-audit":
            self.reporter.silent = True
            self._voice_notify("啟動健康度自動審計...", urgency="critical")
        else:
            self._voice_notify(f"開始執行 {framework} 真實基準測試", urgency="critical")

        catalog_path = self.project_root / "cases" / "catalog.json"
        if not catalog_path.exists():
            logger.error("❌ Benchmark catalog not found!")
            self.reporter.silent = original_silent
            return []

        catalog = json.loads(catalog_path.read_text())
        cases_to_run = catalog["cases"][:task_count]

        results = []

        for case in cases_to_run:
            res = self._run_single_case(case)
            if res:
                results.append(res)

        # 輸出 CSV
        if results:
            csv_reporter = BenchmarkCsvReporter(output_csv)
            csv_reporter.write_results(results)

        self.reporter.silent = original_silent
        return results

    def _run_single_case(self, case: dict):
        case_id = case["id"]
        case_type = case["type"]
        relative_case_file = case["file"]
        case_file_path = self.project_root / "cases" / relative_case_file

        if not case_file_path.exists():
            logger.warning("⚠️ Case file %s missing, skipping.", relative_case_file)
            return None

        case_data = json.loads(case_file_path.read_text())
        goal_desc = case_data.get("goal", "")
        logger.info("🚀 [Benchmark] Running Case: %s", case_id)

        benchmark_workspace = BenchmarkWorkspace(
            self.project_root, case_id, self.run_dir / case_id
        )
        workspace_root = benchmark_workspace.create()
        applied_fixture = None
        try:
            # Check if this method exists, otherwise use internal fallback
            if hasattr(benchmark_workspace, "apply_fixture"):
                applied_fixture = benchmark_workspace.apply_fixture(case_data)
            else:
                applied_fixture = self._apply_benchmark_fixture(case_data)
        except Exception as exc:
            logger.error(
                "💥 [Benchmark] Fixture setup failed for %s: %s", case_id, exc
            )
            benchmark_workspace.cleanup()
            return self._build_fail_result(case_id, "fixture_error")

        # 建立子任務隔離目錄
        case_run_dir = self.run_dir / case_id
        case_run_dir.mkdir(parents=True, exist_ok=True)

        from nexus.containers import NexusContainer

        container = NexusContainer()
        container.project_root.from_value(str(workspace_root))
        container.run_dir.from_value(str(case_run_dir))

        sub_engine = container.engine_factory(
            silent=True, fast_mode=self.fast_mode, audit_level=self.audit_level
        )

        start_time = time.time()
        success = False
        try:
            success = self._execute_isolated_case(
                sub_engine,
                case_type=case_type,
                case_id=case_id,
                goal_desc=goal_desc,
                case_data=case_data,
            )
        except Exception as e:
            logger.error("💥 [Benchmark] Case %s crashed: %s", case_id, e)

        duration = time.time() - start_time
        
        if hasattr(benchmark_workspace, "restore_fixture"):
            benchmark_workspace.restore_fixture(applied_fixture)
        else:
            self._restore_benchmark_fixture(applied_fixture)
            
        benchmark_workspace.cleanup()

        final_state = sub_engine.state_io.load_global_state()
        return self._collect_case_metrics(case_id, success, duration, final_state)

    def _collect_case_metrics(self, case_id, success, duration, final_state):
        """採集並標準化 Case 執行指標。"""
        # 1. 提取各階段健康度與信號狀態 (R8-4 Step 1)
        health_info = self._extract_phase_health_info(final_state)
        
        # 2. 判定最終狀態與幻覺偵測 (R8-4 Step 2)
        outcome_info = self._determine_outcome_info(final_state, success)

        # 3. 組裝最終結果字典 (R8-4 Step 3)
        res = self._assemble_benchmark_dict(
            case_id, duration, final_state, health_info, outcome_info
        )

        logger.info(
            "🏁 [Benchmark] Case %s: %s (Tokens: %d, ph_min: %.1f, v: %.2f)",
            case_id, res["status"], res["tokens"],
            res["lowest_phase_health"], res["learning_velocity"],
        )
        return res

    def _extract_phase_health_info(self, state: Any) -> Dict[str, Any]:
        """從全域狀態萃取各階段的健康度數據。"""
        metrics = state.phase_metrics
        phases = ["P", "X", "D", "R", "A", "C"]
        
        health_map = {p: (metrics.get(p).health if metrics.get(p) else 0.0) for p in phases}
        signal_status = {
            p: ("measured" if metrics.get(p) and bool(metrics.get(p).signals) else "missing")
            for p in phases
        }
        
        valid_healths = [m.health for m in metrics.values() if m.health > 0]
        lowest_ph = min(valid_healths) if valid_healths else 0.0
        
        return {
            "health_map": health_map,
            "signal_status": signal_status,
            "lowest_ph": lowest_ph
        }

    def _determine_outcome_info(self, state: Any, success: bool) -> Dict[str, Any]:
        """判定任務結果標籤。"""
        outcome = state.metadata.get("pipeline_outcome", {})
        terminal_state = outcome.get("terminal_state", "SUCCESS" if success else "FAILED")
        phantom_detected = bool(state.metadata.get("phantom_success_reason"))
        exit_code = outcome.get("exit_code", 0 if success else 1)
        
        return {
            "terminal_state": terminal_state,
            "phantom_detected": phantom_detected,
            "exit_code": exit_code,
            "pregate_skip": outcome.get("pregate_skip", False)
        }

    def _assemble_benchmark_dict(self, case_id, duration, state, health_info, outcome_info) -> Dict[str, Any]:
        """將所有分散指標匯總為扁平的 CSV 相容字典。"""
        h_map = health_info["health_map"]
        s_status = health_info["signal_status"]
        
        return {
            "task_id": case_id,
            "status": outcome_info["terminal_state"],
            "exit_code": outcome_info["exit_code"],
            "pregate_skip": outcome_info["pregate_skip"],
            "phantom_detected": outcome_info["phantom_detected"],
            "tokens": state.total_token_usage,
            "token_raw_model": state.token_raw_model,
            "token_fallback_est": state.token_fallback_est,
            "token_system_overhead": state.token_system_overhead,
            "token_source_x": state.phase_tokens.get("X", 0),
            "token_source_r": state.phase_tokens.get("R", 0),
            "token_capture_status": state.token_capture_status,
            "phase_path": " -> ".join([h.phase for h in state.steps_history]),
            "review_status": state.metadata.get("last_review_status", "UNKNOWN"),
            "duration": round(duration, 2),
            "health": state.health_score,
            "drift": state.health_metrics.drift_index,
            "lowest_phase_health": health_info["lowest_ph"],
            "phase_health_p": h_map["P"] if s_status["P"] == "measured" else "",
            "phase_health_x": h_map["X"] if s_status["X"] == "measured" else "",
            "phase_health_d": h_map["D"] if s_status["D"] == "measured" else "",
            "phase_health_r": h_map["R"] if s_status["R"] == "measured" else "",
            "phase_health_a": h_map["A"] if s_status["A"] == "measured" else "",
            "phase_health_c": h_map["C"] if s_status["C"] == "measured" else "",
            "phase_signal_status_p": s_status["P"],
            "phase_signal_status_x": s_status["X"],
            "phase_signal_status_d": s_status["D"],
            "phase_signal_status_r": s_status["R"],
            "phase_signal_status_a": s_status["A"],
            "phase_signal_status_c": s_status["C"],
            "policy_hit": ",".join(state.policy_hit_ids),
            "learning_velocity": state.learning_velocity,
        }

    def _build_fail_result(self, case_id: str, reason: str):
        return {
            "task_id": case_id,
            "status": "FAIL",
            "tokens": 0,
            "token_raw_model": 0,
            "token_fallback_est": 0,
            "token_system_overhead": 0,
            "token_source_x": 0,
            "token_source_r": 0,
            "token_capture_status": reason,
            "phase_path": "",
            "review_status": "UNKNOWN",
            "duration": 0.0,
            "health": 0.0,
            "drift": 0.0,
            "lowest_phase_health": 0.0,
            "policy_hit": "",
            "learning_velocity": 0.0,
        }

    def _execute_isolated_case(
        self,
        sub_engine,
        *,
        case_type: str,
        case_id: str,
        goal_desc: str,
        case_data: dict,
    ) -> bool:
        import importlib

        app_module = importlib.import_module("nexus.app.command_service")
        service = app_module.NexusCommandService(sub_engine)
        if case_type == "bug":
            return service.execute_bug(
                goal_desc,
                delivery_mode="standard",
                bug_id=case_id,
                execution_context={
                    "auto_repair_enabled": False,
                    "benchmark_run": True,
                    "benchmark_force_research": True,
                    "benchmark_target_files": case_data.get("initial_state", {}).get(
                        "files", []
                    ),
                },
            )
        return service.execute_feature(
            goal_desc,
            delivery_mode="standard",
            execution_context={
                "auto_repair_enabled": False,
                "benchmark_run": True,
                "benchmark_force_research": True,
                "benchmark_target_files": case_data.get("initial_state", {}).get(
                    "files", []
                ),
            },
        )

    def _apply_benchmark_fixture(self, case_data: dict) -> Optional[Dict[str, Any]]:
        fixture = case_data.get("benchmark_fixture")
        if not fixture:
            return None

        relative_file = fixture.get("file")
        target_text = fixture.get("target")
        replacement_text = fixture.get("replacement", "")
        if not relative_file or target_text is None:
            raise ValueError("benchmark_fixture requires file and target")

        file_path = self.project_root / relative_file
        original_text = file_path.read_text(encoding="utf-8")
        if target_text not in original_text:
            raise ValueError(f"benchmark fixture target not found in {relative_file}")

        mutated_text = original_text.replace(target_text, replacement_text, 1)
        file_path.write_text(mutated_text, encoding="utf-8")
        return {
            "file": file_path,
            "relative_file": relative_file,
            "original_text": original_text,
        }

    def _restore_benchmark_fixture(
        self, applied_fixture: Optional[Dict[str, Any]]
    ) -> None:
        if not applied_fixture:
            return

        file_path = Path(applied_fixture["file"])
        original_text = applied_fixture["original_text"]
        file_path.write_text(original_text, encoding="utf-8")
