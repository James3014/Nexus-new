# 🛡️ Nexus Enforced Launch Guide
1. Run `bash scripts/ops/_nexus_preflight.sh`
2. Delegated Gemini round (Nexus-enforced preamble auto-injected):
   - `bash scripts/ops/run_gemini_nexus_round.sh /tmp/task.md .nexus/reports/gemini_round.json 240`
3. One-command launch wrapper:
   - `bash scripts/ops/start_gemini_nexus_enforced.sh /tmp/task.md .nexus/reports/gemini_round.json 240`
4. Use `uv run scripts/engine/nexus_cli.py` for all local Nexus tasks and gates.
