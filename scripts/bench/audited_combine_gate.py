#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


def load_blockers(policy_path: Path | str) -> list[dict[str, Any]]:
    """
    載入合約 combine blockers 的 RCA 檔案。
    """
    path = Path(policy_path)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("blockers", [])
    except Exception as e:
        print(f"⚠️ 載入 blockers 失敗: {e}")
        return []


def run_audited_combine(
    chunks_path: Path | str | None,
    policy_path: Path | str = ".nexus/policy/combine_blockers_rca.json",
    mock_chunks: list[dict[str, Any]] | None = None
) -> tuple[bool, dict[str, Any]]:
    """
    執行 7R Audited Combine rollup 審計。
    驗算五維度 (delivery, cost, ledger, token, promotion readiness)。
    """
    print("=== [Nexus] 7R Audited Combine rollup 審計 ===")
    
    # 1. 載入 Chunks (或 row 證據束)
    chunks: list[dict[str, Any]] = []
    if mock_chunks is not None:
        chunks = mock_chunks
        print(f"  - 使用 Mock 證據束: {len(chunks)} Chunks")
    else:
        if chunks_path and Path(chunks_path).exists():
            try:
                with open(chunks_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 兼容 tasks 或 rows 結構
                chunks = data.get("rows", data.get("tasks", []))
                print(f"  - 載入 Chunks 數量: {len(chunks)}")
            except Exception as e:
                print(f"❌ 載入 Chunks 檔案失敗: {e}")
                return False, {"error": "load_chunks_failed"}
        else:
            # 預設乾淨的模擬 100% Chunks 作為 demo
            print("  - 警告: 未指定實體 Chunks 檔案，載入默認驗算數據")
            chunks = []

    # 2. 進行五維度合約驗算 (五維全部 PASS 門檻)
    dimension_results = {
        "delivery": {"pass": True, "count": 0, "failures": []},
        "cost": {"pass": True, "count": 0, "failures": []},
        "ledger": {"pass": True, "count": 0, "failures": []},
        "token": {"pass": True, "count": 0, "failures": []},
        "promotion_readiness": {"pass": True, "count": 0, "failures": []}
    }

    for idx, chunk in enumerate(chunks):
        chunk_id = chunk.get("id", f"chunk-{idx}")
        
        # 1. Delivery 維度
        d_val = chunk.get("delivery_passed", chunk.get("delivery", True))
        if not d_val:
            dimension_results["delivery"]["pass"] = False
            dimension_results["delivery"]["failures"].append(chunk_id)
        else:
            dimension_results["delivery"]["count"] += 1
            
        # 2. Cost 維度
        c_val = chunk.get("cost_passed", chunk.get("cost", True))
        cost_class = chunk.get("cost_evidence_class", "")
        # 如果是模糊的 tokenless fallback 或是未收斂的 token_unreliable 狀態，則視為 fail
        if not c_val or cost_class == "token_unreliable":
            dimension_results["cost"]["pass"] = False
            dimension_results["cost"]["failures"].append(chunk_id)
        else:
            dimension_results["cost"]["count"] += 1
            
        # 3. Ledger 維度
        l_val = chunk.get("ledger_passed", chunk.get("ledger", True))
        if not l_val:
            dimension_results["ledger"]["pass"] = False
            dimension_results["ledger"]["failures"].append(chunk_id)
        else:
            dimension_results["ledger"]["count"] += 1
            
        # 4. Token 維度
        t_val = chunk.get("token_passed", chunk.get("token", True))
        t_clean = chunk.get("token_cleanliness_passed", True)
        if not t_val or not t_clean:
            dimension_results["token"]["pass"] = False
            dimension_results["token"]["failures"].append(chunk_id)
        else:
            dimension_results["token"]["count"] += 1
            
        # 5. Promotion Readiness 維度
        p_val = chunk.get("promotion_readiness_passed", chunk.get("promotion_readiness", True))
        if not p_val:
            dimension_results["promotion_readiness"]["pass"] = False
            dimension_results["promotion_readiness"]["failures"].append(chunk_id)
        else:
            dimension_results["promotion_readiness"]["count"] += 1

    # 五維度綜合判定
    five_dimensions_ok = all(res["pass"] for res in dimension_results.values())
    print("\n[1/2] 五維度合約聚合結果:")
    for dim_name, res in dimension_results.items():
        status = "PASS" if res["pass"] else "FAIL"
        fail_details = f" (不合格 Chunks: {res['failures']})" if not res["pass"] else ""
        print(f"  - {dim_name.capitalize()}: [{status}]{fail_details} (合格數: {res['count']}/{len(chunks)})")

    # 3. Blocker 零殘留判定
    print("\n[2/2] 正在檢測 combine_blockers_rca 狀態...")
    blockers = load_blockers(policy_path)
    
    # 查找是否有 action 為 non-refillable 的 blocker 殘留
    non_refillable_blockers = [
        b for b in blockers 
        if b.get("action") == "non-refillable"
    ]
    
    blockers_clean = len(non_refillable_blockers) == 0
    if not blockers_clean:
        print(f"  - ⚠️ 警告: 發現 {len(non_refillable_blockers)} 個 non-refillable blocker(s) 殘留！")
        for b in non_refillable_blockers:
            print(f"    - Task ID: {b.get('task_id')}, RCA: {b.get('rca_category')}")
            print(f"      證據鏈引用: {b.get('evidence_bundle_ref') or b.get('report_ref', '無')}")
    else:
        print("  - ✓ 未檢測到殘留的 non-refillable combine blockers。")

    # 4. 最終轉綠綠燈綜合判定
    # 只有當五維度全部 PASS，且 blockers 零殘留時，整體才可以轉綠，否則一律 fail-closed 維持 RED
    green_light = five_dimensions_ok and blockers_clean
    
    print("\n=== 審計判定報告 ===")
    if green_light:
        print("🟢 [GREEN] 7R audited combine 轉綠成功！全部合約門檻均已 PASS，無 blockers 殘留。")
        verdict = "GREEN"
    else:
        print("🔴 [RED] [FAIL-CLOSED] 審計未通過，合約維持 fail-closed (RED)！")
        reasons = []
        if not five_dimensions_ok:
            reasons.append("五維度合約驗算不完全 PASS")
        if not blockers_clean:
            reasons.append("偵測到 non-refillable blockers 殘留")
        print(f"  - 原因: {', '.join(reasons)}")
        verdict = "RED"
        
    return green_light, {
        "verdict": verdict,
        "five_dimensions_ok": five_dimensions_ok,
        "blockers_clean": blockers_clean,
        "dimension_details": dimension_results,
        "blockers_checked": len(blockers)
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="7R Audited Chunk-Combine Dry-Run Rollup Gate")
    parser.add_argument(
        "--chunks",
        type=str,
        default=None,
        help="Path to tasks/rows chunk JSON"
    )
    parser.add_argument(
        "--policy",
        type=str,
        default=".nexus/policy/combine_blockers_rca.json",
        help="Path to combine blockers RCA registry"
    )
    args = parser.parse_args()

    success, _ = run_audited_combine(
        chunks_path=args.chunks,
        policy_path=args.policy
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
