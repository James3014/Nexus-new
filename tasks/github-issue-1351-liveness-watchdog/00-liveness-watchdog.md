# Issue #1351: Agy Progress Watchdog for Stream-Only and Zero-Effect Non-Progress

## Goal
Implement a bounded progress watchdog for Agy coding tasks so that operations producing stream activity without tool or effect progress do not burn quota indefinitely up to broad timeout.

## Key Changes
1. Stream activity ingestion: Ingest operation-local Agy stream evidence from attestation log (`streamGenerateContent?alt=sse`).
2. Structured tool activity ingestion: Bind provider conversation ID and parse tool events from provider-owned `transcript_full.jsonl`.
3. Bounded timeouts: Configure `provider_stall_seconds` and `stream_no_progress_seconds` for coding tasks (`mode == "accept-edits"` and `write_paths`).
4. Taxonomy: Classify zero-progress operations as `PROVIDER_STALLED` or `PROVIDER_STREAM_NO_PROGRESS`.
5. Non-coding tasks exemption: Preserve no-tool / exact-reply / reviewer operations without false positive termination.
6. Multi-session drainage: Drain transcripts across observed session IDs in order during session switches.
