"""Redacted excerpts of live Agy calls used by test_agy_outcome_classification.

Kept as Python data so the exact-base impact gate maps them to their tests.
stdout/stderr are verbatim; logs keep only model-identity, conversation and
timeout lines. Checked by test_fixtures_hold_no_account_data_or_secrets.
"""

from __future__ import annotations

AGY_OUTCOME_FIXTURES: dict[tuple[str, str], str] = {
    (
        "denied_command",
        "agylog.txt",
    ): 'I1013 10:36:21.492269       1 model_resolver.go:93] Resolving model gemini-3.8-flash-medium\nI1013 10:36:21.492300       1 model_config_manager.go:328] Propagating selected model override to backend: label="Gemini 3.8 Flash (Medium)"\nI1013 10:36:22.546810       1 server.go:1278] Created conversation 628a20ea-a1d0-4dbf-b7b6-95ae4a94dbfd\n',
    (
        "denied_command",
        "stderr",
    ): 'jetski: no output produced — a tool required the "command" permission that headless mode cannot prompt for, so it was auto-denied. Add an allow-rule under permissions.allow in settings.json (e.g. command(<target>)). Alternatively, re-run with --dangerously-skip-permissions to auto-approve all tools.\n',
    (
        "denied_command",
        "stdout",
    ): '{"conversation_id":"628a20ea-a1d0-4dbf-b7b6-95ae4a94dbfd","status":"SUCCESS","response":"","duration_seconds":7.32631,"num_turns":1,"usage":{"input_tokens":13558,"output_tokens":604,"thinking_tokens":484,"cache_read_tokens":0,"total_tokens":14162},"denied_actions":[{"action":"command","display_name":"RunCommand"}]}\n',
    (
        "denied_read_file",
        "agylog.txt",
    ): 'I1013 10:38:06.315189       1 model_resolver.go:93] Resolving model gemini-3.8-flash-medium\nI1013 10:38:06.315216       1 model_config_manager.go:328] Propagating selected model override to backend: label="Gemini 3.8 Flash (Medium)"\nI1013 10:38:08.118480       1 server.go:1278] Created conversation 8e0ba609-d018-4021-92a3-bdc50fac61b3\n',
    (
        "denied_read_file",
        "stderr",
    ): 'jetski: no output produced — a tool required the "read_file" permission that headless mode cannot prompt for, so it was auto-denied. Add an allow-rule under permissions.allow in settings.json (e.g. read_file(<target>)). Alternatively, re-run with --dangerously-skip-permissions to auto-approve all tools.\n',
    (
        "denied_read_file",
        "stdout",
    ): '{"conversation_id":"8e0ba609-d018-4021-92a3-bdc50fac61b3","status":"SUCCESS","response":"","duration_seconds":5.5287939999999995,"num_turns":1,"usage":{"input_tokens":13560,"output_tokens":619,"thinking_tokens":565,"cache_read_tokens":0,"total_tokens":14179},"denied_actions":[{"action":"read_file","display_name":"ViewFile"}]}\n',
    (
        "print_timeout",
        "agylog.txt",
    ): 'I1013 10:40:01.109309       1 model_resolver.go:93] Resolving model gemini-3.8-flash-medium\nI1013 10:40:01.109340       1 model_config_manager.go:328] Propagating selected model override to backend: label="Gemini 3.8 Flash (Medium)"\nI1013 10:40:02.013098       1 server.go:1278] Created conversation 456eeb10-6ec6-4767-99e1-978ca8910fb1\nW1013 10:40:07.041287       1 poll.go:188] Print mode: print timeout after 5s with turn in progress after 194 polls (printed=1)\n',
    (
        "print_timeout",
        "stderr",
    ): "[agy] print timeout after 5s with turn in progress; returning partial output\n",
    (
        "print_timeout",
        "stdout",
    ): '{"conversation_id":"456eeb10-6ec6-4767-99e1-978ca8910fb1","status":"SUCCESS","response":"","duration_seconds":0,"num_turns":1,"usage":{"input_tokens":0,"output_tokens":0,"thinking_tokens":0,"cache_read_tokens":0,"total_tokens":0}}\n',
    (
        "print_timeout_2",
        "agylog.txt",
    ): 'I1013 10:40:08.820518       1 model_resolver.go:93] Resolving model gemini-3.8-flash-medium\nI1013 10:40:08.820550       1 model_config_manager.go:328] Propagating selected model override to backend: label="Gemini 3.8 Flash (Medium)"\nI1013 10:40:09.723658       1 server.go:1278] Created conversation 618ffbe0-fbd4-46b5-bf83-2f3bfdb91130\nW1013 10:40:14.729954       1 poll.go:188] Print mode: print timeout after 5s with turn in progress after 193 polls (printed=1)\n',
    (
        "print_timeout_2",
        "stderr",
    ): "[agy] print timeout after 5s with turn in progress; returning partial output\n",
    (
        "print_timeout_2",
        "stdout",
    ): '{"conversation_id":"618ffbe0-fbd4-46b5-bf83-2f3bfdb91130","status":"SUCCESS","response":"","duration_seconds":0,"num_turns":1,"usage":{"input_tokens":0,"output_tokens":0,"thinking_tokens":0,"cache_read_tokens":0,"total_tokens":0}}\n',
    (
        "quota_1362_empty_success",
        "agylog.txt",
    ): 'I1013 10:35:57.951525       1 model_resolver.go:93] Resolving model gemini-3.8-flash-medium\nI1013 10:35:57.951562       1 model_config_manager.go:328] Propagating selected model override to backend: label="Gemini 3.8 Flash (Medium)"\nI1008 09:14:01.000000   4242 server.go:1263] Created conversation 11111111-2222-3333-4444-555555555555\nE1008 09:14:03.512204   4242 errorreport.go:224] agent executor error: pre-invocation hook: context summarization: RESOURCE_EXHAUSTED (code 429): Individual quota reached.\n',
    ("quota_1362_empty_success", "stderr"): "",
    (
        "quota_1362_empty_success",
        "stdout",
    ): '{"conversation_id":"11111111-2222-3333-4444-555555555555","status":"SUCCESS","response":"","duration_seconds":0,"num_turns":1,"usage":{"input_tokens":0,"output_tokens":0,"thinking_tokens":0,"cache_read_tokens":0,"total_tokens":0}}\n',
    (
        "success_patch_json",
        "agylog.txt",
    ): 'I1013 10:38:35.641140       1 model_resolver.go:93] Resolving model gemini-3.8-flash-medium\nI1013 10:38:35.641235       1 model_config_manager.go:328] Propagating selected model override to backend: label="Gemini 3.8 Flash (Medium)"\nI1013 10:38:37.346696       1 server.go:1278] Created conversation c65f3dff-c130-4929-b358-c60f941ca230\n',
    ("success_patch_json", "stderr"): "",
    (
        "success_patch_json",
        "stdout",
    ): '{"conversation_id":"c65f3dff-c130-4929-b358-c60f941ca230","status":"SUCCESS","response":"{\\"status\\": \\"OK\\", \\"patch\\": \\"--- a/calc.py\\\\n+++ b/calc.py\\\\n@@ -1 +1 @@\\\\n-def add(a, b): return a - b\\\\n+def add(a, b): return a + b\\\\n\\"}\\n","duration_seconds":18.150252,"num_turns":1,"usage":{"input_tokens":13595,"output_tokens":2470,"thinking_tokens":2407,"cache_read_tokens":0,"total_tokens":16065}}\n',
    (
        "success_plain_text",
        "agylog.txt",
    ): 'I1013 10:35:57.951525       1 model_resolver.go:93] Resolving model gemini-3.8-flash-medium\nI1013 10:35:57.951562       1 model_config_manager.go:328] Propagating selected model override to backend: label="Gemini 3.8 Flash (Medium)"\nI1013 10:35:59.610368       1 server.go:1278] Created conversation a014dc72-92f3-40e1-8585-36be7dcc894e\n',
    ("success_plain_text", "stderr"): "",
    (
        "success_plain_text",
        "stdout",
    ): '{"conversation_id":"a014dc72-92f3-40e1-8585-36be7dcc894e","status":"SUCCESS","response":"OK\\n","duration_seconds":15.670341,"num_turns":1,"usage":{"input_tokens":13561,"output_tokens":1636,"thinking_tokens":1635,"cache_read_tokens":0,"total_tokens":15197}}\n',
}
