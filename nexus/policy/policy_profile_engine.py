from dataclasses import dataclass
from typing import Dict, Any
from nexus.problem.taxonomy import ProblemClass

@dataclass(frozen=True)
class PolicyProfile:
    """
    🛡️ 政策設定檔 (Policy Profile)
    職責: 定義針對特定問題類別的治理約束。
    """
    profile_name: str
    requires_sandbox: bool
    requires_two_person_review: bool
    requires_staging_replay: bool
    allow_canary: bool
    read_only: bool = False

class PolicyProfileEngine:
    """
    🛡️ Task M4: Policy Profile Engine
    職責: 基於 ProblemClass 自動匹配對應的治理政策設定。
    Linus Good Taste: 政策是資料，而不是硬編碼的分支。
    """
    
    PROFILES = {
        ProblemClass.PRODUCTION: PolicyProfile(
            profile_name="PROD_INCIDENT",
            requires_sandbox=True,
            requires_two_person_review=True,
            requires_staging_replay=True,
            allow_canary=False # 生產事故通常直接 hotfix 且嚴格驗證
        ),
        ProblemClass.DEBUG: PolicyProfile(
            profile_name="INVESTIGATION",
            requires_sandbox=False,
            requires_two_person_review=False,
            requires_staging_replay=False,
            allow_canary=False,
            read_only=True # Debug 模式預設唯讀
        ),
        ProblemClass.REVIEW: PolicyProfile(
            profile_name="CODE_REVIEW",
            requires_sandbox=True,
            requires_two_person_review=True,
            requires_staging_replay=False,
            allow_canary=False
        ),
        ProblemClass.CHANGE: PolicyProfile(
            profile_name="STANDARD_CHANGE",
            requires_sandbox=True,
            requires_two_person_review=False,
            requires_staging_replay=True,
            allow_canary=True
        )
    }

    @staticmethod
    def get_profile(problem_class: ProblemClass) -> PolicyProfile:
        return PolicyProfileEngine.PROFILES.get(
            problem_class, 
            PolicyProfileEngine.PROFILES[ProblemClass.CHANGE] # 預設走 Standard Change
        )
