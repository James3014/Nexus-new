from pathlib import Path

from scripts.ops.cbo_io_measurement import measure_cbo_io


def test_cbo_io_measurement_writes_observation_only_report(tmp_path: Path):
    output = tmp_path / "cbo_io.json"

    report = measure_cbo_io(output_path=output)

    assert output.exists()
    assert report["schema"] == "nexus.cbo_io_measurement.v1"
    assert report["status"] == "PASS"
    assert report["claim_class"] == "OBSERVATION_ONLY"
    assert report["delta_claim_allowed"] is False
    assert report["sample_size"] == 2
    assert report["baseline"]["file_reads"] >= 1
    assert report["changed"]["file_writes"] >= 1
