# L2 static-flag fixture (Refs #2752)

`hard_cohort_subset.jsonl.gz`: 59 candidate patches from the #1196 round-20 HARD cohort
(`round20/data/PATCHES.jsonl`, sha256 912d616feb0a921508820720a28fc068ac63d656f595170a7661932901f47c3d).
Every unit passed the public gate; `label` is `wrong` (hidden oracle failed, a wrong accept) or `correct`
(oracle passed).

Selection: smallest-first within three strata (refined-flagged, iv1-only flagged, unflagged) so the subset keeps
both full-data flag rates and stays under 200 KB. IV1 tier: 20 of 41 wrong flagged = 48.8 %, 3 of 18 correct = 16.7 %
(full data 132/272 = 48.5 %, 3/20 = 15 %). Refined tier: 8 of 41 wrong = 19.5 %, 0 of 18 correct (full data 50/272 = 18.4 %,
0/20). Refined pins are computed inside the vendored mini tree (touched files only), which can only add literal flags. Per unit: `diff` (git-style unified diff against the task's HEAD tree),
`issue_text` (task statement), `intake_paths`, `base_files` (HEAD text of touched `.py` files),
`quoting_tests` (only the lines of existing HEAD tests that quote a candidate literal) and
`expect_flags` / `expect_refined` (checks each tier produced when the fixture was built; regression pins).
