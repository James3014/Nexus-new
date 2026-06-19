"""Tests for shadow_receipt module."""

import pytest
from nexus.services.local_heal.shadow_receipt import (
    create_dry_run_receipt,
    validate_receipt,
    detect_forbidden_output,
    ShadowReceipt,
    ValidationResult,
)


def test_valid_dry_receipt():
    r = create_dry_run_receipt("task_001", "dry_001", "3B", "slice_score_shadow", "input_ref")
    assert r.model_call_executed is False
    assert r.eval_executed is False
    assert r.runtime_effect is False
    assert r.adoption_allowed is False
    result = validate_receipt(r)
    assert result.ok is True


def test_runtime_effect_blocks():
    r = create_dry_run_receipt("task_001", "dry_001", "3B", "slice_score", "ref")
    r.runtime_effect = True
    result = validate_receipt(r)
    assert result.ok is False
    assert any("runtime_effect" in e for e in result.errors)


def test_routing_changed_blocks():
    r = create_dry_run_receipt("task_001", "dry_001", "3B", "slice_score", "ref")
    r.routing_changed = True
    result = validate_receipt(r)
    assert result.ok is False
    assert any("routing_changed" in e for e in result.errors)


def test_patch_apply_allowed_blocks():
    r = create_dry_run_receipt("task_001", "dry_001", "3B", "slice_score", "ref")
    r.patch_apply_allowed = True
    result = validate_receipt(r)
    assert result.ok is False


def test_verifier_override_blocks():
    r = create_dry_run_receipt("task_001", "dry_001", "3B", "slice_score", "ref")
    r.verifier_override_allowed = True
    result = validate_receipt(r)
    assert result.ok is False


def test_source_mutation_blocks():
    r = create_dry_run_receipt("task_001", "dry_001", "3B", "slice_score", "ref")
    r.source_mutation_allowed = True
    result = validate_receipt(r)
    assert result.ok is False


def test_training_export_blocks():
    r = create_dry_run_receipt("task_001", "dry_001", "3B", "slice_score", "ref")
    r.training_export_allowed = True
    result = validate_receipt(r)
    assert result.ok is False


def test_adoption_allowed_blocks():
    r = create_dry_run_receipt("task_001", "dry_001", "3B", "slice_score", "ref")
    r.adoption_allowed = True
    result = validate_receipt(r)
    assert result.ok is False


def test_forbidden_patch_output():
    detected = detect_forbidden_output("I will generate_patch for this file")
    assert "patch_generation" in detected


def test_forbidden_routing_output():
    detected = detect_forbidden_output("route_to_model 14B")
    assert "routing_decision" in detected


def test_forbidden_verifier_override():
    detected = detect_forbidden_output("bypass_verifier check")
    assert "verifier_override" in detected


def test_forbidden_solve_claim():
    detected = detect_forbidden_output("bug_fixed successfully")
    assert "solve_claim" in detected


def test_forbidden_output_blocks():
    r = create_dry_run_receipt("task_001", "dry_001", "3B", "slice_score", "ref")
    r.forbidden_output_detected = True
    result = validate_receipt(r)
    assert result.ok is False


def test_writer_output_path():
    r = create_dry_run_receipt("task_001", "dry_001", "3B", "slice_score", "ref")
    assert r.governance["runtime_effect"] is False
    assert r.governance["model_calls_executed"] is False
    assert r.governance["training_export"] is False
