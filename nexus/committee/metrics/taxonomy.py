from dataclasses import dataclass
from typing import Literal, Optional

# [NEXUS v26.4] 精準歸因分類
FailureMainBucket = Literal[
    "coverage_low",       # 候選池無解
    "diversity_low",      # 候選過於同質
    "verifier_gap_low",   # 選不出 (Gap 小)
    "abstain_safe",       # 安全棄權 (訊號衝突)
    "env_blocked"         # 環境噪音
]

@dataclass(frozen=True)
class FailureTaxonomyV3:
    """
    [Task T1] 強制每個失敗必須精準對齊單體模型無法處理的痛點。
    """
    main_bucket: FailureMainBucket
    secondary_bucket: Optional[str] = None
    evidence_ref: Optional[str] = None
    oracle_gap_estimate: float = 0.0 # 預估離正解的距離
