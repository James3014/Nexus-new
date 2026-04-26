# 📜 Universal Agent Guidelines: READ MUSE_PROTO.md
# SCOPE: Antigravity, Gemini, OpenClaw, Codex, Claude.
# SSOT: ./MUSE_PROTO.md

## 🎯 Semantic Completion Criteria
- **Behavioral Integrity**: The requested functionality is verified through empirical testing.
- **Structural Soundness**: Changes adhere to the local codebase conventions and architectural patterns.
- **Documentation Alignment**: Supporting documentation and tests are updated to reflect the new state.

## 📊 Evidence Reporting Format
- **Change Log**: List of modified files and high-level summary of changes.
- **Verification Evidence**: Specific commands executed and their key outputs (e.g., test results, status checks).
- **Residual Debt**: Any known issues or follow-up tasks explicitly stated.

## 🛡️ Agent Capability Boundaries
- **allowed_paths**: Project root, scripts/ops/, nexus_wiki_vault/, docs/
- **forbidden_paths**: .obsidian/, benchmarks/, logs/, nexus_swarm/, packages/
- **max_files_touched**: 10 (Strict Limit for single task)

## 🔄 Failure-to-Lesson Writeback
- Every failure encountered during the task MUST be analyzed for a "lesson".
- These lessons MUST be written back to the corresponding "Learning Closure Matrix" or ADR before task finalization.

## 🤐 輸出壓縮協議 (bu-ketao)
- **禁用開場**: 禁止「好的」、「收到」、「我將...」。
- **禁用敘事**: 禁止解釋 Tool Call 過程。
- **禁用客套**: 禁止「希望能幫助你」、「隨時回報」。
- **數據優先**: 僅輸出 [任務] -> [數據] -> [證據]。
