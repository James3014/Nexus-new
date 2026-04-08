import json
from pathlib import Path
from typing import Dict, Any, List

class ReadabilityGate:
    """
    👁️ Work Order E: Human Readability Gate
    稽核規格的可讀性與無歧義性，確保「指揮官 3 秒看懂」。
    """

    JARGON_LIST = ["改一下", "調整", "處理", "fix", "update", "change", "優化", "可能", "大概"]

    def __init__(self, i_pack: Dict[str, Any], sot_map: Dict[str, Any]):
        self.pack = i_pack
        self.sot = sot_map

    def audit(self) -> Dict[str, Any]:
        """
        執行可讀性稽核。
        """
        jargon_found = []
        # 遍歷 goal 與 deliverables 檢查黑話
        text_to_scan = self.pack.get("goal", "") + " ".join(self.pack.get("deliverables", []))
        for jargon in self.JARGON_LIST:
            if jargon in text_to_scan:
                jargon_found.append(jargon)

        # 檢查無來源欄位 (Unmapped fields)
        unmapped = []
        for field in self.sot.get("field_map", {}):
            if "source" not in self.sot["field_map"][field]:
                unmapped.append(field)

        # 計算評分 (基礎 100)
        score = 100 - (len(jargon_found) * 10) - (len(unmapped) * 15)
        score = max(0, score)

        return {
            "readability_score": score,
            "jargon_count": len(jargon_found),
            "jargon_details": jargon_found,
            "unmapped_fields": unmapped,
            "timestamp": "now"
        }

    def save_report(self, run_dir: Path) -> Dict[str, Any]:
        """儲存稽核報告"""
        report = self.audit()
        report_path = run_dir / "readability_audit.json"
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return report

if __name__ == "__main__":
    # 測試
    mock_pack = {
        "goal": "優化一下代碼，然後處理那個 bug。",
        "deliverables": ["fix_script.py"]
    }
    mock_sot = {"field_map": {"status": {}}}
    gate = ReadabilityGate(mock_pack, mock_sot)
    print(json.dumps(gate.audit(), indent=2, ensure_ascii=False))
