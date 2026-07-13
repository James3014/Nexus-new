# M4 agy Real Cloud-Local Runtime Evidence

## Result

`CLOUD_CANDIDATE_VERIFIED`

The bounded smoke used only the local `agy` CLI with a public `/tmp` fixture. It did not invoke Gemini CLI and did not pass an API-key environment variable to the subprocess.

## Evidence

| Field | Observed value |
| :--- | :--- |
| task_id | `m4-agy-real-cloud-local-20260713` |
| provider | `agy` |
| response_identity | `Antigravity` |
| candidate | unified diff changing `return 1` to `return 2` |
| stage 1 | bounded local diagnosis succeeded |
| stage 2 | provider call confirmed; real cloud call true |
| stage 3 | isolated apply succeeded; selected/applied hash matched |
| stage 3 verifier | exit code `0` |
| formal workspace mutated | `false` |
| route truth source | `CapabilityPlanner` |

The isolated workspace path and candidate hash are retained in the smoke receipt under `/tmp/nexus-universal-local-assist-smoke-20260713/agy_stage_chain_result.json`. The receipt contains no credential material.

## Claim boundary

This proves the provider-neutral cloud-local runtime path for one bounded public fixture. It does not prove contribution, value, generalization, production readiness, or a public solve-rate claim. Those remain governed by the final gate and value matrix.
