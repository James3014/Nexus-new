---
last_compiled: 2026-04-06
owner: agent
status: active
tags:
- ops
- wiki
- governance
- evaluation
- regression
title: Ops - Wiki Regression Evals
type: governance
version_scope:
- v23
---



# Ops - Wiki Regression Evals

## One-sentence summary
本文件定義 Nexus Wiki 知識庫的自動化回歸測試題目與驗證邏輯，確保關鍵治理知識在更新過程中不丟失、不漂移。 [Source: scripts/ops/wiki_eval_regression.py]

## Role / responsibility
- **知識完整性**: 確保核心組件、流程與政策的描述符合預期。
- **證據鏈驗證**: 強制要求頁面必須包含 `[source: scripts/ops/ci_gate.py]` 或 `[code: scripts/ops/ci_gate.py]` 證據標籤。
- **防止漂移**: 透過關鍵字與錨點檢查，偵測 Wiki 內容的非預期變更。

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 總體治理入口。

## Downstream
- **[[scripts/ops/scripts/ops/ci_gate.py]]**: 作為 [CI gate](Ops - CI/CD Promotion Gate.md) 的一部分執行。

## Related modules / files
- `scripts/ops/wiki_eval_regression.py`
- `.nexus/reports/wiki_eval_report.json`

## Regression Questions (Fixed Governance Suite)

| ID | Domain | Question | Target Page | Required Keywords / Anchors |
|:---|:---|:---|:---|:---|
| Q01 | System | What is the core mission of Nexus? | [System Overview](../00_Home/System Overview.md) | "Nexus", "Swarm", "P-X-D-R-A-C" |
| Q02 | Ops | What are the mandatory frontmatter keys? | [Ops - Wiki Page Type Contracts](Ops - Wiki Page Type Contracts.md) | "title:", "type:", "status:", "owner:" |
| Q03 | Ops | What is the query writeback policy? | [Ops - Query Writeback Policy](Ops - Query Writeback Policy.md) | "query_context", "evidence_link", "confidence_score" |
| Q04 | Flow | How is [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] runtime triggered? | [Flow - PXDRAC Runtime](../03_Flows/Flow - PXDRAC Runtime.md) | "nexus_cli.py", "[[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]]" |
| Q05 | Gov | How are waivers approved? | [Ops - Provenance Exceptions and Waivers](Ops - Provenance Exceptions and Waivers.md) | "expiry", "id" |
| Q06 | CI | What triggers a CI-BLOCK? | scripts/ops/scripts/ops/ci_gate.py | "P0 drift", "enforce-level", "VENV_PYTHON" |
| Q07 | Truth | How are [truth claims](Ops - Truth Claims Register.md) registered? | [Ops - Truth Claims Register](Ops - Truth Claims Register.md) | "ID", "Claim", "Status", "Source" |
| Q08 | Module | What is the [Dual Phase Diagnosis](../02_Modules/Module - Dual Phase Diagnosis.md)? | [Module - Dual Phase Diagnosis](../02_Modules/Module - Dual Phase Diagnosis.md) | "Phase", "Diagnosis" |
| Q09 | Protocol | What is the CLI surface contract? | [Protocol - CLI Surface](../05_Protocols/Protocol - CLI Surface.md) | "nexus" |
| Q10 | Onboard | What is the Agent [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]]]]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]]]]]]]]]? | [Agent Onboarding - Command Pack](../00_Home/Agent Onboarding - Command Pack.md) | "uv run", "scripts", "commands" |
| Q11 | State | How are state transitions documented? | 04_State/[State - Lifecycle](../04_State/State - Lifecycle.md).md | "轉移", "State" |
| Q12 | Roadmap | What is the Roadmap overview? | 09_Roadmap/[Phase 6 - Nexus Hardening](../09_Roadmap/Phase 6 - Nexus Hardening.md).md | "Hardening", "Governance", "Wiki" |
| Q13 | Incidents | What is the CI failure playbook? | [Ops - CI Failure Playbook](Ops - CI Failure Playbook.md) | "RCA" |
| Q14 | SLO | What is the target SLO for wiki review? | [Ops - Ownership and Review SLA](Ops - Ownership and Review SLA.md) | "SLA", "Review" |
| Q15 | Audit | How is capability coverage calculated? | scripts/ops/wiki_capability_coverage_audit.py | "risk_weight", "weighted_score" |
| Q16 | Schema | What is the [AGENT_SCHEMA](../nexus_wiki_vault/99_Schema/AGENT_SCHEMA.md)? | 99_Schema/[AGENT_SCHEMA](../nexus_wiki_vault/99_Schema/AGENT_SCHEMA.md).md | "schema" |
| Q17 | Learning | How is learning velocity calculated? | scripts/ops/calc_learning_velocity.py | "velocity", "learning" |
| Q18 | Sync | How are nodes synchronized? | scripts/ops/start_index_sync_daemon.sh | "scheduler" |
| Q19 | Provenance | What is a source provenance tag? | [Ops - Artifact Retention and Provenance](Ops - Artifact Retention and Provenance.md) | "source", "provenance", "tag" |
| Q20 | Metrics | How are conversation metrics tracked? | scripts/ops/write_phase_metrics.py | "metrics", "phase" |

## Source notes
- Nexus v23 Governance Enforcement Specifications
- Automated Regression Policy [v1.0]

## Open questions / conflicts
- [ ] 如何動態增加回歸測試案例而不影響 CI 穩定性。

---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]