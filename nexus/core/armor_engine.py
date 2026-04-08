from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseArmorEngine(ABC):
    """
    🛡️ Base Armor Engine (Refactored)
    定義戰甲執行的統一介面，符合策略模式。
    """
    def __init__(self, armor_type: str):
        self.armor_type = armor_type

    @abstractmethod
    def execute(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        pass

class PythonArmorEngine(BaseArmorEngine):
    def __init__(self):
        super().__init__("python")

    def execute(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # 執行 Python 戰甲特定邏輯
        return {"status": "SUCCESS", "armor": "python"}

class RustArmorEngine(BaseArmorEngine):
    def __init__(self):
        super().__init__("rust")

    def execute(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # 執行 Rust 戰甲特定邏輯
        return {"status": "SUCCESS", "armor": "rust"}

class ArmorFactory:
    """
    🏭 Armor Factory
    根據型別分配對應的戰甲引擎。
    """
    _ARMORS = {
        "python": PythonArmorEngine,
        "rust": RustArmorEngine
    }

    @staticmethod
    def get_armor(armor_type: str) -> BaseArmorEngine:
        armor_class = ArmorFactory._ARMORS.get(armor_type.lower())
        if not armor_class:
            raise ValueError(f"Unknown armor type: {armor_type}")
        return armor_class()
