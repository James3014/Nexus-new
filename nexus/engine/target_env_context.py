from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class TargetEnvContext:
    """顯式區分 Nexus 引擎根目錄與被解題目標專案的環境上下文。"""
    engine_root: Path        # Nexus 引擎自身（不可變）
    target_repo_root: Path   # 被解題專案的實體路徑
    target_venv: Path | None = None # 目標專案的虛擬環境路徑
    run_dir: Path | None = None     # 階段性執行日誌目錄

def resolve_target_env(engine_root: Path, task_id: str, run_dir: Path | None = None) -> TargetEnvContext:
    """根據 task_id 自動推斷被解題專案的 workspace 與 venv"""
    engine_root = Path(engine_root)
    task_id_lower = str(task_id or "").lower()
    
    target_repo_root = engine_root
    target_venv = None
    
    supported_repos = {
        "astropy": ("astropy", "astropy"),
        "sympy": ("sympy", "sympy"),
        "django": ("django", "django"),
        "requests": ("requests", "requests"),
        "flask": ("flask", "flask"),
    }
    
    for key, (repo_folder, venv_folder) in supported_repos.items():
        if key in task_id_lower:
            candidate_repo = engine_root / ".nexus" / "workspaces" / repo_folder
            candidate_venv = engine_root / f".venv_{venv_folder}"
            
            if candidate_repo.exists() and candidate_repo.is_dir():
                target_repo_root = candidate_repo
                if candidate_venv.exists() and candidate_venv.is_dir():
                    target_venv = candidate_venv
            break
            
    return TargetEnvContext(
        engine_root=engine_root,
        target_repo_root=target_repo_root,
        target_venv=target_venv,
        run_dir=run_dir
    )
