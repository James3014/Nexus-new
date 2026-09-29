# TRAJECTORY_VERIFIER_EXPERIMENT_REPORT

1. Experiment identity
NEXUS_SYSTEM_ONE_CLM_V2 / TRACK_1_TRAJECTORY_VERIFIER_HEAD. AUTO_CHAIN=false. Claim ceiling: EXPERIMENTAL_SHADOW_ONLY.

2. Current source revision
Canonical GitHub main: `57edae9832392e3e369ee039b2e12f18b8c433df`. Active gateway reports deployed source `a316448de6b056a9ba1be910ac5f97a49afe2452` and upstream freshness STALE. Dirty local checkouts were not treated as current-main authority.

3. Corpus manifest
Audited live candidate evidence: 1 complete group, 2 rows, 1 task, 0 eligible rows. No trajectory training corpus was formed. R01-R10, Candidate A/B evidence, historical oracle/fix identities, ranking blind v2, and 30 decision cases are frozen in `FINAL_HOLDOUT_DO_NOT_TRAIN.json`.

4. Label provenance
The live group contains only CRITIC_AGGREGATE rows. Current main also has seams capable of ISOLATED_VERIFIER and MECHANICAL_GATE labels, but no eligible live rows were present in the audited active store.

5. Leakage audit
No audited evidence surface provides a complete ordered pre-action state snapshot for each agent step. Runtime receipts are stage summaries. Reconstructing earlier state from final receipts would risk future leakage.

6. Task-family split
Unavailable. With zero strong-label trainable trajectories, neither task-disjoint nor family-disjoint train/dev splitting is possible.
7. Representation format
Target representation remains state-at-time-t plus exact next action. It was not instantiated because leakage-safe step boundaries are missing.

8. CLM head architecture
NOT TRAINED. Frozen Qwen3-8B encoder plus a small Nexus-specific head remains the bounded proposal. Backbone tuning was not performed.

9. Training parameters
NOT RUN. No V2 training checkpoint or parameter set exists because T1 blocked training.

10. Aggregation experiment
NOT RUN. final-step, mean, minimum, and tail-k aggregation remain blocked until a valid development corpus exists.
11. Anti-anchor baselines
NOT RUN. No cached reranker directory was found in the audited host cache. Ollama returned no local model inventory. No baseline environment change was made.

12. Dev metrics
NOT RUN. No valid development split exists.

13. Untouched holdout metrics
NOT RUN by design. The 10 historical replay tasks remain sealed until development choices are frozen.

14. Robustness
NOT RUN. Representation and permutation robustness cannot be evaluated without a trained scorer and valid corpus.
15. Reviewer-saving simulation
NOT RUN. There is no qualified trajectory scorer for Top-1/Top-2 reviewer simulation.

16. Latency / RAM
Full V2 runtime benchmark NOT RUN because the quality gate was never reached. Phase-0 timings remain historical only.

17. Failure cases
Primary failure is corpus readiness: zero strong-label live rows and no leakage-safe ordered state/action trajectory. Active gateway source is also stale relative to current main, so source and runtime evidence are reported separately.

18. Exact Gate results
T0 current-state audit: completed with source/runtime drift recorded. T1 task-disjoint trajectory corpus: FAIL. Stop condition 1 triggered because a task-disjoint split is impossible. The only live group is critic-derived and cannot supply strong PASS/FAIL truth. T2-T9 were not run.
19. Maximum supportable claim
Current Nexus evidence infrastructure can preserve candidate-group evidence and current main contains seams capable of strong verifier labels, but the audited live corpus is insufficient to train or evaluate a Nexus-specific Trajectory Verifier Head without leakage or invalid label promotion.

20. Recommended next action
Use only the minimum passive trajectory sidecar described in `TRAJECTORY_CORPUS_READINESS_REPORT.md`. Accumulate real, verifier-backed, multi-task and multi-family trajectories, then rerun T1. Do not train the head before that gate passes.

Asset identity appendix
CLM asset root: `/Users/james/workspace/gpt/CLM-MLX8-meta`.
config.json SHA256 `e7bc34bdc5aa9163a4d45d6ff2a2e02924e0c9b4354a8f0560aa444c33a541c6`.
tokenizer.json SHA256 `be75606093db2094d7cd20f3c2f385c212750648bd6ea4fb2bf507a6a4c55506`.
quantization.json SHA256 `4d86ae608211ed3f24fe1b0e612ae2e3b1f39cb171152b8fd89eda6139af2350`.
heads/config.json SHA256 `f6d45bb2e3546e1027f0146d2a96304cedd7064ba5c4c4770c61f5e97a3ca70a`.
CLM head weights SHA256 `6abdda23dab728a5195705e6d1299ab123d4f26a7a089527e32b0d6cdf95d854`.
Backbone shard 1 SHA256 `413208fcf9eae187ab68426b5330074690a3768ea1c2deb9f560e7900e15d7dd`.
Backbone shard 2 SHA256 `8eab5c854430ac89e2b0a17d89e674129f91dedb5b27d82a45bd7aca49033a70`.
Isolated Python env exists with Python 3.13.15 and mlx_lm 0.31.3.

Final verdict: **TRAJECTORY_VERIFIER_INCONCLUSIVE_MORE_DATA_REQUIRED**.
Missing evidence: ordered pre-action state/action/result steps plus final strong verifier-backed PASS/FAIL bindings across enough independent tasks/families to permit task-disjoint evaluation.
