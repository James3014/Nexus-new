---
title: AGENT 強制執行規約 v2.9
type: agent-protocol-snapshot
status: review_required
lifecycle: legacy
authority: non_normative
snapshot_version: v2.9
current_state_source: ../nexus_wiki_vault/00_Home/CURRENT_STATE.md
authority_manifest: DOC_AUTHORITY_MANIFEST.yaml
confidence: medium
---

# AGENT 強制執行規約 v2.9

> [!warning] Legacy Agent protocol snapshot
>
> This v2.9 protocol is not the complete current normative Agent policy.
>
> Evidence discipline, receipt requirements, completion gates, and
> anti-hallucination rules may still be useful within their original scope,
> but references to Nexus v26, mandatory runtime activation, provider
> behavior, bootstrap state, or execution topology require current physical
> verification.
>
> Do not use this document alone to claim that an Agent is currently
> "wearing Nexus," that a route is active, or that a capability is available.
>
> Current Agent protocol authority has not been resolved to a single canonical file.
> For current state, see:
> [`../nexus_wiki_vault/00_Home/CURRENT_STATE.md`](../nexus_wiki_vault/00_Home/CURRENT_STATE.md)

[NEXUS v26 HISTORICAL SNAPSHOT]

## 0) 目的
本規約強制 Gemini CLI / Antigravity / Codex / 其他 Agent 以「穿 Nexus」模式工作，但禁止在證據不足時直接宣稱 ACTIVE。

Nexus 不是另一個 agent，而是治理作業系統與能力戰甲：
- 模型負責推理與產出
- Nexus 負責路由、上下文、能力組合、證據、gate、回放、學習閉環

完成宣告必須有真實命令、真實輸出、真實 evidence/report 路徑、CapabilityReceipt、delivery/acceptance/ci gate 結果。

## 1) 身份與啟動
開頭一律先使用：

`[NEXUS v26 BOOTSTRAP-CANDIDATE]`

只有完成 bootstrap/preflight/wearing proof 後，才可切換為：

`[NEXUS v26 ACTIVE]`

必須證明：
1. `commit_sha`
2. `_nexus_preflight.sh` 結果
3. `uv run scripts/engine/nexus_cli.py --help`
4. `uv run scripts/engine/nexus_cli.py nexus --help`
5. Nexus context/briefing 已交付
6. CapabilityReceipt 或等價 runtime evidence 存在

任一缺失時回報 `NEXUS_BOOTSTRAP_INCOMPLETE` 或 `NEXUS_BOOTSTRAP_FAILED`，不得假裝已穿 Nexus。

## 2) CLI 與能力宣稱
只能使用 help 中實際存在的命令。以 `nexus <command>` 為主；`nexus:*` 僅在 help 證明仍存在時作相容路徑。

能力可宣稱前必須同時滿足：
- `selected=true`
- `invoked=true`
- `evidence_present=true`
- `gate_passed=true`
- `outcome_contributed=true`
- public claim 時另需 `public_claim_safe=true`

`selected-only`、recommendation-only、disabled flag、pending executor、報告文字推論都不可宣稱能力發揮。

## 3) Report Trust 硬規則
- `FAIL_CLOSED != SUCCESS`：fail-closed 只能代表防線有效，不代表任務完成。
- `ENV_INVALID` / `INFRA_INVALID` / dependency missing / Docker missing 必須獨立標記，不可算成模型或 Nexus 能力失敗。
- RLM/self-heal 必須有 `rlm_trace_present=true` 或 `capability_self_heal_used=true`。
- DDTree 必須有 pruning evidence 才能宣稱節省成本或加速。
- Swarm/Drone/Nightshift 必須有實際 report/evidence。
- deterministic local rescue profile 只能宣稱 Nexus-system local deterministic rescue profile 成本效率改善；不能說同一外部模型本身變省 token/wall。

## 4) 工作區安全
- Do not kill/stash/restore/clean ambiguous targets.
- `kill`、`pkill`、`git stash`、`git restore`、`git clean`、刪除 unrelated untracked 檔案前，必須列出精確候選並等使用者明確確認，除非使用者已指定 exact PID、command 或 path。
- 根目錄 `task_*.patch`、`*_test.patch`、`element_task_*` 預設是 `ROOT_ARTIFACT_LEAK`，除非任務明確要求保留。
- 禁止未授權修改 `.obsidian/`、`benchmarks/`、`logs/`、`nexus_swarm/`、`packages/`。

## 4.5) 環境變數與運行門禁 (強制 3B Advisor)
- 為了確保在測試、評估或解題任務中 100% 啟用 Qwen 3B S2T Advisor v2 輔助決策，Agent 在執行所有任務與測試指令時，**必須**在環境中設定或預載：
  ```bash
  NEXUS_S2T_3B_ADVISOR_ENABLED=1
  NEXUS_S2T_3B_ADVISOR_FORCE=1
  ```
- 當 `NEXUS_S2T_3B_ADVISOR_FORCE=1` 時，系統將繞過 10% Canary 分流限制，對所有推理行進行 100% 決策覆蓋與遙測審計。

## 5) Gates
一般任務至少回報：
1. `delivery_gate`
2. `acceptance_check`
3. `contract_check`
4. `ci_gate`
5. `public_claim_gate` 或 `NOT_APPLICABLE`

缺 evidence 視為 `UNVERIFIED`，不得宣稱完成。

## 6) Public Claim Gate
對外宣稱提升前必須滿足 same model、same task/trial multiset、hidden verifier、run eligibility complete、infra invalid rows 分離、trust mismatch 0、Nexus wearing valid rate 100%、context delivered 100%、claim verified 100%、evidence bundle hash present、raw JSONL preserved、per-capability public gate PASS。

任一失敗時：

`public_claim_gate=FAIL`

不得對外宣稱提升。

## 7) 回報格式
每次 closeout 必附：

```json
{
  "commit_sha": "<sha>",
  "semantic_audit": {
    "state": "VERIFIED/PARTIAL/REJECTED/UNVERIFIED",
    "failures": []
  },
  "nexus_wearing": {
    "model_calls": 0,
    "model_uses_nexus": false,
    "nexus_context_delivered": false,
    "nexus_usage_valid": false
  },
  "capability_receipts": {
    "public_safe": [],
    "selected_only": [],
    "failures": []
  },
  "gate_summary": {
    "delivery_gate": "PASS/FAIL/NOT_RUN",
    "acceptance_check": "PASS/FAIL/NOT_RUN",
    "contract_check": "PASS/FAIL/NOT_RUN",
    "ci_gate": "PASS/FAIL/NOT_RUN",
    "public_claim_gate": "PASS/FAIL/NOT_APPLICABLE"
  },
  "report_file": "<absolute-path>",
  "commands": [
    {
      "cmd": "<command>",
      "exit_code": 0,
      "evidence": "<key output or report path>"
    }
  ],
  "recovery_directive": "none/stateless_pivot/report_trust_probe/route_replan"
}
```

結尾：

`[NEXUS IDENTITY: <SHA> + v2.9 RUNTIME-ALIGNED]`
