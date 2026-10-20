import os
import json
import time
import subprocess
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class MissionStatus(str, Enum):
    DRAFT = "draft"         # 規劃中
    ACTIVE = "active"       # 戰鬥中 (Running)
    PAUSED = "paused"       # 暫停 (Snapshot saved)
    BLOCKED = "blocked"     # 遭門禁阻擋 (Gate fail, need human)
    VERIFYING = "verifying" # 驗收中 (Acceptance check)
    COMPLETED = "completed" # 成功封印 (Manifest sealed)
    ABORTED = "aborted"     # 撤退

class MissionTransitionError(ValueError):
    """Raised when a mission status change is not in MISSION_TRANSITIONS."""


# Legal mission status transitions. Terminal states (COMPLETED, ABORTED) have no exits.
# ACTIVE->ACTIVE / BLOCKED->BLOCKED are idempotent re-entries (restart after a crashed run,
# repeated preflight failure).
MISSION_TRANSITIONS: Dict[MissionStatus, frozenset] = {
    MissionStatus.DRAFT: frozenset({MissionStatus.ACTIVE, MissionStatus.BLOCKED, MissionStatus.ABORTED}),
    MissionStatus.ACTIVE: frozenset({
        MissionStatus.ACTIVE, MissionStatus.PAUSED, MissionStatus.BLOCKED,
        MissionStatus.VERIFYING, MissionStatus.ABORTED,
    }),
    MissionStatus.PAUSED: frozenset({MissionStatus.ACTIVE, MissionStatus.BLOCKED, MissionStatus.ABORTED}),
    MissionStatus.BLOCKED: frozenset({
        MissionStatus.ACTIVE, MissionStatus.BLOCKED, MissionStatus.PAUSED, MissionStatus.ABORTED,
    }),
    MissionStatus.VERIFYING: frozenset({
        MissionStatus.COMPLETED, MissionStatus.ACTIVE, MissionStatus.BLOCKED, MissionStatus.ABORTED,
    }),
    MissionStatus.COMPLETED: frozenset(),
    MissionStatus.ABORTED: frozenset(),
}


def transition(mission: "NexusMission", new_status: MissionStatus) -> MissionStatus:
    """Move ``mission`` to ``new_status`` or raise MissionTransitionError if illegal."""
    new_status = MissionStatus(new_status)
    current = MissionStatus(mission.status)
    if new_status not in MISSION_TRANSITIONS[current]:
        raise MissionTransitionError(
            f"illegal mission transition: {current.value} -> {new_status.value}"
        )
    mission.status = new_status
    return new_status


def _usage_tokens(usage: Dict[str, Any]) -> float:
    def num(key: str) -> float:
        value = usage.get(key)
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else 0.0

    total = num("total_tokens") or num("tokens_used") or num("tokens")
    if total:
        return total
    return (
        num("input_tokens") + num("output_tokens")
        or num("prompt_tokens") + num("completion_tokens")
        or num("prompt_eval_count") + num("eval_count")
    )


def extract_receipt_tokens(payload: Any) -> float:
    """Sum token counts from every ``usage`` mapping (and top-level token fields) in a receipt tree."""
    total = 0.0
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "usage" and isinstance(value, dict):
                total += _usage_tokens(value)
            elif key in ("tokens_used", "total_tokens") and isinstance(value, (int, float)) and not isinstance(value, bool):
                total += max(0.0, float(value))
            else:
                total += extract_receipt_tokens(value)
    elif isinstance(payload, list):
        for item in payload:
            total += extract_receipt_tokens(item)
    return total


class NexusMission(BaseModel):
    mission_id: str
    objective: str
    status: MissionStatus = MissionStatus.DRAFT
    constraints: List[str] = Field(default_factory=list)
    
    # 預算控制 (防止失控)
    budget: Dict[str, float] = Field(default_factory=lambda: {
        "max_tokens": 1000000.0,
        "max_wall_time_sec": 259200.0, # 72 hours
        "max_retries": 10.0
    })
    
    # 累積消耗統計 (Gateway-level Telemetry 核心)
    accumulated_usage: Dict[str, float] = Field(default_factory=lambda: {
        "tokens": 0.0,
        "wall_time_sec": 0.0,
        "retries": 0.0
    })
    
    # 持久化指標
    current_run_id: Optional[str] = None
    last_snapshot_path: Optional[str] = None
    evidence_bundle_hash: Optional[str] = None
    git_fingerprint: Optional[str] = None
    
    # 歷史追蹤
    run_history: List[str] = Field(default_factory=list)

    # Wall-clock accounting: epoch seconds of the current active stretch (start/resume), None when idle.
    active_since: Optional[float] = None

    budget_unknown: bool = False
    token_budget_unknown: bool = False

    def persist(self, project_root: Path) -> None:
        """安全寫入到 .nexus/mission.json 中"""
        out_dir = project_root / ".nexus"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "mission.json"
        
        # Pydantic v1 / v2 相容序列化
        if hasattr(self, "model_dump_json"):
            data = self.model_dump_json(indent=2)
        else:
            data = self.json(indent=2)
        
        path.write_text(data, encoding="utf-8")

    @classmethod
    def load(cls, project_root: Path) -> Optional["NexusMission"]:
        """從 .nexus/mission.json 載入並還原戰役模型"""
        path = project_root / ".nexus" / "mission.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if hasattr(cls, "model_validate"):
                return cls.model_validate(payload)
            else:
                return cls.parse_obj(payload)
        except Exception:
            return None

    def begin_wall_clock(self, now: Optional[float] = None) -> None:
        """Start (or keep) the active stretch used for wall-time accounting (start/resume)."""
        if self.active_since is None:
            self.active_since = time.time() if now is None else float(now)

    def settle_wall_clock(self, now: Optional[float] = None) -> float:
        """Fold the active stretch into accumulated wall time (pause/abort/run end). Returns seconds added."""
        if self.active_since is None:
            return 0.0
        current = time.time() if now is None else float(now)
        elapsed = max(0.0, current - self.active_since)
        self.accumulated_usage["wall_time_sec"] = self.accumulated_usage.get("wall_time_sec", 0.0) + elapsed
        self.active_since = None
        return elapsed

    def wall_time_remaining(self, now: Optional[float] = None) -> Optional[float]:
        """Seconds left before the wall-time limit trips, counting any open stretch; None when unlimited."""
        limit = self.budget.get("max_wall_time_sec", 0.0)
        if limit <= 0.0:
            return None
        current = time.time() if now is None else float(now)
        open_stretch = max(0.0, current - self.active_since) if self.active_since is not None else 0.0
        return limit - self.accumulated_usage.get("wall_time_sec", 0.0) - open_stretch

    def add_tokens_from_receipt_file(self, receipt_path: Path) -> float:
        """Add tokens recorded in a run receipt/report JSON to accumulated usage. Returns tokens added.

        A `nexus run` report carries no usage itself; it names the unified runtime receipt
        (``unified_runtime_receipt_path``), where stage usage is recorded. When the report
        exists but no usage can be read from it or that receipt, a mission with ``max_tokens``
        marks its token spend unknown and fails the budget check from then on (#2768). Only a
        missing report leaves the budget as it was.
        """
        receipt_file = Path(receipt_path)
        if not os.path.lexists(receipt_file):  # a dangling symlink is present, not missing
            return 0.0
        payload = _read_json_bounded(receipt_file)
        added = extract_receipt_tokens(payload) if payload is not None else 0.0

        if isinstance(payload, dict):
            unified = _unified_receipt_for(receipt_file, payload)
            if unified is not None:
                added += extract_receipt_tokens(unified)

        self.accumulated_usage["tokens"] = self.accumulated_usage.get("tokens", 0.0) + added

        max_tokens = self.budget.get("max_tokens")
        has_max_tokens = (
            isinstance(max_tokens, (int, float))
            and not isinstance(max_tokens, bool)
            and max_tokens > 0
        )
        if has_max_tokens and added <= 0.0:
            self.budget_unknown = True
            self.token_budget_unknown = True

        return added

    def check_telemetry_budget(self) -> bool:
        """
        [Gateway-level Telemetry 防禦]
        確認當前累積開銷是否超出預算。若超標，傳回 False 用於立即攔截與阻斷。
        """
        max_tokens = self.budget.get("max_tokens")
        has_max_tokens = (
            isinstance(max_tokens, (int, float))
            and not isinstance(max_tokens, bool)
            and max_tokens > 0
        )
        if has_max_tokens and (self.budget_unknown or self.token_budget_unknown):
            return False

        for key in ("tokens", "wall_time_sec", "retries"):
            budget_key = f"max_{key}"
            if key == "tokens":
                budget_key = "max_tokens"
            elif key == "retries":
                budget_key = "max_retries"
            
            limit = self.budget.get(budget_key, 0.0)
            spent = self.accumulated_usage.get(key, 0.0)
            if limit > 0.0 and spent >= limit:
                return False
        return True

    def _block(self, project_root: Path) -> bool:
        """Move to BLOCKED via the transition table; terminal missions stay untouched."""
        try:
            transition(self, MissionStatus.BLOCKED)
        except MissionTransitionError:
            return False
        self.persist(project_root)
        return True

    def run_fingerprint_preflight(self, project_root: Path) -> bool:
        """
        [Environment Fingerprinting 防禦]
        比對當前的環境變數與 Git SHA。如果 preflight.sh 執行失敗，
        或是 Git SHA 與上次記錄不對位，則標記為 BLOCKED 以防跨 session 狀態污染。
        """
        # 1. 執行實體環境預檢
        preflight_script = project_root / "scripts/ops" / "_nexus_preflight.sh"
        if preflight_script.exists():
            res = subprocess.run(["bash", str(preflight_script)], cwd=str(project_root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode != 0:
                self._block(project_root)
                return False

        # 2. 獲取當前 Git SHA
        try:
            current_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(project_root), stderr=subprocess.DEVNULL, timeout=5.0).decode("utf-8").strip()
        except Exception:
            current_sha = None

        if self.git_fingerprint and current_sha and self.git_fingerprint != current_sha:
            # Git SHA 發生偏離，疑似環境被修改
            self._block(project_root)
            return False

        if current_sha and not self.git_fingerprint:
            self.git_fingerprint = current_sha
            self.persist(project_root)
        
        return True


_MAX_RECEIPT_BYTES = 8 * 1024 * 1024


def _read_json_bounded(path: Path) -> Any:
    """Parse a regular JSON file of bounded size; None when it cannot be read or parsed."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_RECEIPT_BYTES:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):  # UnicodeDecodeError is a ValueError
        return None


def _unified_receipt_for(report_file: Path, report: dict) -> Optional[dict]:
    """The unified runtime receipt a run report names, if it is this run's.

    The pointer is taken as written (absolute, as `nexus run` writes it) or relative to the
    report's own directory; the same file as the report is ignored, and when both sides carry
    a task id they must agree, so a stale receipt from another run is not counted.
    """
    raw = report.get("unified_runtime_receipt_path")
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = report_file.parent / candidate
    try:
        if candidate.resolve() == report_file.resolve():
            return None
    except (OSError, RuntimeError, ValueError):  # ValueError: e.g. a NUL in the pointer
        return None
    unified = _read_json_bounded(candidate)
    if not isinstance(unified, dict):
        return None
    expected = report.get("unified_runtime_task_id")
    actual = unified.get("task_id")
    if expected and actual and str(expected) != str(actual):
        return None
    return unified
