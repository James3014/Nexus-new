from abc import ABC, abstractmethod
from .protocol import ExecutorInput, ExecutorOutput

class BaseExecutor(ABC):
    """
    Nexus 執行器基底類別。
    所有外部 Agent 適配器必須實作 execute 介面，
    確保推理與治理完全解耦。
    """
    
    @abstractmethod
    def execute(self, input_data: ExecutorInput) -> ExecutorOutput:
        """
        執行推理任務。
        輸入：標準協議包 (InputPacket)。
        輸出：標準報表包 (OutputPacket)。
        """
        pass

    def name(self) -> str:
        return self.__class__.__name__
