# memory_ab_tasks_v3

24 fixtures = 12 bug classes x 2 variants (`-a`, `-b`). Each variant of a class shares the same
underlying pitfall but uses a different domain and different identifiers, so a lesson learned on
`-a` should transfer to `-b`.

Layout per task: `task.json` (id, bug_class, variant, problem_statement, target_file, repro_file),
one buggy target module, and `repro.py`. `repro.py` raises an uncaught `AssertionError` while the
bug exists and exits 0 once fixed. Stdlib only, deterministic, 3-5 assertions each, and the
problem statement describes the symptom only.

Verify red: `python scripts/eval/verify_fixtures.py --tasks-dir scripts/eval/memory_ab_tasks_v3`

| # | bug_class | Pitfall | a (domain, target) | b (domain, target) |
|---|-----------|---------|--------------------|--------------------|
| 1 | timezone_naive_aware | Comparing offset-naive and offset-aware datetimes | Flight departures, `departures.py` (`next_departure`) | Lease windows, `leases.py` (`active_leases`) |
| 2 | consumed_iterator | Reading a generator/iterator twice | Parcel manifest, `manifest.py` (`summarize`) | Sensor readings, `sensor_log.py` (`describe`) |
| 3 | float_money_rounding | Float money; tax rounded to the cent (half-even) before adding | Invoice total with tax, `invoice.py` (`invoice_total`) | Fare split across riders, `fare_split.py` (`split_fare`) |
| 4 | greedy_regex_multiline | Greedy or DOTALL regex running across lines | INI section headers, `ini_sections.py` (`section_names`) | Template placeholders, `templates.py` (`placeholders`) |
| 5 | mutate_while_iterating | Mutating a list or dict during iteration | Stock list pruning, `stock.py` (`drop_stale`) | Session dict expiry, `sessions.py` (`expire_sessions`) |
| 6 | recursive_base_case | Missing base case for empty containers and tuples | Nested number sum, `tally.py` (`deep_sum`) | Menu tree depth, `menu_tree.py` (`tree_depth`) |
| 7 | encoding_bytes_str | str vs bytes mixing when hashing or joining | Webhook HMAC signature, `webhook_sig.py` (`sign`) | Cache-key fingerprint, `cache_key.py` (`fingerprint`) |
| 8 | shallow_copy_nested | Shallow copy leaking nested mutations (and shallow merge) | Profile defaults merge, `profiles.py` (`build_profile`) | Board snapshot and undo, `board.py` (`snapshot`, `History`) |
| 9 | bit_width_overflow | Unbounded ints where a fixed width (32/64-bit) is required | FNV-1a 32-bit hash, `fnv.py` (`fnv1a32`) | 64-bit id packing, `ids.py` (`pack_id`, `unpack_id`) |
| 10 | sort_none_key | Sorting with None values (TypeError), tie order | Leaderboard ranking, `leaderboard.py` (`rank`) | File listing by modified date, `listing.py` (`order_files`) |
| 11 | exception_swallowing | Broad `except` hiding the real error and returning a default | Config port parsing, `settings.py` (`load_port`) | Profile store lookup, `profiles_store.py` (`load_profile`) |
| 12 | off_by_one_half_open | Off-by-one in half-open ranges with a remainder | Chunking into pages, `pager.py` (`chunk_ranges`) | Page slice, `paging.py` (`page_slice`) |
