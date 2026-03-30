import csv
import logging

logger = logging.getLogger(__name__)

class BenchmarkCsvReporter:
    def __init__(self, output_csv: str):
        self.output_csv = output_csv
        self.fieldnames = [
            "task_id",
            "status",
            "exit_code",
            "pregate_skip",
            "phantom_detected",
            "tokens",
            "token_raw_model",
            "token_fallback_est",
            "token_system_overhead",
            "token_source_x",
            "token_source_r",
            "token_capture_status",
            "phase_path",
            "review_status",
            "duration",
            "health",
            "drift",
            "lowest_phase_health",
            "phase_health_p",
            "phase_health_x",
            "phase_health_d",
            "phase_health_r",
            "phase_health_a",
            "phase_health_c",
            "phase_signal_status_p",
            "phase_signal_status_x",
            "phase_signal_status_d",
            "phase_signal_status_r",
            "phase_signal_status_a",
            "phase_signal_status_c",
            "policy_hit",
            "learning_velocity",
        ]

    def write_results(self, results: list):
        if not results:
            return

        with open(self.output_csv, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=self.fieldnames)
            writer.writeheader()
            for r in results:
                writer.writerow(r)
        logger.info("💾 [Benchmark] Results saved to %s", self.output_csv)
