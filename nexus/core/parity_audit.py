from typing import Any, Dict, List, Optional, Set, Tuple
import ast
import logging

logger = logging.getLogger(__name__)

class SurfaceViolation(Exception):
    """當偵測到功能表面積丟失時拋出 (30 Pillars P0)"""
    pass

class ParityAuditor:
    """
    ⚖️ Nexus 原子對等審計器 (AOS-P5.7 / Claw-30P0)
    負責核驗修復後的代碼表面積 (Surface Area) 是否與修復前對等。
    """
    
    def __init__(self, workspace: str):
        self.workspace = workspace

    def audit_surface(self, before: str, after: str, filepath: str = "unknown") -> Dict[str, Any]:
        """🎯 檢查修復後的功能表面積是否完整 (Claw-30 Pillars Interface)"""
        res = self.audit_patch(before, after, filepath)
        if res["risk"] == "HIGH":
            raise SurfaceViolation(f"❌ [Parity:SurfaceViolation] 丟函數了！ File: {filepath}")
        return res

    def audit_patch(self, before_code: str, after_code: str, filepath: str) -> Dict[str, Any]:
        """🎯 檢查修復後的功能表面積是否完整"""
        logger.info(f"⚖️ [ParityAuditor] Auditing surface area for {filepath}...")
        
        try:
            old_surface = self._extract_surface(before_code)
            new_surface = self._extract_surface(after_code)
        except SyntaxError as e:
            logger.error(f"❌ [Parity:SyntaxError] Failed to parse code for {filepath}: {e}")
            return {"surface_match": False, "error": "Syntax Error in code."}
            
        missing = old_surface - new_surface
        extra = new_surface - old_surface
        
        match = len(missing) == 0
        risk = "HIGH" if missing else "LOW"
        
        if not match:
            logger.warning(f"🚨 [Parity:VIOLATION] Missing functions in {filepath}: {missing}")
            
        return {
            "filepath": filepath,
            "surface_match": match,
            "missing_funcs": list(missing),
            "extra_funcs": list(extra),
            "risk": risk
        }

    def _extract_surface(self, code: str) -> Set[str]:
        """提取函數名、類名與方法名（只比對名稱，不比對參數）"""
        if not code.strip():
            return set()
            
        tree = ast.parse(code)
        surface = set()
        
        for node in ast.walk(tree):
            # 1. 頂層函數（只取名稱，不取參數）
            if isinstance(node, ast.FunctionDef):
                surface.add(f"func:{node.name}")
                
            # 2. 類及其方法
            if isinstance(node, ast.ClassDef):
                surface.add(f"class:{node.name}")
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        idx = " (async)" if isinstance(item, ast.AsyncFunctionDef) else ""
                        surface.add(f"meth:{node.name}.{item.name}{idx}")
                        
        return surface
