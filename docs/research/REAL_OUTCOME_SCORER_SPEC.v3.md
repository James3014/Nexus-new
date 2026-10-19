# Real-Outcome Scorer Specification v3

**v3 = the rules a task would otherwise use + one §8 env rule (A10).** Those rules are v1
(`docs/research/REAL_OUTCOME_SCORER_SPEC.md`, sha256
`315d95de21ea7ec82c97bf80165feaa052cb8a36fe99f3a1072d45ff74bb2bda`), or v2
(`docs/research/REAL_OUTCOME_SCORER_SPEC.v2.md`, sha256
`d380d885cf96f0aa2b0a9c320a3146697974ee84a94d2c69bc299586132cf539`) for a task whose GOLD
needs the A5 GOLD port fallback. Both files stay byte-identical. Every v1 and v2 rule
applies in v3 unless the rule below says otherwise. The amendment notes
(`REAL_OUTCOME_SCORER_SPEC.amendments.md`, A1–A10) apply to v3 too.

This file is frozen once merged. A later rule change needs a v4 file.

## Status: post hoc, not pre-registered, opt-in

The rule was designed **after** the V12 replay showed the problem (Issue #2709). So v3
results are **not pre-registered evidence**, and they are always reported apart from v1
and v2:

- v3 is opt-in: `--spec-version v3` on the CLI (`spec_version="v3"` on `ScoreContext`
  and `UvEnvProvider`). The default, `--spec-version v1`, scores exactly as scorer 1.2.4
  did: v1, with the v2 fallback for the tasks that need it. Its env build, pytest
  command, pytest environment, cache-key formulas and receipt fields are unchanged.
- Every receipt written under v3 records `spec_version: "v3"` and this file's sha256 in
  `spec_sha256`, whether or not the A5 fallback was needed. `spec_v3_base_rules`
  records the rule set v3 built on for that task: `"v1"`, or `"v2"` when the GOLD needed
  the fallback (`gold_port_method` is not `"3way"`).
- `--summarize` keeps its headline numbers and its `v1_plus_v2` block exactly as before;
  v3 receipts enter neither. A separate `v3` block counts the v3 receipts at their own
  labels, computed the same way as `v1_plus_v2`. It is present only when there is at
  least one v3 receipt, so a store of v1 and v2 receipts summarizes exactly as under
  scorer 1.2.4. `spec_version_counts` counts every receipt by version, and
  `unknown_spec_versions` now counts the versions other than `"v1"`, `"v2"` and `"v3"`.
- The intended use is to rescore the affected V12 tasks under v3 and report them next to
  the unchanged v1 headline, never in place of it. A v3 rescore needs its own `--out`
  store: the CLI skips every task that already has a receipt in `--out`, so pointing it
  at a v1 store would rescore nothing.

## A10: a metadata-only stub for the BASE project

**Problem (Issue #2709).** v1 §8 builds a `uv.lock` repo's env with
`uv sync --frozen --all-groups --no-install-project` (Nexus-new also with
`--all-extras`), so the project's own distribution metadata is never installed. Code
under test that asks for it fails. In nexus-core, `tests/product/test_client_conformance.py`
calls `importlib.metadata.version("nexus-certify")` at import time. That raises
`PackageNotFoundError`, pytest stops collecting, and the P2P(c) run `pytest tests` on
`BASE+T` exits 2 (collection interrupted) with no passing node. The P2P(c) base set is
empty (`p2p_total` 0). A candidate that breaks existing tests is then `UNRESOLVED` (or
even `RESOLVED`) instead of `BROKE_EXISTING`.

**Why not install the project.** A regular or editable install of BASE would put BASE
code (or a `.pth` that points at the BASE tree) on `sys.path`, where it can shadow the
tree under test. A test could then import BASE code while the candidate's code sits in
`PYTHONPATH=<tree>`. The stub gives the project's metadata and nothing else.

### Rule

After the env build of every recipe that runs `uv sync --no-install-project`
(`uv-sync-all-extras+canonical`, the Nexus-new recipe, after its canonical requirement
installs; and `uv-sync-all-groups`), the scorer writes one directory into the env's
`site-packages`:

- Name: `<name>-<version>.dist-info`. `<name>` is BASE `pyproject.toml` `[project].name`
  normalised as the packaging spec says (each run of `-`, `_`, `.` becomes `_`, then lower
  case). `<version>` is `[project].version` as written, with `-` escaped to `_`. Example:
  `nexus-certify` 0.3.0 gives `nexus_certify-0.3.0.dist-info`, so
  `importlib.metadata.version("nexus-certify")` returns `0.3.0`.
- Content: `METADATA` (`Metadata-Version: 2.1`, `Name`, `Version`), `INSTALLER`
  (`nexus-real-outcome-scorer`), `WHEEL` (`Wheel-Version: 1.0`,
  `Generator: nexus-real-outcome-scorer`, `Root-Is-Purelib: true`, `Tag: py3-none-any`,
  so `uv pip check` does not report the stub as broken) and a valid `RECORD` that lists
  those files with their sha256 and size. Nothing else:
  no code, no `.pth`, no `direct_url.json`, no entry points, no editable install. Imports
  still resolve only through `PYTHONPATH=<tree>` (plus `<tree>/src`), so the tree under
  test is never shadowed.
- Name and version come from an untrusted file, so they are checked before use, with
  ASCII-only full matches (a trailing newline, a non-ASCII letter or digit, whitespace or a
  path separator such as `../x` or `a/b` is refused). The name must match the PEP 508
  name pattern `[A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]`. The version must be a
  PEP 440 version (`packaging.version.Version` when `packaging` is importable, otherwise a
  strict ASCII PEP 440 pattern) made only of ASCII letters, digits and `!+._-`. The
  directory written must be a direct child of `site-packages`.
- The stub comes from BASE only, like the rest of the env (§8). A candidate or GOLD change
  to the project name or version is not reflected (see "BASE metadata on every tree").

No stub is written, and the receipt says why, when:

| Case | `project_metadata_stub_reason` |
|---|---|
| BASE has no `pyproject.toml` | `no_pyproject_toml` |
| `pyproject.toml` is a symlink | `pyproject_symlink` |
| `pyproject.toml` does not parse | `pyproject_unreadable:<ExceptionType>` (e.g. `TOMLDecodeError`) |
| no `[project]` table | `no_project_table` |
| `[project].name` missing or fails the name check above | `project_name_missing_or_invalid` |
| `version` is listed in `[project].dynamic` | `dynamic_version` |
| `[project].version` missing | `version_missing` |
| `[project].version` fails the version check above | `version_invalid` |
| a `*.dist-info` or `*.egg-info` in `site-packages` is the same project: its METADATA / PKG-INFO `Name` when readable, otherwise its entry name, equals the project name after PEP 503 normalisation (`re.sub(r"[-_.]+", "-", name).lower()`), whatever separator or case the entry uses | `project_already_installed:<dir>` |
| the env has no single `lib/python*/site-packages` | `site_packages_not_found` |
| the recipe has no project install step (below) | `recipe_without_project_install:<recipe>` |

A task without a stub is scored exactly as v1 or v2 would score it; the reason is a
diagnostic and never changes a label.

**Not covered: `uv-venv-runtime-pins`.** Repos without `uv.lock` (nexus-runtime) are built
with `uv venv` plus pinned packages. That recipe has no project and no
`--no-install-project` step, so v3 leaves it unchanged and writes no stub
(`recipe_without_project_install:uv-venv-runtime-pins`). Under v3 such a task differs from
v1 only in its spec fields and its env key.

### BASE metadata on every tree

The env, and so the stub, is built once from BASE and used for every tree (`BASE+T`,
`GOLD`, `CAND+T` and the others). Per-tree envs are out of scope. So when GOLD or the
candidate changes `[project].name` or `[project].version`, the installed metadata still
says BASE's. Consequences:

- **GOLD and the candidate both bump the version** (the usual case when the human fix
  bumps it and the candidate copies the bump). A test that needs the installed metadata to
  match the tree fails on GOLD as well. As an oracle node it cannot be F2P (it must pass
  3/3 on GOLD). As a P2P suspect it fails on GOLD and is dropped as `gold_also_fails`.
  Either way it never counts against the candidate.
- **Only the candidate bumps the version** and a BASE test compares the installed
  metadata with the tree's `pyproject.toml`. That test passes on `BASE+T` and fails on
  `CAND+T` and passes on GOLD, so it is a P2P new failure: a false `BROKE_EXISTING` is
  possible. The diagnostic below flags this case.

**Diagnostic.** Every v3 receipt that reached the env build records
`project_metadata_tree_versions`: `{"GOLD": …, "CAND": …}`, each the `{"name",
"version"}` read from that tree's `pyproject.toml` with the same checks as the stub, or
`{"reason": …}` when there is none. `"CAND"` is `null` when scoring stopped before the
candidate tree was built (for example `NO_CANDIDATE`). It also records
`project_metadata_version_mismatch`: `true` when a stub was written and either tree's
name (PEP 503 normalised) or version differs from it (a tree with no valid static
metadata counts as differing), otherwise `false`. No label, sub-reason or
`shadow_label` reads these fields. A reader should check a v3 `BROKE_EXISTING` that has
`project_metadata_version_mismatch: true` by hand.

### Receipt and cache keys

- Every v3 receipt that reached the env build records `project_metadata_stub`: either
  `{"name", "version", "dist_info"}` or `null`, and `project_metadata_stub_reason`:
  `null` when a stub was written, otherwise the reason above. An env provider that does
  not implement v3 gives `null` with reason `env_provider_without_v3_stub`. Receipts that
  stop before the env build (for example `PENDING_GROUND_TRUTH`) carry neither field.
- The env cache key under v3 also covers the spec version, so a v1 env and a v3 env are
  never the same cache entry. The test-result cache key is built from the env key, so v1
  and v3 test results never share an entry either. The v1 key formula is unchanged.
