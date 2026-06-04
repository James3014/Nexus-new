from typing import List, Dict, Any, Literal, Optional, Set
from dataclasses import dataclass
import hashlib
from nexus.services.local_heal.task_manifest import local_heal_113_task_manifest, LocalHealTaskSpec

@dataclass(frozen=True)
class TaskLaneAssignment:
    """[T1] 任務車道分配數據結構"""
    task_id: str
    lane: Literal["baseline", "challenge", "migration"]
    failure_family: str
    receipt_id: Optional[str] = None

class ManifestValidator:
    """
    🛡️ Task: v27 Manifest Schema Validator (Hardened)
    職責: 鎖死「欄位合法性、Lane 規則、Promotion Policy」三位一體治理。
    """
    VALID_LANES = {"baseline", "challenge", "migration"}
    VALID_POLICIES = {"default", "cross_domain_gate", "aggressive_explore", "evidence_driven"}

    @staticmethod
    def validate_spec(spec: LocalHealTaskSpec, known_ids: Optional[Set[str]] = None):
        # 1. 基礎型別與存在性檢查 (Type & Presence)
        if not isinstance(spec.task_id, str) or not spec.task_id:
            raise TypeError(f"❌ Type Error: task_id must be a non-empty string in {spec}")
            
        if known_ids is not None:
            if spec.task_id in known_ids:
                raise ValueError(f"❌ Governance Violation: Duplicate task_id detected: {spec.task_id}")
            known_ids.add(spec.task_id)

        # 2. domain_id 准入鎖死
        if not spec.domain_id or spec.domain_id == "legacy" and spec.kind == "cross_domain_experimental":
            raise ValueError(f"❌ Governance Violation: explicit domain_id required for experimental task {spec.task_id}")
            
        if not spec.verifier_pack_id:
             raise ValueError(f"❌ Governance Violation: verifier_pack_id is required in task {spec.task_id}")

        # 3. Lane 與 Policy 規則
        if spec.lane not in ManifestValidator.VALID_LANES:
            raise ValueError(f"❌ Illegal Lane: {spec.lane} in {spec.task_id}. Must be one of {ManifestValidator.VALID_LANES}")

        if spec.promotion_policy not in ManifestValidator.VALID_POLICIES:
            raise ValueError(f"❌ Illegal Promotion Policy: {spec.promotion_policy} in {spec.task_id}")

        # 4. 互斥與完整性條件 (Linus: Data constraints)
        if spec.lane == "migration" and not spec.extension_metadata:
            raise ValueError(f"❌ Incomplete Migration: extension_metadata required for lane 'migration' in {spec.task_id}")
            
        if spec.lane == "baseline" and spec.kind == "cross_domain_experimental":
            # 禁止新實驗任務直接進入 Baseline
            raise ValueError(f"❌ Safety Violation: experimental task {spec.task_id} cannot enter 'baseline' lane directly.")

class ManifestManager:
    """
    🗺️ Task T1: 113 題總表管理員 (v27 Hardened)
    職責: 實施「100 守成 + 13 攻堅 + 新域擴展」的分層治理政策。
    """
    @staticmethod
    def get_full_inventory() -> List[TaskLaneAssignment]:
        specs = local_heal_113_task_manifest()
        inventory = []
        known_ids = set()
        
        for spec in specs:
            # 准入驗證 (Hardened)
            ManifestValidator.validate_spec(spec, known_ids)
            
            inventory.append(TaskLaneAssignment(
                task_id=spec.task_id,
                lane=spec.lane,
                failure_family="SOLVED" if spec.lane == "baseline" else "PENDING_RECOVERY"
            ))
            
        return inventory

    @staticmethod
    def get_manifest_hash() -> str:
        """[P0] Schema Freeze Check: 任何欄位變動都會改變雜湊值"""
        specs = local_heal_113_task_manifest()
        raw_data = str([str(s) for s in specs]).encode("utf-8")
        return hashlib.sha256(raw_data).hexdigest()
