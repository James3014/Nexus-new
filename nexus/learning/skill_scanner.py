from typing import Any, Dict, List, Optional, Tuple
"""Security scanner for learned skill artifacts.

Scans SKILL.md content for 4 threat vectors:
1. Destructive commands (rm -rf, sudo, DROP TABLE)
2. Data exfiltration (curl, wget, requests.post to external URLs)
3. Prompt injection (ignore previous, system:, etc.)
4. Supply chain risk (pip install, npm install unaudited packages)

Inspired by skill-creator-advanced's compatibility/trust audit layer.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from nexus.core.event_bus import NexusEventBus


@dataclass
class ScanResult:
    """Result of a security scan on a skill artifact."""
    safe: bool
    warnings: List[str] = field(default_factory=list)
    blocked_reasons: List[str] = field(default_factory=list)
    scanned_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )

    def to_dict(self):
        return {
            "safe": self.safe,
            "warnings": self.warnings,
            "blocked_reasons": self.blocked_reasons,
            "scanned_at": self.scanned_at,
        }


# --- Threat Patterns ---

BLOCK_PATTERNS: List[Tuple[str, str]] = [
    # Destructive commands
    (r"rm\s+-rf", "破壞性刪除指令 (rm -rf)"),
    (r"sudo\s+", "使用管理員權限 (sudo)"),
    (r"DROP\s+TABLE", "資料庫破壞指令 (DROP TABLE)"),
    (r"TRUNCATE\s+TABLE", "資料庫清空指令 (TRUNCATE TABLE)"),
    (r"format\s+[cCdD]:", "磁碟格式化指令 (format)"),
    # Data exfiltration
    (r"curl\s+https?://", "外部網路請求 (curl)"),
    (r"wget\s+https?://", "外部下載指令 (wget)"),
    (r"requests\.post\s*\(", "Python HTTP POST 請求 (requests.post)"),
    (r"requests\.get\s*\(.*https?://", "Python HTTP GET 到外部 URL"),
]

WARN_PATTERNS: List[Tuple[str, str]] = [
    # Prompt injection
    (r"ignore\s+previous\s+instructions", "可能的 Prompt Injection (ignore previous)"),
    (r"system\s*:", "可能的 Prompt Injection (system:)"),
    (r"<\|im_start\|>", "可能的 Prompt Injection (im_start token)"),
    (r"你是一個", "可能的 Prompt Injection (角色覆寫)"),
    # Supply chain risk
    (r"pip\s+install\s+", "未審核的 Python 套件安裝 (pip install)"),
    (r"npm\s+install\s+", "未審核的 Node.js 套件安裝 (npm install)"),
    (r"gem\s+install\s+", "未審核的 Ruby 套件安裝 (gem install)"),
]

# --- Compliance Patterns (v2.0 Readiness Gate) ---

COMPLIANCE_PATTERNS: List[Tuple[str, str, bool]] = [
    (r"decision_boundary:\s*\{.*\}", "遺漏或格式錯誤之決策邊界 (Decision Boundary)", True),
    (r"iaov_steps:\s*\[.*\]", "遺漏或格式錯誤之 IAOV 執行協議", True),
    (r"readiness_checklist:\s*\{.*\}", "遺漏 Readiness Checklist 結晶標籤", False), # Optional for L0
    (r"portability_markers:", "遺漏跨工具可攜性標記 (Portability Markers)", False),
]


def scan_skill(content: str, enforce_compliance: bool = False) -> ScanResult:
    """Scan skill content for security threats.

    Returns a ScanResult indicating whether the content is safe,
    with detailed warnings and blocking reasons.
    """
    if not content:
        return ScanResult(safe=True)

    warnings: List[str] = []
    blocked: List[str] = []

    for pattern, reason in BLOCK_PATTERNS:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            blocked.append(f"🔴 BLOCK: {reason} (偵測到 {len(matches)} 處)")

    for pattern, reason in WARN_PATTERNS:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            warnings.append(f"🟡 WARN: {reason} (偵測到 {len(matches)} 處)")

    # --- Compliance Checks (v2.0 Readiness Gate) ---
    if enforce_compliance:
        for pattern, reason, is_block in COMPLIANCE_PATTERNS:
            if not re.search(pattern, content, re.MULTILINE | re.DOTALL):
                msg = f"📁 COMPLIANCE: {reason}"
                if is_block:
                    blocked.append(f"🔴 BLOCK: {msg}")
                else:
                    warnings.append(f"🟡 WARN: {msg}")

    safe = len(blocked) == 0
    if not safe:
        NexusEventBus.publish("scan_blocked", {"blocked_reasons": blocked, "content_preview": content[:200]})
        
    return ScanResult(safe=safe, warnings=warnings, blocked_reasons=blocked)
