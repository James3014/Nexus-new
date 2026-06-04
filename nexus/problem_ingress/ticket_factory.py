from typing import Dict, Any
from .problem_ticket import ProblemTicket, ProblemClass

class TicketFactory:
    """
    職責: 將原始資料轉化為 ProblemTicket 實例。
    這是 Problem Ingress 層的對外接口。
    """
    
    @staticmethod
    def create_from_swe_spec(spec_data: Dict[str, Any]) -> ProblemTicket:
        # 模擬從舊有的 LocalHealTaskSpec 轉化
        # 在此實施 Linus 式消滅特例：所有屬性皆對位
        
        # 決定 Problem Class
        family = spec_data.get("family", "general")
        p_class = ProblemClass.CORRECTNESS
        if "migration" in family:
            p_class = ProblemClass.MIGRATION
        elif "concurrency" in family:
            p_class = ProblemClass.SAFETY
            
        return ProblemTicket(
            source="swe-bench",
            task_id=spec_data["task_id"],
            problem_class=p_class,
            domain_family=family,
            risk_level="MEDIUM", # 預設
            repro_steps=[],
            acceptance_checks=[],
            rollbackability=True
        )
