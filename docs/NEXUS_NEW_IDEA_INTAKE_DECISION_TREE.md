# Nexus 新構想 Intake + Decision Tree v1

## 使用時機
當你提出任何新的 Nexus 本體構想（功能、重構、治理、知識、runtime）時，先走本流程，再決定是否進實作。

## 一句話提案格式（你只要丟這行）
新構想：<想做的事>；風險：<low|medium|high|unknown>；範圍：<可改/禁改>；期限：<date>

## Step 1: Task Intent（Orchestrator 填）
- task_id:
- intent_summary:
- change_type: feature|refactor|governance|runtime|knowledge
- touched_domains:
- suspected_risk: low|medium|high

## Step 2: Owner Routing（單一 owner）
- primary_owner: exactly one
- consulted_agents: up to 2
- human_verdict_required: yes/no

## Step 3: Proposal Gate Decision
若符合任一條件，proposal_required = yes：
1. 觸及 core 邊界或 PXDRAC。
2. 變更 acceptance/audit/closeout。
3. 影響 wiki 真值、ADR、lineage。
4. 影響 CLI/swarm/worktree/runtime。
5. 需要多 agent 協作。
6. rollback 路徑不明。

## Step 4: ADR Gate
- high risk 必查 ADR
- 若推翻既有 ADR，必附新證據（測試或 A/B）

## Step 5: Proposal Card（若 required）
```md
- proposal_id:
- owner_agent:
- consulted_agents:
- affected_components:
- problem_statement:
- adr_checked:
- risk_level:
- rollback_plan:
- evidence_plan:
- wiki_impact:
- acceptance_criteria:
```

## Step 6: Isolated Execution Policy
- low risk: baseline isolation
- medium/high risk: worktree 或 .nexus-swarm-* 隔離環境
- enforced launch + preflight required

## Step 7: Acceptance Gate
完成宣告必附 evidence bundle：
- code_artifacts
- test_artifacts
- command_artifacts
然後執行 acceptance-check。

## Step 8: Writeback + Promotion
- 若有架構/治理/知識變更：同步 wiki/changelog
- 若退件或失敗：寫 lesson writeback + prevention rule
- 最後由 Human Maintainer 下 promotion verdict

## 決策樹（文字版）
1. 新構想進來 → 分類 change_type
2. 是否跨域或高風險？
   - 否 → 直接隔離實作
   - 是 → Proposal Card
3. 是否 high-risk？
   - 是 → ADR check
4. 實作完成後 evidence 是否完整？
   - 否 → RETURN
   - 是 → acceptance-check
5. acceptance-check 通過？
   - 否 → RETURN/BLOCK + lesson writeback
   - 是 → wiki/changelog 同步檢查
6. 同步完成？
   - 否 → RETURN
   - 是 → 送 Human verdict
7. Human verdict = approve?
   - 否 → hold/rollback
   - 是 → promotion
