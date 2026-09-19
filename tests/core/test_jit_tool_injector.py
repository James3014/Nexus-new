import pytest

from nexus.core.jit_tool_injector import JITToolInjector


READ_ONLY = [
    "workspace.read",
    "workspace.search_text",
    "workspace.search_paths",
    "workspace.list",
]
ALL = [*READ_ONLY, "workspace.mutate", "process.execute"]


def test_legacy_apply_mask_contract_is_unchanged() -> None:
    legacy = ["read_file", "run_test", "write_file", "edit_file", "other", "sixth"]
    assert JITToolInjector.apply_mask("測試這個功能", legacy) == ["read_file", "run_test"]
    assert JITToolInjector.apply_mask("修復這個功能", legacy) == ["write_file", "edit_file"]
    assert JITToolInjector.apply_mask("ordinary task", legacy) == legacy[:5]


def test_explicit_single_file_read_only_narrows_four_to_one() -> None:
    selected = JITToolInjector.apply_canonical_mask(
        "Read only this single file and return its first heading.",
        READ_ONLY,
    )
    assert selected == ["workspace.read"]


def test_search_and_verify_classes_remain_subset_safe() -> None:
    search = JITToolInjector.apply_canonical_mask("Find and inspect the declaration", ALL)
    verify = JITToolInjector.apply_canonical_mask("Run tests and verify the result", ALL)
    assert search == READ_ONLY
    assert verify == [*READ_ONLY, "process.execute"]
    assert set(search) <= set(ALL)
    assert set(verify) <= set(ALL)


def test_mutation_and_unknown_classes_never_widen() -> None:
    supplied = ["workspace.read", "workspace.mutate"]
    assert JITToolInjector.apply_canonical_mask("Fix and edit the file", supplied) == supplied
    assert JITToolInjector.apply_canonical_mask("Do the bounded task", supplied) == supplied


def test_canonical_path_rejects_duplicate_and_unknown_intents() -> None:
    with pytest.raises(ValueError, match="candidate_tools_duplicate"):
        JITToolInjector.apply_canonical_mask(
            "Read only this single file",
            ["workspace.read", "workspace.read"],
        )
    with pytest.raises(ValueError, match="candidate_tools_unknown"):
        JITToolInjector.apply_canonical_mask(
            "Find the declaration",
            ["workspace.read", "provider.magic"],
        )


def test_canonical_order_is_stable_and_no_global_fallback_exists() -> None:
    supplied = ["workspace.list", "workspace.read", "workspace.search_text"]
    selected = JITToolInjector.apply_canonical_mask("Unclassified bounded task", supplied)
    assert selected == ["workspace.read", "workspace.search_text", "workspace.list"]
    assert set(selected) == set(supplied)
