from nexus.engine.phase_factory import PhaseFactory


def test_phase_factory_creates_all_default_phase_executors(tmp_path):
    factory = PhaseFactory(project_root=tmp_path, run_dir=tmp_path / ".nexus" / "runs", hub=None)

    executors = factory.create_all()

    assert set(executors) == {"P", "X", "D", "R", "A", "C"}
    assert executors["P"].name == "P"
    assert executors["X"].name == "X"
    assert executors["D"].name == "D"
    assert executors["R"].name == "R"
    assert executors["A"].name == "A"
    assert executors["C"].name == "C"


def test_phase_factory_rejects_unknown_phase(tmp_path):
    factory = PhaseFactory(project_root=tmp_path, run_dir=tmp_path / ".nexus" / "runs")

    try:
        factory.create_phase("Z")
    except ValueError as exc:
        assert str(exc) == "unknown_phase:Z"
    else:
        raise AssertionError("unknown phase should fail fast")
