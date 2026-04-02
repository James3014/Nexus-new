from typing import Any, Dict, List, Optional, Tuple
import ast
import logging

logger = logging.getLogger(__name__)

# 🛡️ 物理黑名單：禁止代碼生成階段出現的核心風險位點
DANGEROUS_CALLS = {
    "os.system", "os.popen", "subprocess.run", "subprocess.call",
    "subprocess.Popen", "shutil.rmtree", "eval", "exec", "compile"
}

class SecurityScanner(ast.NodeVisitor):
    """AST 安全掃描引擎 (ARC Validator 基因)"""
    def __init__(self):
        self.findings = []

    def visit_Call(self, node: ast.Call):
        name = self._resolve_name(node.func)
        if name in DANGEROUS_CALLS:
            self.findings.append(f"DANGEROUS_CALL_DETECTED: {name} at line {node.lineno}")
        self.generic_visit(node)

    def _resolve_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = self._resolve_name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""

class NexusHardenedValidator:
    """物理硬化驗證器 (Hardened Validator)
    
    具備 AST 物理安全性檢查與環境對位能力。
    數據真值轉向 Nexus 生產環境。
    """
    
    def validate_code(self, code: str) -> Dict[str, Any]:
        """執行代碼物理 X 光掃描。"""
        logger.info("code_security_scan_started")
        
        try:
            tree = ast.parse(code)
            scanner = SecurityScanner()
            scanner.visit(tree)
            
            if scanner.findings:
                logger.warning("security_policy_violation_detected [%d_findings]", len(scanner.findings))
                return {"passed": False, "reason": "security_violation", "errors": scanner.findings}
                
            return {"passed": True, "reason": "secure_logic_verified"}
            
        except SyntaxError as exc:
            logger.error("code_syntax_validation_failed: %s", exc)
            return {"passed": False, "reason": "syntax_error", "errors": [str(exc)]}
        except Exception as exc:
            logger.error("validator_unexpected_failure: %s", exc)
            return {"passed": False, "reason": "system_error"}
