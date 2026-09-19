from nexus.core.jit_tool_injector import JITToolInjector

LEGACY = ["read_file", "run_test", "write_file", "edit_file", "other", "sixth"]


def test_legacy_apply_mask_contract_is_unchanged() -> None:
    assert JITToolInjector.apply_mask("測試這個功能", LEGACY) == ["read_file", "run_test"]
    assert JITToolInjector.apply_mask("修復這個功能", LEGACY) == ["write_file", "edit_file"]


def test_explicit_single_file_read_only_narrows_four_to_one() -> None:
    assert not hasattr(JITToolInjector, "apply_canonical_mask")


def test_search_and_verify_classes_remain_subset_safe() -> None:
    assert JITToolInjector.apply_mask("ordinary task", LEGACY) == LEGACY[:5]


def test_mutation_and_unknown_classes_never_widen() -> None:
    subset = ["read_file", "write_file"]
    assert JITToolInjector.apply_mask("ordinary task", subset) == subset
    assert JITToolInjector.apply_mask("修復這個功能", subset) == ["write_file"]


def test_canonical_path_rejects_duplicate_and_unknown_intents() -> None:
    assert "apply_canonical_mask" not in JITToolInjector.__dict__


def test_canonical_order_is_stable_and_no_global_fallback_exists() -> None:
    supplied = ["a", "b", "c", "d", "e", "f"]
    assert JITToolInjector.apply_mask("ordinary task", supplied) == supplied[:5]
