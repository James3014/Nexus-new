from enum import Enum, auto

class ProblemClass(Enum):
    """
    🧬 Task M1: Problem Taxonomy (Core Governance Axis)
    職責: 定義 Nexus 治理的核心問題類別，這是不隨 Domain 變動的內層契約。
    """
    PRODUCTION = auto()  # 線上事故、緊急修復
    SAFETY = auto()      # 安全性/注入/並發鎖 (補齊)
    DEBUG = auto()       # 根因定位、假設驗證
    REVIEW = auto()      # 代碼/設計審查
    CHANGE = auto()      # 新功能、重構
    MIGRATION = auto()   # 遷移/ORM (補齊)
    PERFORMANCE = auto() # 性能延遲、吞吐
    GOVERNANCE = auto()  # 政策、審計、封板

class Severity(Enum):
    """問題嚴重程度"""
    CRITICAL = auto()
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()
