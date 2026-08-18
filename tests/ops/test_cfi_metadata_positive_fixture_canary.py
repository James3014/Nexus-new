"""Controlled failing fixture for positive CFI metadata binding."""


def test_cfi_metadata_positive_fixture_intentionally_fails() -> None:
    raise AssertionError("CFI_METADATA_POSITIVE_FIXTURE_EXPECTED_FAILURE")
