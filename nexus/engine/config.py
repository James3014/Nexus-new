from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

@dataclass
class EngineConfig:
    """R1: NexusEngine 執行配置物件。"""
    project_root: Path
    run_dir: Optional[Path] = None
    silent: bool = False
    fast_mode: bool = False
    audit_level: str = "normal"
    eval_mode: bool = False
    model: Optional[str] = None
    delivery_mode: str = "standard"
    sandbox_mode: bool = True
    auto_repair_enabled: bool = True
    custom_executor: Optional[str] = None
    benchmark_mode: bool = False
    governor_threshold: float = 0.5
    execution_context: Dict[str, Any] = field(default_factory=dict)
