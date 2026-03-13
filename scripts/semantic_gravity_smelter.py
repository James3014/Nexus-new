import os
import json
import glob
from datetime import datetime

# Brain-B Core Script: Semantic Gravity Smelter
# 功能：掃描自治區內的碎片化日誌，識別低熵檔案並提出「熔煉」建議，實踐「主動遺忘」憲法。

class BrainBSmelter:
    def __init__(self, base_path="/Users/jameschen/Downloads/Brain_B_Lab"):
        self.base_path = base_path
        self.logs_path = os.path.join(base_path, "99_Experiments/Brain_B")
        self.manifesto_path = os.path.join(base_path, "EVOLUTION_MANIFESTO.md")

    def scan_for_redundancy(self):
        """掃描那些重複性高、長度短、且超過 24 小時未更新的演化碎步"""
        files = glob.glob(os.path.join(self.logs_path, "*.md"))
        candidates = []
        for f in files:
            if "DREAM_" in f or "EVOLUTION_LOG" in f:
                stats = os.stat(f)
                age_hours = (datetime.now().timestamp() - stats.st_mtime) / 3600
                if age_hours > 24:
                    with open(f, 'r', encoding='utf-8') as file:
                        content = file.read()
                        if len(content) < 500: # 規模較小的碎片
                            candidates.append(f)
        return candidates

    def generate_smelt_plan(self, candidates):
        """產出熔煉計畫，準備將這些碎片轉化為更高維度的結論"""
        if not candidates:
            return "目前語義引力穩定，無須熔煉。"
        
        plan_name = f"SMELT_PLAN_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        plan_path = os.path.join(self.base_path, "Future_Ops", plan_name)
        
        with open(plan_path, 'w', encoding='utf-8') as f:
            f.write(f"# 🌀 Brain-B 語義熔煉計畫\n\n")
            f.write(f"**執行時間**: {datetime.now().isoformat()}\n")
            f.write(f"**待熔煉碎片數**: {len(candidates)}\n\n")
            f.write("## 候選清單\n")
            for c in candidates:
                f.write(f"- {os.path.basename(c)}\n")
            f.write("\n## 預期產出\n")
            f.write("- [ ] 提取跨域雜交關鍵詞\n")
            f.write("- [ ] 更新演化日誌總表\n")
            f.write("- [ ] 執行物理刪除以實踐「主動遺忘」\n")
        
        return f"熔煉計畫已生成：{plan_name}"

if __name__ == "__main__":
    smelter = BrainBSmelter()
    candidates = smelter.scan_for_redundancy()
    result = smelter.generate_smelt_plan(candidates)
    print(result)