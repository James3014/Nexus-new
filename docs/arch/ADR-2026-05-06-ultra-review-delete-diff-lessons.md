# ADR: UltraReview logic repro must distinguish deletions from mirror loss

## Status

Accepted

## Context

The full route smoke invoked UltraReview successfully, but its dry gate failed
because the logic breaker treated a deleted file as a missing sandbox mirror
file. Git deletion diffs keep the same `diff --git a/path b/path` header while
the file is expected not to exist after applying the diff.

## Decision

The UltraReview logic repro now detects `deleted file mode` blocks and does not
require deleted paths to exist in the sandbox mirror.

## Consequences

UltraReview still fails closed when a changed file is missing unexpectedly, but
legitimate deletions no longer block route receipt public-safety gates.

## Lesson

Filesystem existence checks need to understand patch semantics. A deleted file
is successful application evidence, not missing evidence.
