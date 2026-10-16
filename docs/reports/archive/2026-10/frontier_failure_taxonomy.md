# Frontier Failure Taxonomy v1.0

This document defines the failure classification for the Frontier Bug-Solving Loop using local Qwen2.5 models and the Nexus framework.

## 🛠️ Taxonomy Definitions

| Code | Name | Description |
| :--- | :--- | :--- |
| **R1** | `route_misfire` | Nexus router selected an inappropriate lane or model for the task context. |
| **R2** | `retrieval_miss` | Localization failed to identify the correct files or code sections. |
| **L1** | `localization_wrong` | Correct files found, but the specific line range or bug cause was misidentified. |
| **P1** | `patch_syntax_invalid` | Generated patch fails basic syntax checks (e.g., indentation, missing colons). |
| **P2** | `patch_semantic_wrong` | Patch is syntactically correct but does not fix the bug or introduces regressions. |
| **P3** | `prompt_over_budget` | Prompt length near or exceeds `num_ctx`, leaving no room for generation. |
| **P4** | `generation_headroom_exhausted` | LLM exhausted available token window before completing output, causing truncation. |
| **P5** | `no_blocks_found` | Parser failed to find valid SEARCH/REPLACE tags in the LLM output. |
| **V1** | `verification_gap` | Verification suite failed to detect that the patch was incorrect, or failed to run. |
| **T1** | `latency_over_budget` | Task execution exceeded the allocated time or token budget. |
| **A1** | `abstain_should_have_happened` | Model/Nexus should have abstained but attempted a low-confidence fix that failed. |
| **W1** | `whitelist_lane_misuse` | Task was routed to the whitelist deliberation lane but didn't meet the criteria. |
| **S1** | `unsupported_task_shape` | The task structure (e.g., massive repo-wide change) is outside current Nexus/Local capabilities. |

## 📊 Mapping to Root Causes

- **Model Issues**: P1, P2, A1
- **Nexus Runtime Issues**: R1, W1, T1
- **Pipeline Issues**: R2, L1, V1, S1
