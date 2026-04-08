from enum import Enum

class TaskType(str, Enum):
    """🛠️ Nexus Task Types"""
    UI = "ui"
    BACKEND = "backend"
    FULLSTACK = "fullstack"
    INFRA = "infra"
    CONVERSATION = "conversation"
    RESEARCH = "research"

class Phase(str, Enum):
    """六階段演化鏈 (PXDRAC)"""
    PROBE = "P"
    EXPLORE = "X"
    DIAGNOSE = "D"
    REPAIR = "R"
    AUDIT = "A"
    CRYSTALLIZE = "C"

class RiskLevel(str, Enum):
    """治理風險等級"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    BLOCK = "BLOCK"
