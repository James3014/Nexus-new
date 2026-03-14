PHASES: P,D,R
TRIGGERS: memory, recall, lessons, reminder, hydration, deps, strike
DESCRIPTION: 統一四源 (.codex_lessons, crystal.jsonl, tracelog, patterns) 到 LanceDB，per-round RAG top-3 reminders。
OUTPUT SCHEMA: reminders.json {"reminders": [{"source": str, "content": any, "relevance": float}], "total_sources": int}
NEGATIVE: 無 relevance <0.7，限 3 項防噪音。
HOOK: Context Hub pre-phase 注入。
