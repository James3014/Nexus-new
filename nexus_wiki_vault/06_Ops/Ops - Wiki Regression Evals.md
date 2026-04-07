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
- **證據鏈驗證**: 強制要求頁面必須包含 `[source: ci_gate.py]` 或 `[code: ci_gate.py]` 證據標籤。
- **防止漂移**: 透過關鍵字與錨點檢查，偵測 Wiki 內容的非預期變更。

## Upstream
- **[[System Overview]]**: 總體治理入口。

## Downstream
- **[[scripts/ops/ci_gate.py]]**: 作為 [[CD Promotion Gate|CI gate]] 的一部分執行。

## Related modules / files
- `scripts/ops/wiki_eval_regression.py`
- `.nexus/reports/wiki_eval_report.json`

## Regression Questions (Fixed Governance Suite)

| ID | Domain | Question | Target Page | Required Keywords / Anchors |
|:---|:---|:---|:---|:---|
| Q01 | System | What is the core mission of Nexus? | [[System Overview]] | "Nexus", "Swarm", "P-X-D-R-A-C" |
| Q02 | Ops | What are the mandatory frontmatter keys? | [[Ops - Wiki Page Type Contracts]] | "title:", "type:", "status:", "owner:" |
| Q03 | Ops | What is the query writeback policy? | [[Ops - Query Writeback Policy]] | "query_context", "evidence_link", "confidence_score" |
| Q04 | Flow | How is [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] runtime triggered? | [[Flow - PXDRAC Runtime]] | "nexus_cli.py", "[[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]]" |
| Q05 | Gov | How are waivers approved? | [[Ops - Provenance Exceptions and Waivers]] | "expiry", "id" |
| Q06 | CI | What triggers a CI-BLOCK? | scripts/ops/ci_gate.py | "P0 drift", "enforce-level", "VENV_PYTHON" |
| Q07 | Truth | How are [[Ops - Truth Claims Register|truth claims]] registered? | [[Ops - Truth Claims Register]] | "ID", "Claim", "Status", "Source" |
| Q08 | Module | What is the [[Module - Dual Phase Diagnosis|Dual Phase Diagnosis]]? | [[Module - Dual Phase Diagnosis]] | "Phase", "Diagnosis" |
| Q09 | Protocol | What is the CLI surface contract? | [[Protocol - CLI Surface]] | "nexus" |
| Q10 | Onboard | What is the Agent [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]]]]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - [[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]|[[Agent [[Agent Onboarding - Command Pack|Onboarding]] - Command Pack|Command Pack]]]]]]]]]]]]? | [[Agent Onboarding - Command Pack]] | "uv run", "scripts", "commands" |
| Q11 | State | How are state transitions documented? | 04_State/[[State - Lifecycle]].md | "轉移", "State" |
| Q12 | Roadmap | What is the Roadmap overview? | 09_Roadmap/[[Phase 6 - Nexus Hardening]].md | "Hardening", "Governance", "Wiki" |
| Q13 | Incidents | What is the CI failure playbook? | [[Ops - CI Failure Playbook]] | "RCA" |
| Q14 | SLO | What is the target SLO for wiki review? | [[Ops - Ownership and Review SLA]] | "SLA", "Review" |
| Q15 | Audit | How is capability coverage calculated? | scripts/ops/wiki_capability_coverage_audit.py | "risk_weight", "weighted_score" |
| Q16 | Schema | What is the [[AGENT_SCHEMA]]? | 99_Schema/[[AGENT_SCHEMA]].md | "schema" |
| Q17 | Learning | How is learning velocity calculated? | scripts/ops/calc_learning_velocity.py | "velocity", "learning" |
| Q18 | Sync | How are nodes synchronized? | scripts/ops/start_index_sync_daemon.sh | "scheduler" |
| Q19 | Provenance | What is a source provenance tag? | [[Ops - Artifact Retention and Provenance]] | "source", "provenance", "tag" |
| Q20 | Metrics | How are conversation metrics tracked? | scripts/ops/write_phase_metrics.py | "metrics", "phase" |

## Source notes
- Nexus v23 Governance Enforcement Specifications
- Automated Regression Policy [v1.0]

## Open questions / conflicts
- [ ] 如何動態增加回歸測試案例而不影響 CI 穩定性。