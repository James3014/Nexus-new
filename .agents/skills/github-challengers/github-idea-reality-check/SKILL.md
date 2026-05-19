---
name: github-idea-reality-check
description: 當使用者要求 Nexus 執行 forecast_pregate, research, research_control_plane, or benchmark_meta_opt work that needs build-vs-buy prior-art checks, competitor discovery, or idea feasibility screening. Do not use as a runtime MCP tool unless external network and token boundaries are separately approved.
metadata: {"source_repo":"https://github.com/mnemox-ai/idea-reality-mcp","source_commit":"6929fe531a28ca11957628f805beb07aeae9968b","source_status":"external_challenger","runtime_eligible":false,"ablation_eligible":true}
---

# Idea Reality Check

## When to use
- Starting a new project or side project
- Evaluating whether to build or buy
- Researching competitors before a sprint
- Validating a feature idea before implementation

## Instructions
1. Ask the user for a natural-language description of their idea
2. Call the `idea_check` MCP tool with the idea text
3. Use `depth="quick"` for fast checks (GitHub + HN), `depth="deep"` for comprehensive analysis (all 5 sources)
4. Present the reality_signal score (0-100) and interpret it:
   - **0-30**: Low competition — green light to build
   - **31-60**: Moderate competition — differentiation needed
   - **61-80**: High competition — find a niche or pivot
   - **81-100**: Very high competition — consider contributing to existing projects instead
5. List the top 3 competitors with star counts and descriptions
6. Share the pivot_hints for actionable next steps
