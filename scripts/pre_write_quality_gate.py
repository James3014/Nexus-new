import os
import re
import yaml
import argparse
import tempfile
import subprocess
import json
from pathlib import Path

# 基礎配置
BRAND_VOICE_PATH = "/Users/jameschen/Downloads/obsidian/知識庫/00_System_Knowledge/01_Persona/brandVoice.md"
DB_PATH = os.path.expanduser("~/.openclaw/memory/lancedb-pro")


class QualityGate:
    def __init__(self, draft, linked_notes=None, file_path=None):
        self.draft = draft
        self.linked_notes = linked_notes or []
        self.file_path = file_path
        self.issues = []
        self.metadata = {}

    def audit_metadata(self):
        """Tier 0: Metadata 必填項檢查"""
        yaml_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", self.draft, re.DOTALL)
        if not yaml_match:
            self.issues.append("缺失 YAML Header (---)")
            return False

        try:
            self.metadata = yaml.safe_load(yaml_match.group(1))
            required_fields = ["ai_role", "ai_scope", "domain", "level"]
            for field in required_fields:
                if field not in self.metadata or not self.metadata[field]:
                    self.issues.append(f"YAML 缺失必填欄位: {field}")
        except Exception as e:
            self.issues.append(f"YAML 解析失敗: {e}")
            return False
        return True

    def audit_structure(self):
        """Tier 1: Muse-Core 3.0 四層結構檢查 (含 Trunk 深度)"""
        required_sections = ["## Agent-Guide", "## Agent-Index", "## Agent-Actions"]
        for section in required_sections:
            if section not in self.draft:
                self.issues.append(f"缺失 Muse-Core 3.0 必要區塊: {section}")

        # Trunk 深度檢查 (Legacy & Depth Guard)
        if "## 🌳 TREE 核心提煉 (Trunk)" in self.draft:
            trunk_content = re.search(
                r"## 🌳 TREE 核心提煉 \(Trunk\)\n(.*?)(?=\n##|---|$)", self.draft, re.DOTALL
            )
            if not trunk_content or len(trunk_content.group(1).strip()) < 20:
                self.issues.append("Trunk 內容過於單薄，缺乏提煉深度")
        elif "## Agent-Index" not in self.draft:
            self.issues.append("缺失知識核心區塊 (需具備 Trunk 或 Agent-Index)")

        return True

    def narritive_stitching(self):
        """Tier 2: 敘事化連結 (Narrative Stitching)"""
        links = re.findall(r"\[\[(.*?)\]\]", self.draft)
        for link in links:
            # 寬鬆檢查：是否有上下各 5-30 字
            pattern = rf".{{5,30}}\[\[{re.escape(link)}\]\].{{5,30}}"
            context = re.search(pattern, self.draft, re.DOTALL)
            if not context:
                # 嚴格檢查：該行文字長度
                lines = self.draft.split("\n")
                context_line = next((l for l in lines if f"[[{link}]]" in l), "")
                clean_line = re.sub(r"\[\[.*?\]\]", "", context_line).strip()
                if len(clean_line) < 15:
                    self.issues.append(
                        f"連結 [[{link}]] 缺乏敘事銜接 (Narrative Stitching)：上下文過於零碎"
                    )
        return True

    def persona_check(self):
        """Tier 3: 語氣對齊 (Persona Check)"""
        forbidden_words = [
            "總而言之", "大家都知道", "令人驚訝的是", "簡單來說", "也就是說", "顯而易見"
        ]
        for word in forbidden_words:
            if word in self.draft:
                self.issues.append(f"檢測到品牌禁忌詞：{word}")
        return True

    def check_anti_hallucination(self):
        """Tier 4: 事實標註查驗 (Anti-Hallucination Gate)"""
        data_patterns = [r"\d+%", r"\$\d+", r"\d{4}年\d{1,2}月\d{1,2}日"]
        has_facts = any(re.search(p, self.draft) for p in data_patterns)
        if has_facts and not any(tag in self.draft for tag in ["✅", "⚠️", "❌"]):
            self.issues.append(
                "檢測到具體事實數據，但未按照 SOP 標註信心等級 (✅/⚠️/❌)"
            )

        if "❌" in self.draft:
            self.issues.append(
                "檢測到 Low-Confidence (❌) 標記，禁止寫入，請先修正事實"
            )
        return True

    def check_deduplication(self):
        """Tier 5: 物理防碰撞與去重 (>0.85)"""
        lines = [l for l in self.draft.split("\n") if l.strip()]
        if not lines: return True
        query = lines[0][:100]
        
        # 優先尋找 brain_search_v4，否則退回 v2
        search_script = "/Users/jameschen/Downloads/Muse-Nexus/scripts/brain_search_v4.py"
        if not os.path.exists(search_script):
            search_script = "/Users/jameschen/Downloads/Muse-Nexus/scripts/brain_search_v2.py"
        
        if not os.path.exists(search_script):
            return True

        try:
            res = subprocess.run(
                ["python3", search_script, query, "--json", "--limit", "1"],
                capture_output=True, text=True, timeout=10
            )
            if res.returncode == 0:
                results = json.loads(res.stdout)
                if results and "_distance" in results[0]:
                    if results[0]["_distance"] < 0.15:
                        self.issues.append(
                            f"檢測到高度重複內容 (相似度 > 0.85)，請執行『增量合併』而非重複寫入。"
                        )
        except Exception:
            pass
        return True

    def safe_write(self, target_path, trust_level="Verified"):
        """實作 Atomic Swap 安全寫入與品質蓋章"""
        target_path = Path(target_path).resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        fd, temp_path = tempfile.mkstemp(dir=target_path.parent, prefix="muse_tmp_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(self.draft)
            
            # 原子替換
            os.replace(temp_path, target_path)
            
            # 自動調用 quality_stamper
            stamper = "/Users/jameschen/.local/bin/quality_stamper.py"
            if os.path.exists(stamper):
                # 傳遞信任等級作為 commit_id 的一部分或額外參數
                stamp_id = f"Muse-Core-v3.0/{trust_level}"
                subprocess.run(["python3", stamper, str(target_path), stamp_id], capture_output=True)
            
            # --- [NEW] Obsidian CLI 整合 ---
            # 嘗試使用 obsidian CLI 開啟檔案以提供即時 UI 反饋
            try:
                # 檢查 obsidian 指令是否可用
                res = subprocess.run(["which", "obsidian"], capture_output=True, text=True)
                if res.returncode == 0:
                    # 使用 obsidian open 指令開啟檔案
                    # 注意：Obsidian CLI 需要 vault 名稱或路徑，這裡假設已配置或使用絕對路徑
                    subprocess.run(["obsidian", "open", str(target_path)], capture_output=True)
            except Exception:
                pass # 靜默失敗，不影響核心寫入流程
            # ----------------------------

            print(f"✅ 原子寫入與品質蓋章成功：{target_path}")
            return True
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            self.issues.append(f"安全寫入失敗：{e}")
            return False

    def run_full_audit(self):
        self.audit_metadata()
        self.audit_structure()
        self.narritive_stitching()
        self.persona_check()
        self.check_anti_hallucination()
        self.check_deduplication()
        return {"is_valid": len(self.issues) == 0, "issues": self.issues}


def main():
    parser = argparse.ArgumentParser(description="Muse-Core 3.0 結構化品質閘門 (Unified Engine)")
    parser.add_argument("file", nargs="?", help="待審核的草稿檔案路徑")
    parser.add_argument("--write", help="審核通過後寫入的目標路徑")
    parser.add_argument("--level", default="Verified", choices=["Draft", "Reviewed", "Verified"], help="初始信任等級")
    parser.add_argument("--describe", action="store_true", help="輸出閘門規則的 JSON Schema")
    args = parser.parse_args()

    # --- [NEW] API 描述化 ---
    if args.describe:
        schema = {
            "name": "Muse-Core 3.0 Quality Gate",
            "version": "3.0.1",
            "requirements": {
                "metadata": ["ai_role", "ai_scope", "domain", "level"],
                "structure": ["## Agent-Guide", "## Agent-Index", "## Agent-Actions"],
                "stitching": "Min 15 chars context per [[link]]",
                "anti_hallucination": "Stats require ✅/⚠️/❌ tags",
                "persona": "No forbidden corporate jargon",
                "deduplication": "Similarity score must be < 0.85"
            },
            "trust_levels": ["Draft", "Reviewed", "Verified"]
        }
        print(json.dumps(schema, indent=2, ensure_ascii=False))
        return

    if not args.file or not os.path.exists(args.file):
        print(f"❌ 錯誤：找不到或未提供檔案 {args.file}")
        return

    with open(args.file, "r", encoding="utf-8") as f:
        content = f.read()

    gate = QualityGate(content)
    result = gate.run_full_audit()

    if result["is_valid"]:
        print("✅ 品質審核通過！符合 Muse-Core 3.0 結構化規約。")
        if args.write:
            if gate.safe_write(args.write, trust_level=args.level):
                print(f"🚀 寫入作業完成。等級：{args.level}")
            else:
                print(f"❌ 寫入作業失敗。")
    else:
        print("❌ 品質審核未通過：")
        for issue in result["issues"]:
            print(f"  - {issue}")
        exit(1)


if __name__ == "__main__":
    main()
