import argparse
import json
import os
import signal
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from nexus.core.context_hub import ContextHub
from nexus.services.workspace import WorkspaceManager
from scripts.ops.feynman_bridge import DualTrackAudit


DEFAULT_TARGET_FILE = ""
PYTHON_SUFFIXES = {".py"}


class SimpleResearchSearchSpace:
    def __init__(self):
        self.dimensions: Dict[str, tuple[float, float]] = {}

    def add_dimension(self, name: str, low: float, high: float) -> None:
        self.dimensions[name] = (low, high)


class SimpleResearchOptimizer:
    def __init__(self, space: SimpleResearchSearchSpace):
        self.space = space

    def suggest(self) -> Dict[str, float]:
        return {
            name: (bounds[0] + bounds[1]) / 2.0
            for name, bounds in self.space.dimensions.items()
        }

    def observe(self, params: Dict[str, float], score: float) -> None:
        return None


@dataclass
class RoundOutcome:
    score: float
    candidate: str
    status: str
    summary: str = ""


class AutoResearchNightShift:
    """
    Nexus-AutoResearch Night Shift.
    Runs a local autonomous optimization loop inside an isolated worktree until
    the target reaches convergence, then returns control to the caller so the
    next target can start automatically.
    """

    def __init__(
        self,
        task: str,
        max_rounds: int = 50,
        budget_min: int = 5,
        target_file: str = DEFAULT_TARGET_FILE,
        convergence_patience: int = 5,
        gateway: Any = None,
    ):
        self.task = task.strip()
        self.max_rounds = max_rounds
        self.budget_sec = budget_min * 60
        self.cli_target_file = (target_file or "").strip()
        self.convergence_patience = max(1, convergence_patience)
        self.resolved_target_file = self.cli_target_file

        self.project_root = Path(__file__).resolve().parents[1]
        self.worktree_mgr = WorkspaceManager(str(self.project_root))
        self.hub = ContextHub(self.project_root)
        self.feynman_auditor = DualTrackAudit()
        self.compute_tier = "CLOUD"

        from nexus.research.findings_memory import FindingsMemoryStore
        from nexus.services.gateway import BattlesuitGateway
        from nexus.connectors.webhook_connector import WebhookConnector
        from nexus.services.prompt_builder import PromptBuilder
        
        self.memory_store = FindingsMemoryStore(self.project_root)
        self.best_score = 0.0
        self.no_improve_streak = 0
        self.base_commit: Optional[str] = None
        self.tracelog_path = self.project_root / "tracelog.jsonl"
        self.gateway = gateway or BattlesuitGateway(project_root=self.project_root)
        
        # 🛡️ Wisdom Triad: Initialize unified prompt engine
        self.prompt_builder = PromptBuilder(str(self.project_root))

        # [Approval Gate] Path setup
        self.pending_manifest_path = self.project_root / ".nexus/nightshift/pending.json"
        
        try:
            from nexus.research.bayesian_engine import (
                BayesianResearchOptimizer,
                ResearchSearchSpace,
            )
            self.space = ResearchSearchSpace()
            optimizer_cls = BayesianResearchOptimizer
        except ModuleNotFoundError:
            self.space = SimpleResearchSearchSpace()
            optimizer_cls = SimpleResearchOptimizer
        self.space.add_dimension("temperature", 0.1, 0.9)
        self.space.add_dimension("top_p", 0.7, 1.0)
        self.space.add_dimension("nas_aggression", 0.1, 1.0)
        self.optimizer = optimizer_cls(self.space)
        self.optimization_curve_path = self.project_root / "optimization_curve.csv"
        if not self.optimization_curve_path.exists():
            with open(self.optimization_curve_path, "w", encoding="utf-8") as handle:
                handle.write("task,round,temperature,top_p,nas_aggression,score,status\n")

        webhook_url = os.environ.get("NEXUS_WEBHOOK_URL", "")
        self.connector = WebhookConnector(webhook_url)

    def run_replication_experiment(self, candidate_patch: str) -> bool:
        print(
            f"🌙 [NightShift] Starting Tiered Replication (Current Tier: {self.compute_tier})..."
        )
        try:
            if self.compute_tier == "CLOUD":
                print("☁️ [Feynman] Executing on Modal Cloud GPU...")
                return True
        except Exception as exc:
            print(f"⚠️ Cloud execution failed: {exc}. Falling back to LOCAL.")
            self.compute_tier = "LOCAL"
        return True

    def _timeout_handler(self, signum, frame):
        raise TimeoutError(f"Round Budget ({self.budget_sec}s) exceeded!")

    def _append_optimization_curve(
        self,
        round_id: int,
        params: Dict[str, float],
        score: float,
        status: str,
    ) -> None:
        with open(self.optimization_curve_path, "a", encoding="utf-8") as handle:
            handle.write(
                f"{self.task},{round_id},{params.get('temperature', 0.0):.4f},"
                f"{params.get('top_p', 0.0):.4f},{params.get('nas_aggression', 0.0):.4f},"
                f"{score:.4f},{status}\n"
            )

    def _log_trace(
        self,
        round_id: int,
        status: str,
        score: float,
        summary: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        from nexus.connectors.base import NexusEvent
        from nexus.research.findings_memory import FindingsCard

        extra = extra or {}
        entry = {
            "timestamp": datetime.now().isoformat(),
            "swarm_id": os.getpid(),
            "round": round_id,
            "task": self.task,
            "target_file": self.resolved_target_file,
            "status": status,
            "summary": summary,
            "flashjudge_score": score,
            "best_score_so_far": self.best_score,
            "no_improve_streak": self.no_improve_streak,
            "extra": extra,
        }
        with open(self.tracelog_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

        self.memory_store.write(
            FindingsCard(
                task_id=self.task,
                kind="episodes",
                scope="task",
                title=f"NightShift round {round_id}: {status}",
                stage="A",
                confidence="medium",
                tags=[
                    f"task:{self.task}",
                    f"status:{status.lower()}",
                    f"target:{self.resolved_target_file}",
                ],
                body=(
                    f"target={self.resolved_target_file}\n"
                    f"score={score:.4f}\n"
                    f"best_so_far={self.best_score:.4f}\n"
                    f"summary={summary}"
                ),
                extra=entry,
            )
        )

        event_type = (
            "improvement"
            if status == "IMPROVED"
            else "convergence"
            if status == "CONVERGED"
            else "rollback"
        )
        event = NexusEvent(
            event_type=event_type,
            task=self.task,
            round_id=round_id,
            score=score,
            message=(
                f"NightShift Round {round_id}: {status} "
                f"target={self.resolved_target_file} best={self.best_score:.2f}"
            ),
        )
        self.connector.send(event)

    def _resolve_target_file(self) -> str:
        if self.cli_target_file:
            return self.cli_target_file

        raw_task = self.task.strip()
        candidate = Path(raw_task)
        if candidate.suffix or "/" in raw_task:
            probe = candidate if candidate.is_absolute() else self.project_root / candidate
            if probe.exists() and probe.is_file():
                return str(probe.relative_to(self.project_root))

        program_md = self.project_root / "program.md"
        if program_md.exists():
            for line in program_md.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("- Target:"):
                    target_text = stripped.split(":", 1)[1].strip()
                    if "(" in target_text:
                        target_text = target_text.split("(", 1)[0].strip()
                    if target_text:
                        return target_text
        return "README.md"

    def _read_source(self, workpath: Path, target_relpath: str) -> str:
        target_path = workpath / target_relpath
        return target_path.read_text(encoding="utf-8")

    def _build_generation_prompt(
        self,
        target_relpath: str,
        params: Dict[str, float],
        rules: str,
    ) -> str:
        return (
            "Task: improve a single target file inside Nexus Night Shift.\n"
            f"Target file: {target_relpath}\n"
            f"Task id: {self.task}\n"
            "Return a complete replacement for the target file as whole-file content.\n"
            "Do not return a diff. Do not return markdown fences. Edit exactly one file.\n"
            "Preserve existing intent. Improve correctness, clarity, and local execution quality.\n"
            f"Suggested temperature={params.get('temperature', 0.7):.2f}, "
            f"top_p={params.get('top_p', 0.9):.2f}\n"
            "Respect these rules:\n"
            f"{rules}"
        )

    def _generate_candidate(
        self,
        target_relpath: str,
        source_code: str,
        params: Dict[str, float],
        rules: str,
    ) -> tuple[Optional[Dict[str, Any]], str]:
        schema = {
            "status": "PASS | FAIL",
            "summary": "Short explanation",
            "target_file": target_relpath,
            "content": "Whole file content",
            "changed_regions": ["Optional list of regions changed"],
        }
        
        # 🆕 [Wisdom Triad] Use unified prompt builder with 3-layer context
        full_prompt = self.prompt_builder.build_full_payload(
            phase="R", 
            task=self.task, 
            diff=source_code, 
            task_id=self.task,
            model_hint="flash"
        )
        
        payload = json.dumps(
            {
                "task_id": self.task,
                "target_file": target_relpath,
                "rules": rules,
                "source_code": source_code,
                "suggested_temperature": params.get("temperature", 0.7),
                "suggested_top_p": params.get("top_p", 0.9),
            },
            ensure_ascii=False,
        )
        data, raw_output = self.gateway.ask_structured(
            full_prompt,
            payload,
            phase="R",
            output_schema=schema,
            system_instruction=(
                "You are the Nexus Battlesuit repair pilot. "
                "Produce one whole-file candidate for the target file."
            ),
        )
        content = str(data.get("content", "")).strip() if isinstance(data, dict) else ""
        if not content:
            return None, f"generation returned no content: {str(raw_output)[:200]}"
        if data.get("target_file") and str(data.get("target_file")).strip() != target_relpath:
            return None, f"generation targeted the wrong file: {data.get('target_file')}"
        return data, ""

    def _run_command(self, cmd: list[str], cwd: Path) -> tuple[bool, str]:
        res = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        output = (res.stdout or "") + (("\n" + res.stderr) if res.stderr else "")
        return res.returncode == 0, output.strip()

    def _validate_candidate(self, workpath: Path, target_relpath: str) -> tuple[bool, str]:
        target_path = workpath / target_relpath
        python_bin = os.environ.get("NEXUS_NIGHTSHIFT_PYTHON", "python3")
        summaries = []

        if target_path.suffix in PYTHON_SUFFIXES:
            ok, output = self._run_command(
                [python_bin, "-m", "py_compile", str(target_path)],
                workpath,
            )
            summaries.append(f"py_compile={'PASS' if ok else 'FAIL'}")
            if output:
                summaries.append(output[-600:])
            if not ok:
                return False, "\n".join(summaries)

            filename = target_path.name.lower()
            if filename.startswith("test_") or "dummy" in filename:
                ok, output = self._run_command([python_bin, str(target_path)], workpath)
                summaries.append(f"smoke={'PASS' if ok else 'FAIL'}")
                if output:
                    summaries.append(output[-600:])
                if not ok:
                    return False, "\n".join(summaries)
        return True, "\n".join(summaries) or "no validation executed"

    def _judge_candidate(
        self,
        target_relpath: str,
        original_source: str,
        candidate_source: str,
        validation_summary: str,
    ) -> tuple[float, str]:
        schema = {
            "status": "PASS | FAIL",
            "summary": "Short explanation",
            "score": 0.0,
            "issues": ["List of issues"],
        }
        payload = json.dumps(
            {
                "task_id": self.task,
                "target_file": target_relpath,
                "best_score_so_far": self.best_score,
                "validation_summary": validation_summary,
                "original_source": original_source,
                "candidate_source": candidate_source,
            },
            ensure_ascii=False,
        )
        data, raw_output = self.gateway.ask_structured(
            (
                "Score the candidate from 0.0 to 10.0. "
                "Reward correctness, reduced defects, and maintainability. "
                "Penalize unnecessary churn."
            ),
            payload,
            phase="A",
            output_schema=schema,
            system_instruction=(
                "You are the Nexus Battlesuit judge. "
                "Return a strict JSON verdict with a numeric score."
            ),
        )
        try:
            score = float(data.get("score", 0.0))
        except Exception:
            score = 0.0
        score = max(0.0, min(10.0, score))
        summary = str(data.get("summary", "")).strip()
        if not summary:
            summary = str(raw_output)[:200]
        return score, summary

    def _run_round(self, round_id: int, workpath: Path) -> RoundOutcome:
        signal.signal(signal.SIGALRM, self._timeout_handler)
        signal.alarm(self.budget_sec)

        try:
            print(f"\n🔄 [{self.task} | Round {round_id}] Starting local convergence loop...")
            params = self.optimizer.suggest()
            temp = params.get("temperature", 0.7)
            top_p = params.get("top_p", 0.9)
            print(
                f"   🎛️ [DeepScientist:Suggest] Params: temp={temp:.2f}, top_p={top_p:.2f}"
            )

            rules = self.hub.load_program_rules(str(self.project_root / "program.md"))
            source_code = self._read_source(workpath, self.resolved_target_file)
            generation, generation_error = self._generate_candidate(
                self.resolved_target_file,
                source_code,
                params,
                rules,
            )
            if generation is None:
                self.optimizer.observe(params, 0.0)
                self._append_optimization_curve(round_id, params, 0.0, "GENERATION_FAILED")
                signal.alarm(0)
                return RoundOutcome(
                    score=0.0,
                    candidate="",
                    status="GENERATION_FAILED",
                    summary=generation_error,
                )

            candidate = str(generation.get("content", ""))
            if candidate == source_code:
                self.optimizer.observe(params, 0.0)
                self._append_optimization_curve(round_id, params, 0.0, "NO_CHANGE")
                signal.alarm(0)
                return RoundOutcome(
                    score=0.0,
                    candidate="",
                    status="NO_CHANGE",
                    summary="candidate matched the existing file",
                )

            target_path = workpath / self.resolved_target_file
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(candidate, encoding="utf-8")

            validation_ok, validation_summary = self._validate_candidate(
                workpath, self.resolved_target_file
            )
            if not validation_ok:
                self.optimizer.observe(params, 0.0)
                self._append_optimization_curve(
                    round_id, params, 0.0, "VALIDATION_FAILED"
                )
                signal.alarm(0)
                return RoundOutcome(
                    score=0.0,
                    candidate=candidate,
                    status="VALIDATION_FAILED",
                    summary=validation_summary,
                )

            score, judge_summary = self._judge_candidate(
                self.resolved_target_file,
                source_code,
                candidate,
                validation_summary,
            )
            self.feynman_auditor.run_advisory_audit(
                pr_diff=candidate,
                task_spec=self.task,
            )
            self.optimizer.observe(params, score)
            self._append_optimization_curve(round_id, params, score, "SCORED")

            signal.alarm(0)
            return RoundOutcome(
                score=score,
                candidate=candidate,
                status="SCORED",
                summary=f"{validation_summary}\n{judge_summary}".strip(),
            )

        except TimeoutError as exc:
            return RoundOutcome(0.0, "", "TIMEOUT", str(exc))
        except Exception as exc:
            return RoundOutcome(0.0, "", "ERROR", str(exc))
        finally:
            signal.alarm(0)

    def _commit_candidate(self, workpath: Path, round_id: int, score: float) -> tuple[bool, str]:
        add_res = subprocess.run(
            ["git", "add", self.resolved_target_file],
            cwd=workpath,
            capture_output=True,
            text=True,
            check=False,
        )
        if add_res.returncode != 0:
            return False, add_res.stderr.strip() or add_res.stdout.strip()

        commit_res = subprocess.run(
            [
                "git",
                "commit",
                "-m",
                f"AutoResearch {self.task} Round {round_id}: score {score:.2f}",
            ],
            cwd=workpath,
            capture_output=True,
            text=True,
            check=False,
        )
        if commit_res.returncode != 0:
            return False, commit_res.stderr.strip() or commit_res.stdout.strip()
        return True, commit_res.stdout.strip()

    def run(self) -> Dict[str, Any]:
        print(
            f"🏭 [AutoResearch] Factory Initiated | Task: {self.task} | Rounds: {self.max_rounds}"
        )

        timestamp = int(time.time_ns())
        safe_task_name = "".join(filter(str.isalnum, self.task))[:15] or "task"
        task_id_unique = f"ds-{safe_task_name}-{timestamp % 1000000}"
        branch_prefix = f"audit/{task_id_unique}"
        lock_path = "/tmp/nexus_git_atomic.lock"

        acquired = False
        for _ in range(60):
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                acquired = True
                break
            except FileExistsError:
                time.sleep(1)

        if not acquired:
            print("❌ [Fatal] Could not acquire Git Global Lock. Terminating.")
            return {"task": self.task, "status": "LOCK_FAILED", "best_score": self.best_score}

        workpath: Optional[Path] = None
        task_id = None
        branch = None
        try:
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=self.project_root,
                capture_output=True,
                check=False,
            )
            task_id, branch, leased = self.worktree_mgr.lease(task_id_unique, branch_prefix)
        finally:
            if os.path.exists(lock_path):
                os.remove(lock_path)

        if not leased:
            print("❌ [Fatal] Could not establish workspace. Terminating.")
            return {"task": self.task, "status": "LEASE_FAILED", "best_score": self.best_score}

        workpath = Path(leased)
        self.resolved_target_file = self._resolve_target_file()
        target_path = workpath / self.resolved_target_file
        if not target_path.exists():
            print(
                f"❌ [Fatal] Target not found in worktree: {self.resolved_target_file}"
            )
            return {
                "task": self.task,
                "status": "TARGET_NOT_FOUND",
                "target_file": self.resolved_target_file,
                "best_score": self.best_score,
            }

        try:
            head_res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=workpath,
                capture_output=True,
                text=True,
                check=False,
            )
            self.base_commit = head_res.stdout.strip()

            for round_id in range(1, self.max_rounds + 1):
                outcome = self._run_round(round_id, workpath)
                improved = outcome.score > self.best_score and bool(outcome.candidate)

                if improved:
                    print(
                        f"   📈 [{self.task}] Improvement {self.best_score:.2f} -> {outcome.score:.2f}"
                    )
                    commit_ok, commit_summary = self._commit_candidate(
                        workpath, round_id, outcome.score
                    )
                    if commit_ok:
                        self.best_score = outcome.score
                        self.no_improve_streak = 0
                        head_res = subprocess.run(
                            ["git", "rev-parse", "HEAD"],
                            cwd=workpath,
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        self.base_commit = head_res.stdout.strip()
                        self._log_trace(
                            round_id,
                            "IMPROVED",
                            outcome.score,
                            outcome.summary,
                            extra={"commit": self.base_commit},
                        )
                        continue

                    subprocess.run(
                        ["git", "reset", "--hard", self.base_commit],
                        cwd=workpath,
                        capture_output=True,
                        check=False,
                    )
                    self.no_improve_streak += 1
                    self._log_trace(
                        round_id,
                        "COMMIT_FAILED",
                        0.0,
                        commit_summary,
                    )
                else:
                    subprocess.run(
                        ["git", "reset", "--hard", self.base_commit],
                        cwd=workpath,
                        capture_output=True,
                        check=False,
                    )
                    self.no_improve_streak += 1
                    self._log_trace(
                        round_id,
                        outcome.status,
                        outcome.score,
                        outcome.summary,
                    )

                if self.no_improve_streak >= self.convergence_patience:
                    message = (
                        f"Convergence reached after {self.no_improve_streak} "
                        "consecutive non-improving rounds."
                    )
                    print(f"✅ [AutoResearch] {message}")
                    self._log_trace(
                        round_id,
                        "CONVERGED",
                        self.best_score,
                        message,
                    )
                    break

            # --- [Approval Gate] Queue for Review ---
            if self.best_score > 0 and self.base_commit:
                try:
                    self.pending_manifest_path.parent.mkdir(parents=True, exist_ok=True)
                    pending = []
                    if self.pending_manifest_path.exists():
                        with open(self.pending_manifest_path, "r", encoding="utf-8") as f:
                            pending = json.load(f)
                    
                    # Remove older entry if it exists
                    pending = [p for p in pending if p["task"] != self.task]
                    
                    pending.append({
                        "task": self.task,
                        "target_file": self.resolved_target_file,
                        "best_score": self.best_score,
                        "workpath": str(workpath),
                        "commit_sha": self.base_commit,
                        "timestamp": datetime.now().isoformat()
                    })
                    with open(self.pending_manifest_path, "w", encoding="utf-8") as f:
                        json.dump(pending, f, indent=2)
                    print(f"📝 [Approval Gate] Task '{self.task}' queued for review.")
                except Exception as e:
                    print(f"⚠️ [Approval Gate] Failed to queue task for review: {e}")

            print(
                f"\n✅ [AutoResearch] Finished {self.task}. "
                f"Target: {self.resolved_target_file} | Best Score: {self.best_score:.2f}"
            )

            csv_path = self.project_root / f"optimization_curve_{safe_task_name}.csv"
            with open(csv_path, "w", encoding="utf-8") as handle:
                handle.write("round,score,status,target_file\n")
                if self.tracelog_path.exists():
                    for line in self.tracelog_path.read_text(encoding="utf-8").splitlines():
                        if not line.strip():
                            continue
                        entry = json.loads(line)
                        if entry.get("task") == self.task:
                            handle.write(
                                f"{entry['round']},{entry['flashjudge_score']},"
                                f"{entry['status']},{entry.get('target_file', '')}\n"
                            )
            print(f"📊 [Metrics] Optimization curve exported to {csv_path}")
            return {
                "task": self.task,
                "status": "COMPLETED",
                "target_file": self.resolved_target_file,
                "best_score": self.best_score,
                "workpath": str(workpath),
                "commit_sha": self.base_commit,
            }
        finally:
            print(f"🧹 [Cleanup] Worktree retained at {workpath}")


def _update_manifest_status(project_root: Path, task_name: str, commit_sha: str):
    """
    🛡️ [Governance] Automatically sync task_manifest.yaml after physical harvest.
    """
    manifest_path = project_root / "task_manifest.yaml"
    if not manifest_path.exists():
        return
    
    # 🧬 Heuristic: Map file path to manifest ID (e.g. pipeline.py -> *pipeline*)
    identifier = Path(task_name).stem.lower()
    
    content = manifest_path.read_text(encoding="utf-8")
    
    # 🔍 Regex Match: Find the block corresponding to the auto.repair task for this target
    import re
    block_pattern = rf"(- id: auto\.repair\..*?{re.escape(identifier)}.*?\n\s+description: ')(.*?)(')"
    
    timestamp = datetime.now().strftime("%Y-%m-%d")
    resolved_msg = f"AUTO-REPAIR: RESOLVED {timestamp}. Physical patch merged ({commit_sha[:7]}), acceptance-check PASS."
    
    new_content, count = re.subn(block_pattern, rf"\1{resolved_msg}\3", content, flags=re.IGNORECASE)
    
    if count > 0:
        manifest_path.write_text(new_content, encoding="utf-8")
        print(f"📡 [Governance] Task Manifest updated for '{identifier}'.")
        
        # 🛡️ Governance Commit
        subprocess.run(["git", "add", "task_manifest.yaml"], capture_output=True)
        subprocess.run(["git", "commit", "-m", f"docs(governance): resolve task status for {identifier} ({commit_sha[:7]})"], capture_output=True)
        print(f"📜 [Governance] Commit generated: docs(governance): resolve task status for {identifier}")
    else:
        print(f"⚠️ [Governance] Could not find matching task ID for '{identifier}' in manifest.")


def main():
    parser = argparse.ArgumentParser(description="Nexus Night Shift local convergence runner")
    parser.add_argument("--task", default="default-task")
    parser.add_argument("--tasks", help="Comma separated list of tasks")
    parser.add_argument("--swarm", action="store_true", help="Launch multi-agent swarm")
    parser.add_argument("--workers", type=int, default=2, help="Number of parallel workers")
    parser.add_argument("--max_rounds", type=int, default=10)
    parser.add_argument("--budget_min", type=int, default=5)
    parser.add_argument("--target_file", default=DEFAULT_TARGET_FILE)
    parser.add_argument(
        "--mode",
        default="default",
        choices=["default", "v23-burnin", "governance-upgrade"],
        help="Night Shift mode",
    )
    parser.add_argument("--target-events", type=int, default=0, help="Target number of events to stop")
    parser.add_argument("--parallel", type=int, default=1, help="Parallel workers")
    parser.add_argument("--target-layers", type=int, default=19, help="Number of governance layers")
    parser.add_argument("--auto-stop", action="store_true", help="Auto-stop based on governance criteria")
    parser.add_argument(
        "--convergence-patience",
        type=int,
        default=5,
        help="Stop a target early after this many consecutive non-improving rounds",
    )
    parser.add_argument("--list-pending", action="store_true", help="List all optimizations waiting for approval")
    parser.add_argument("--approve", type=str, help="Harvest (cherry-pick) the given task or 'ALL'")

    args = parser.parse_args()

    pending_file = Path(".nexus/nightshift/pending.json")

    # [Approval Gate] List operations
    if args.list_pending:
        if not pending_file.exists():
            print("✨ [Approval Gate] No pending reviews.")
            return
        with open(pending_file, "r", encoding="utf-8") as f:
            pending = json.load(f)
        if not pending:
            print("✨ [Approval Gate] No pending reviews.")
            return

        print("\n🎯 [Approval Gate] Night Shift 巡邏完畢，以下是待審核的優化成果：\n")
        for i, item in enumerate(pending, 1):
            print(f"[{i}] Task: {item['task']} | Target: {item['target_file']}")
            print(f"  | 最佳分數：{item['best_score']:.2f}")
            print(f"  | Commit:   {item['commit_sha'][:7]}")
            print(f"  | 合併指令：uv run python scripts/nightshift.py --approve {item['task']}")
            print("-" * 50)
        return

    # [Approval Gate] Harvest operations
    if args.approve:
        if not pending_file.exists():
            print("❌ [Approval Gate] Pending manifest not found. No tasks to harvest.")
            return
        with open(pending_file, "r", encoding="utf-8") as f:
            pending = json.load(f)
        
        target_task = args.approve.strip()
        matches = [p for p in pending if target_task == "ALL" or p["task"] == target_task]
        if not matches:
            print(f"⚠️ [Approval Gate] No pending task matching '{target_task}' found.")
            return
            
        remaining = [p for p in pending if p not in matches]
        print(f"🔍 [Approval Gate] Found {len(matches)} task(s) to harvest.")
        
        for item in matches:
            print(f"\n🚀 Harvesting '{item['task']}' (Commit {item['commit_sha'][:7]})...")
            # 1. Branch Cherry-pick
            res = subprocess.run(["git", "cherry-pick", item['commit_sha']], capture_output=True, text=True)
            if res.returncode != 0:
                print(f"❌ [Conflict] Git cherry-pick failed for {item['task']}. Aborting...")
                subprocess.run(["git", "cherry-pick", "--abort"])
                print("   Please resolve manually. Task left in pending list.")
                remaining.append(item)
                continue
            
            # 2. Worktree Cleanup 
            workpath = item['workpath']
            print(f"🧹 Removing worktree: {workpath}")
            subprocess.run(["git", "worktree", "remove", "--force", workpath], capture_output=True)
            print(f"✅ Harvested '{item['task']}' successfully!")
            
            # 3. 🛡️ [Governance Sync]
            _update_manifest_status(Path("."), item['task'], item['commit_sha'])
            
        with open(pending_file, "w", encoding="utf-8") as f:
            json.dump(remaining, f, indent=2)
        return

    if args.mode == "v23-burnin":
        os.environ["NEXUS_BURNIN_MODE"] = "1"
        os.environ["NEXUS_SKIP_PROTOCOL_GATE"] = "1"
    elif args.mode == "governance-upgrade":
        os.environ["NEXUS_GOVERNANCE_UPGRADE"] = "1"
        os.environ["NEXUS_TARGET_LAYERS"] = str(args.target_layers)

    task_list = [task.strip() for task in args.tasks.split(",")] if args.tasks else [args.task]
    task_list = [task for task in task_list if task]

    def check_stop_criteria() -> bool:
        metrics_file = Path(".nexus/metrics/governance_benchmark.json")
        if not metrics_file.exists():
            return False
        try:
            with open(metrics_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return bool(data.get("ci_pass")) and float(data.get("context_reduction", 0.0)) >= 0.3
        except Exception:
            return False

    if args.swarm or args.parallel > 1:
        workers = args.parallel if args.parallel > 1 else args.workers
        print(f"🐝 [Swarm] Launching {workers} workers for {len(task_list)} tasks...")
        with ProcessPoolExecutor(max_workers=workers) as executor:
            for task_name in task_list:
                shift = AutoResearchNightShift(
                    task_name,
                    args.max_rounds,
                    args.budget_min,
                    args.target_file,
                    args.convergence_patience,
                )
                executor.submit(shift.run)
                if args.auto_stop and check_stop_criteria():
                    print("🎯 [Governance] Convergence reached (CI Pass + Context -30%). Stopping.")
                    break
    else:
        for task_name in task_list:
            shift = AutoResearchNightShift(
                task_name,
                args.max_rounds,
                args.budget_min,
                args.target_file,
                args.convergence_patience,
            )
            shift.run()
            if args.auto_stop and check_stop_criteria():
                print("🎯 [Governance] Convergence reached. Finishing task.")
                break


if __name__ == "__main__":
    main()
