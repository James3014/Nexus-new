from abc import ABC, abstractmethod
from typing import Any, Dict
from nexus.problem.problem_ticket import ProblemTicket

class BaseLane(ABC):
    """
    🏗️ Task M5: Execution Lane Base Contract
    職責: 定義所有執行車道的統一介面。
    這能消除不同領域 (Django, Astropy, etc.) 之間的流程差異。
    """
    
    @abstractmethod
    def plan(self, ticket: ProblemTicket) -> Any:
        """根據 Ticket 制定執行計畫"""
        pass

    @abstractmethod
    def guard(self, patch: str) -> bool:
        """執行領域級安全檢查"""
        pass

    @abstractmethod
    def execute(self, plan: Any) -> str:
        """執行修復或變更，產出 Patch"""
        pass

    @abstractmethod
    def verify(self, patch: str) -> bool:
        """驗證變更是否達成 Acceptance Checks"""
        pass

    @abstractmethod
    def emit_evidence(self) -> Dict[str, Any]:
        """產出標準化的 Evidence Bundle"""
        pass
