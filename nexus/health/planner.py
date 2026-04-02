from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


from nexus.core.state_contracts import NexusState
from .models import HealthDiagnosis, HealthTrigger, RepairAction, RepairPlan


class RepairPlanner:
    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.python = self.repo_root / ".venv" / "bin" / "python"

    def build_plan(self, diagnosis: HealthDiagnosis, state: Optional[NexusState] = None) -> RepairPlan:
        phase_route = self._route_for_diagnosis(diagnosis)
        phase_route = self._apply_lesson_route_bias(phase_route, diagnosis, state)
        actions: list[RepairAction] = []
        action = self._action_for_diagnosis(diagnosis)
        if action:
            actions.append(action)
        actions.extend(self._actions_for_route(phase_route, diagnosis))
        return RepairPlan(
            diagnosis=diagnosis,
            actions=self._dedupe(actions),
            phase_route=phase_route,
        )

    def build_policy_actions(self, triggers: list[HealthTrigger]) -> list[RepairAction]:
        actions: list[RepairAction] = []
        python = str(self.python)
        for trigger in triggers:
            if trigger.code == "phase_health_low":
                phase = (trigger.target_phase or "R").upper()
                actions.append(
                    RepairAction(
                        id=f"auto.repair.phase.{phase.lower()}",
                        description=f"Auto repair loop for degraded phase {phase}.",
                        run=f"nexus:runner --task repair_phase_{phase}",
                        priority="HIGH",
                        disposition="inject_only",
                        reason=trigger.reason,
                        verify_commands=[f"{python} scripts/nexus_cli.py nexus:benchmark --tasks 1 --output ci_benchmark_autorepair.csv"],
                        artifact_paths=["ci_benchmark_autorepair.csv"],
                    )
                )
            elif trigger.code == "pipeline_health_low":
                actions.append(
                    RepairAction(
                        id="auto.repair.pipeline",
                        description="Recover degraded pipeline health.",
                        run="nexus:runner --task repair_pipeline",
                        priority="HIGH",
                        disposition="inject_only",
                        reason=trigger.reason,
                        verify_commands=[f"{python} scripts/nexus_cli.py nexus:benchmark --tasks 1 --output ci_benchmark_autorepair.csv"],
                        artifact_paths=["ci_benchmark_autorepair.csv"],
                    )
                )
            elif trigger.code == "audit_regression_fail":
                actions.append(
                    RepairAction(
                        id="auto.repair.phase.a",
                        description="Force audit-repair loop because regression failed.",
                        run="nexus:runner --task repair_phase_A",
                        priority="HIGH",
                        disposition="inject_only",
                        reason=trigger.reason,
                        verify_commands=[f"{python} scripts/nexus_cli.py nexus:benchmark --tasks 1 --output ci_benchmark_autorepair.csv"],
                        artifact_paths=["ci_benchmark_autorepair.csv"],
                    )
                )
            elif trigger.code == "learning_velocity_stalled":
                actions.append(
                    RepairAction(
                        id="auto.optimize.learning",
                        description="Refresh learning telemetry and optimize trend signals.",
                        run=f"{python} scripts/ops/calc_learning_velocity.py && {python} scripts/ops/render_phase_sparkline.py --window 10",
                        priority="MEDIUM",
                        disposition="safe_execute",
                        reason=trigger.reason,
                        verify_commands=[f"{python} scripts/ops/calc_learning_velocity.py"],
                        artifact_paths=[".nexus/learning_velocity.json"],
                    )
                )
        return self._dedupe(actions)

    def _route_for_diagnosis(self, diagnosis: HealthDiagnosis) -> list[str]:
        route_map = {
            "healthy": [],
            "insufficient_signals": ["X", "D"],
            "research_failure": ["X", "D", "R", "A"],
            "repair_failure": ["D", "R", "A"],
            "audit_failure": ["R", "A", "D", "R", "A"],
            "evidence_failure": ["X", "R", "A", "C"],
            "environment_failure": ["P", "R", "A"],
        }
        route = list(route_map.get(diagnosis.kind, []))
        target_phase = (diagnosis.target_phase or "").upper()
        if target_phase and target_phase not in route:
            route.insert(0, target_phase)
        return route

    def _apply_lesson_route_bias(
        self,
        phase_route: list[str],
        diagnosis: HealthDiagnosis,
        state: Optional[NexusState],
    ) -> list[str]:
        if not state or not phase_route:
            return phase_route

        scores = {phase: 0.0 for phase in ["P", "X", "D", "R", "A", "C"]}
        prior_weights = state.metadata.get("self_heal_route_phase_weights")
        if isinstance(prior_weights, dict):
            for phase, weight in prior_weights.items():
                phase_name = str(phase).upper()
                if phase_name not in scores:
                    continue
                bounded = max(-40.0, min(40.0, float(weight or 0.0)))
                scores[phase_name] += bounded

        hits = state.metadata.get("fault_lesson_hits")
        if isinstance(hits, list):
            for hit in hits:
                if not isinstance(hit, dict):
                    continue
                relevance = float(hit.get("relevance", 0.0) or 0.0)
                content = hit.get("content") or {}
                if isinstance(content, dict):
                    text = " ".join(
                        str(content.get(key, "") or "")
                        for key in ("lesson", "repair_patch", "diagnosis_kind")
                    ).lower()
                else:
                    text = str(content).lower()
                if not text.strip():
                    continue
                self._accumulate_phase_scores(scores, text, relevance)

        if not any(abs(v) > 0.0 for v in scores.values()):
            return phase_route

        indexed_route = list(enumerate(phase_route))
        indexed_route.sort(key=lambda pair: (-scores.get(pair[1], 0.0), pair[0]))
        reordered = [phase for _, phase in indexed_route]

        if diagnosis.kind != "healthy":
            candidate = max(scores.items(), key=lambda item: item[1])
            if candidate[1] >= 45.0 and candidate[0] not in reordered:
                reordered.insert(0, candidate[0])

        state.metadata["self_heal_route_bias"] = {
            "scores": {k: round(v, 2) for k, v in scores.items() if v > 0},
            "route_before": list(phase_route),
            "route_after": list(reordered),
            "route_prior": {
                str(k).upper(): round(float(v), 2)
                for k, v in (prior_weights.items() if isinstance(prior_weights, dict) else [])
                if str(k).upper() in {"P", "X", "D", "R", "A", "C"}
            },
        }
        return reordered

    @staticmethod
    def _accumulate_phase_scores(scores: dict[str, float], text: str, relevance: float) -> None:
        weight = max(0.1, relevance) * 100.0
        keywords = {
            "P": ("repair_phase_p", "route.p", "phase p", "planner", "plan"),
            "X": ("repair_phase_x", "route.x", "phase x", "research", "signal"),
            "D": ("repair_phase_d", "route.d", "phase d", "diagnos", "root cause"),
            "R": ("repair_phase_r", "route.r", "phase r", "repair", "patch"),
            "A": ("repair_phase_a", "route.a", "phase a", "audit", "regression"),
            "C": ("repair_phase_c", "route.c", "phase c", "crystal", "lesson", "metabol"),
        }
        for phase, markers in keywords.items():
            hits = sum(1 for marker in markers if marker in text)
            if hits > 0:
                scores[phase] += weight * float(hits)

    def _actions_for_route(self, phase_route: list[str], diagnosis: HealthDiagnosis) -> list[RepairAction]:
        python = str(self.python)
        actions: list[RepairAction] = []
        for phase in phase_route:
            phase = phase.upper()
            if phase not in {"P", "X", "D", "R", "A", "C"}:
                continue
            actions.append(
                RepairAction(
                    id=f"auto.repair.route.{phase.lower()}",
                    description=f"Execute recovery route phase {phase}.",
                    run=f"nexus:runner --task repair_phase_{phase}",
                    priority="HIGH" if phase in {"R", "A", "D"} else "MEDIUM",
                    disposition="inject_only",
                    reason=f"route:{diagnosis.kind}",
                    verify_commands=[f"{python} scripts/nexus_cli.py nexus:benchmark --tasks 1 --output ci_benchmark_autorepair.csv"],
                    artifact_paths=["ci_benchmark_autorepair.csv"],
                )
            )
        return actions

    def _action_for_diagnosis(self, diagnosis: HealthDiagnosis) -> RepairAction | None:
        python = str(self.python)
        if diagnosis.kind == "healthy":
            return None
        if diagnosis.kind == "insufficient_signals":
            return None
        if diagnosis.kind == "evidence_failure":
            return RepairAction(
                id="auto.repair.evidence",
                description="Refresh benchmark evidence and token capture.",
                run=f'{python} scripts/nexus_cli.py nexus:benchmark --tasks 1 --output ci_benchmark_autorepair.csv',
                priority="HIGH",
                disposition="safe_execute",
                reason=diagnosis.summary,
                verify_commands=[f"{python} -m pytest tests/test_v9_regression_p1.py -q"],
                artifact_paths=["ci_benchmark_autorepair.csv"],
            )
        if diagnosis.kind == "environment_failure":
            return RepairAction(
                id="auto.repair.environment",
                description="Revalidate Nexus runtime environment and core regression lane.",
                run=f"{python} -m pytest tests/test_v9_regression_p1.py -q",
                priority="HIGH",
                disposition="safe_execute",
                reason=diagnosis.summary,
                verify_commands=[f"{python} -m pytest tests/test_v9_regression_p1.py -q"],
                artifact_paths=[],
            )

        phase = diagnosis.target_phase or "R"
        description = f"Plan a targeted repair task for phase {phase}."
        run = f"nexus:runner --task repair_phase_{phase}"
        return RepairAction(
            id=f"auto.repair.phase.{phase.lower()}",
            description=description,
            run=run,
            priority="HIGH" if diagnosis.kind in {"repair_failure", "audit_failure"} else "MEDIUM",
            disposition="inject_only",
            reason=diagnosis.summary,
            verify_commands=[f"{python} scripts/nexus_cli.py nexus:benchmark --tasks 1 --output ci_benchmark_autorepair.csv"],
            artifact_paths=["ci_benchmark_autorepair.csv"],
        )

    @staticmethod
    def _dedupe(actions: list[RepairAction]) -> list[RepairAction]:
        deduped: list[RepairAction] = []
        seen: set[str] = set()
        for action in actions:
            if action.id in seen:
                continue
            seen.add(action.id)
            deduped.append(action)
        return deduped
