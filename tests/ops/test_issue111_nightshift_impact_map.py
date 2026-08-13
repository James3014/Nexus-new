from scripts.ops.select_tests import load_impact_rules, select_targets


def test_issue111_entrypoint_maps_to_nightshift_contract_without_fallback():
    targets, reasons = select_targets(
        ["scripts/nightshift.py"],
        load_impact_rules(),
    )

    assert targets == [
        "tests/services/test_nightshift_queue_consumer.py",
        "tests/app/test_nightshift_runner_service.py",
    ]
    assert reasons == ["scripts/nightshift.py: matched scripts/nightshift.py"]


def test_issue111_unknown_sibling_remains_on_explicit_fallback():
    targets, reasons = select_targets(
        ["scripts/nightshift_unknown.py"],
        load_impact_rules(),
        fallback_targets=("tests/ops/test_select_tests.py",),
    )

    assert targets == ["tests/ops/test_select_tests.py"]
    assert reasons == ["scripts/nightshift_unknown.py: fallback"]
