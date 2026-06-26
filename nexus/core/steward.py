from pathlib import Path
import json


class MemorySteward:
    """負責將審查教訓結晶為長期記憶。"""

    def __init__(self, project_root):
        self.project_root = Path(project_root) if project_root else None
        self.lessons_file = (
            self.project_root / ".codex_lessons.md" if self.project_root else None
        )

    def crystallize(self, violations):
        """將 violations 轉化為代碼教訓並寫入檔案。"""
        if not self.lessons_file:
            return

        new_lessons = []
        for v in violations:
            pattern = v.get("reason", "Unknown Issue")
            fix = v.get("suggestion", "N/A")

            # 建立結構化教訓
            lesson = f"### 🧠 Lesson: {pattern[:50]}\n- **Anti-pattern**: {pattern}\n- **Correct Practice**: {fix}\n"
            new_lessons.append(lesson)

        if not new_lessons:
            return

        # 讀取現有內容，避免重複
        existing_content = ""
        if self.lessons_file.exists():
            existing_content = self.lessons_file.read_text(encoding="utf-8")

        # 簡單的重複檢查 (基於核心關鍵字)
        with open(self.lessons_file, "a", encoding="utf-8") as f:
            if not existing_content:
                f.write("# 🧬 Project Evolution Lessons\n\n")

            for l in new_lessons:
                # 僅在尚未存在時寫入
                if l[:30] not in existing_content:
                    f.write(f"\n{l}")
                    print(
                        f"   💎 [Memory] Crystallized new lesson: {l.splitlines()[0]}"
                    )

        return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Nexus Memory Steward")
    parser.add_argument("--root", required=True, help="Project root")
    parser.add_argument("--violation", help="JSON formatted violation to crystallize")
    args = parser.parse_args()

    steward = MemorySteward(args.root)
    if args.violation:
        try:
            v_data = json.loads(args.violation)
            steward.crystallize([v_data])
        except Exception as e:
            print(f"Error: {e}")
    else:
        print("Steward active. No violation provided for crystallization.")
