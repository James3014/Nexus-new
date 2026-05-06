# ADR: Pre-Flash Smoke Test Root Scope Lesson

Date: 2026-05-06

## Context

A new pre-Flash smoke test called the full `build_payload()` function with a
temporary directory as `repo_root`. That incorrectly exercised Brain Hub manifest
loading against a fixture root with no `docs/ops/brain_hub_manifest.json`.

## Decision

Tests for isolated pre-Flash sub-checks should call the sub-check directly with
`tmp_path`. Full `build_payload()` tests must use the real repository root or
provide the required manifest fixture.

## Lesson

Pre-Flash gates mix repo-global audits and isolated deterministic smoke checks.
Tests must preserve that root-scope distinction or they will fail because of
fixture incompleteness rather than runtime behavior.
