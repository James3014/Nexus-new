#!/usr/bin/env python3
"""
🧠 Muse-Core Session Wrap-Up
學習自: alex-session-wrap-up (xbillwatsonx)
自建版本: 完全本地化，零外部 API，整合 TRINITY 架構

Usage:
    python3 session_wrap_up.py [<session_note>]

Phases:
    A - Ship It: Git commit + push
    B - Extract Learnings: 從最近 git log 萃取變更摘要
    C - Pattern Detect: 本地關鍵字比對（不呼叫外部 AI）
    D - Persist: 寫入 Daily_Log.md 和 History/
"""

import sys
import subprocess
import re
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional


def get_knowledge_root() -> Path:
    script_dir = Path(__file__).resolve().parent
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(script_dir),
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(r.stdout.strip())
    except subprocess.CalledProcessError:
        # Fallback to the true root (grandparent of 01_Operations/scripts)
        return script_dir.parent.parent


KNOWLEDGE_ROOT = get_knowledge_root()
DAILY_LOG = KNOWLEDGE_ROOT / "01_Operations/Daily_Log.md"
HISTORY_DIR = KNOWLEDGE_ROOT / "01_Operations/History"


def run(cmd: List[str], cwd: Optional[str] = None) -> Tuple[int, str, str]:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def phase_a_ship_it(note: str) -> dict:
    print("\n📦 [Phase A] Ship It ...")
    code, repo, _ = run(
        ["git", "rev-parse", "--show-toplevel"], cwd=str(KNOWLEDGE_ROOT)
    )
    if code != 0:
        return {"shipped": False, "error": "Not a git repo"}

    # Add all intended changes
    run(["git", "add", "-A"], cwd=repo)
    # Exclude common noise/settings files from auto-wrap-up independently
    for pattern in ["**/__pycache__/*", "**/.DS_Store", ".obsidian/workspace.json"]:
        run(["git", "reset", "HEAD", "--", pattern], cwd=repo)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = f"chore(session): auto wrap-up at {ts}"
    if note:
        msg += f" — {note}"

    commit_cmd = ["git", "commit", "-m", msg]
    code, out, err = run(commit_cmd, cwd=repo)
    # returncode 1 with no staged changes is a no-op (not an error)
    combined_output = (out + " " + err).lower()
    is_noop = code == 1 and "nothing to commit" in combined_output
    if code != 0 and not is_noop:
        return {"shipped": False, "error": err or out}

    code2, _, _ = run(["git", "push"], cwd=repo)
    pushed = code2 == 0
    status_msg = "(no-op)" if is_noop else msg
    print("  ✓ Committed: {}".format(status_msg))
    print(
        "  {} Push: {}".format(
            "✓" if pushed else "⚠️", "ok" if pushed else "skipped/offline"
        )
    )
    return {"shipped": True, "commit_msg": msg, "pushed": pushed, "noop": is_noop}


# ── Phase B: Extract Learnings ────────────────────────────────
def phase_b_extract_learnings() -> List[str]:
    print("\n📝 [Phase B] Extracting learnings from recent git log ...")
    code, log, _ = run(
        ["git", "log", "--oneline", "--since=12 hours ago", "--no-merges"],
        cwd=str(KNOWLEDGE_ROOT),
    )
    if code != 0 or not log:
        print("  ⚠ No recent commits found.")
        return []

    lines = [line.strip() for line in log.splitlines() if line.strip()]
    learnings = []
    for line in lines[:10]:
        parts = line.split(" ", 1)
        if len(parts) == 2:
            learnings.append(parts[1])

    for item in learnings:
        print("  · {}".format(item))
    return learnings


# ── Phase C: Pattern Detect (local keyword matching) ──────────
PATTERN_RULES = [
    (r"(fix|修正|修復|bug)", "🐛 有 Bug 修復"),
    (r"(feat|新增|建立|create|add)", "✨ 新功能或新建檔案"),
    (r"(refactor|重構|clean|整理)", "🔧 架構重構"),
    (r"(docs|文件|readme|note)", "📄 文件更新"),
    (r"(security|安全|audit|防護)", "🛡️ 安全性相關"),
    (r"(memory|記憶|knowledge|知識)", "🧠 知識庫演化"),
    (r"(agent|自動|auto|skill)", "🤖 Agent/Skill 升級"),
    (r"(chore|maintain|維運)", "⚙️ 系統維護"),
]


def phase_c_pattern_detect(learnings: List[str]) -> List[str]:
    print("\n🔍 [Phase C] Pattern detection ...")
    if not learnings:
        return []

    combined = " ".join(learnings).lower()
    detected = []
    for pattern, label in PATTERN_RULES:
        if re.search(pattern, combined, re.IGNORECASE):
            detected.append(label)

    if not detected:
        detected = ["📋 一般維運與更新"]

    for item in detected:
        print("  → {}".format(item))
    return detected


# ── Phase D: Persist to Daily_Log.md + History/ ───────────────
def _insert_under_date_header(content: str, today: str, entry_text: str) -> str:
    # Match the full date header line, including optional suffix text.
    header_pattern = r"^## 📅 {}\b[^\n]*$".format(re.escape(today))
    match = re.search(header_pattern, content, flags=re.MULTILINE)

    if match:
        insert_at = match.end()
        return content[:insert_at] + "\n\n" + entry_text + content[insert_at:]

    suffix = "\n\n## 📅 {} 系統演化紀錄\n\n{}".format(today, entry_text)
    if content and not content.endswith("\n"):
        content += "\n"
    return content + suffix


def phase_d_persist(learnings: List[str], patterns: List[str], note: str) -> Path:
    print("\n💾 [Phase D] Persisting to Daily_Log.md ...")
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%H:%M")

    entry_lines = ["### 🔄 {} Session Wrap-Up [{}]".format(today, now)]
    if note:
        entry_lines.append("- **主題**: {}".format(note))

    if learnings:
        entry_lines.append("- **本次演化**:")
        for item in learnings[:5]:
            entry_lines.append("  - {}".format(item))

    if patterns:
        entry_lines.append("- **模式偵測**: {}".format(", ".join(patterns)))

    entry_text = "\n".join(entry_lines) + "\n"

    try:
        existing = DAILY_LOG.read_text(encoding="utf-8") if DAILY_LOG.exists() else ""
        updated = _insert_under_date_header(existing, today, entry_text)
        DAILY_LOG.write_text(updated, encoding="utf-8")
        print("  ✓ Written to Daily_Log.md")
    except Exception as exc:
        print("  ❌ Failed to write Daily_Log.md: {}".format(exc))

    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        history_file = HISTORY_DIR / "{}_Session_WrapUp.md".format(today)
        with history_file.open("a", encoding="utf-8") as f:
            if history_file.stat().st_size > 0:
                f.write("\n")
            f.write(entry_text)
        print("  ✓ Written to History/{}_Session_WrapUp.md".format(today))
        return history_file
    except Exception as exc:
        print("  ❌ Failed to write history: {}".format(exc))
        return HISTORY_DIR / "{}_Session_WrapUp.md".format(today)


# ── Main ──────────────────────────────────────────────────────
def main() -> None:
    note = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else ""

    print("=" * 50)
    print("🧠 Muse-Core Session Wrap-Up")
    if note:
        print("   主題備註: {}".format(note))
    print("=" * 50)

    # B + C first (read-only, no side effects)
    learnings = phase_b_extract_learnings()
    patterns = phase_c_pattern_detect(learnings)

    # D before A so logs are included in this commit
    phase_d_persist(learnings, patterns, note)

    # A: commit + push
    ship = phase_a_ship_it(note)

    print("\n" + "=" * 50)
    status = "✅" if ship.get("shipped") else "⚠️"
    print("{} Session Wrap-Up 完成！".format(status))
    print("=" * 50)


if __name__ == "__main__":
    main()
