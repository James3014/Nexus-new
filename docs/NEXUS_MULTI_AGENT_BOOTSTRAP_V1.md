# Nexus Multi-Agent Bootstrap v1

## 啟動目標
以「你 = 最終裁決、Hermes = 主控 Orchestrator」模式啟動。

## 角色配置（v1）
- 常駐：Chief Orchestrator、Guardrail、Kernel Refactor
- 顧問：Knowledge & Memory、Runtime & Fleet
- Final Verdict：Human Maintainer

## 今日就能執行的啟動步驟
1. 建立任務 Intake（每個任務只允許一個 owner）。
2. 跨域任務先填 Proposal Card，未提案不動工。
3. Owner 在隔離 worktree/shadow 執行。
4. 交由 Guardrail 檢查 acceptance + evidence bundle。
5. 若有失敗，當日做 lesson writeback。
6. 由 Human Maintainer 給最終 promote verdict。

## 模板 A：任務單（Intake Card）
```md
- task_id:
- title:
- primary_domain:
- owner_agent:
- consulted_agents: []
- risk_level: low|medium|high
- cross_domain: yes|no
- done_definition:
- deadline:
```

## 模板 B：Proposal Card（跨域必填）
```md
- proposal_id:
- owner_agent:
- consulted_agents:
- affected_components:
- problem_statement:
- adr_checked: yes|no (link)
- risk_level: low|medium|high
- rollback_plan:
- evidence_plan:
- wiki_impact: none|required
- acceptance_criteria:
```

## 模板 C：Closeout / Evidence Bundle
```md
- task_id:
- verdict: PASS|RETURN|BLOCK
- code_artifacts:
- test_artifacts:
- command_artifacts:
- wiki_sync: n/a|done|required-but-missing
- rollback_ready: yes|no
- residual_risks:
```

## 每日節奏（15 分鐘）
- 09:00：Orchestrator intake + routing
- 17:30：Guardrail closeout + failure writeback check

## 每週節奏（30 分鐘）
- core 膨脹檢視（Kernel Refactor）
- code/wiki drift audit（Knowledge）
- worktree hygiene（Runtime）
- 重複故障 → prevention rules（Guardrail）

## 配套 Skills（已建立）
- devops/nexus-chief-orchestrator-routing
- devops/nexus-proposal-card-protocol
- devops/nexus-acceptance-evidence-gate
- devops/nexus-lesson-writeback-loop
- devops/nexus-new-idea-intake-decision-tree

## 配套流程文件
- docs/NEXUS_NEW_IDEA_INTAKE_DECISION_TREE.md
