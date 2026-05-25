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

    def check_telemetry_budget(self) -> bool:
        """
        [Gateway-level Telemetry 防禦]
        確認當前累積開銷是否超出預算。若超標，傳回 False 用於立即攔截與阻斷。
        """
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
                self.status = MissionStatus.BLOCKED
                self.persist(project_root)
                return False

        # 2. 獲取當前 Git SHA
        try:
            current_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(project_root), stderr=subprocess.DEVNULL, timeout=5.0).decode("utf-8").strip()
        except Exception:
            current_sha = None

        if self.git_fingerprint and current_sha and self.git_fingerprint != current_sha:
            # Git SHA 發生偏離，疑似環境被修改
            self.status = MissionStatus.BLOCKED
            self.persist(project_root)
            return False

        if current_sha and not self.git_fingerprint:
            self.git_fingerprint = current_sha
            self.persist(project_root)
        
        return True
