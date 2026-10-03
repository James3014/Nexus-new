import sys

from nexus.services.m5_local.contracts import (
    HOST_CLASSIFICATION_AVAILABLE_EXACT,
    HOST_CLASSIFICATION_NOT_INSTALLED,
    QUALIFICATION_NOT_QUALIFIED,
)
from nexus.services.m5_local.host_inventory import (
    get_host_memory_info,
    inspect_m5_host,
    inspect_models,
    inspect_runtimes,
)


def test_get_host_memory_info():
    mem = get_host_memory_info()
    assert mem is not None
    if sys.platform == "darwin":
        assert mem.total_ram_bytes > 0
        assert mem.swap_total_mb >= 0
    else:
        assert mem.total_ram_bytes == 0
        assert mem.swap_total_mb == 0.0


def test_inspect_runtimes():
    runtimes = inspect_runtimes()
    assert "llama.cpp" in runtimes
    assert "mlx" in runtimes
    llama = runtimes["llama.cpp"]
    assert llama.classification in (
        HOST_CLASSIFICATION_AVAILABLE_EXACT,
        HOST_CLASSIFICATION_NOT_INSTALLED,
    )


def test_inspect_models():
    models = inspect_models()
    assert "qwen36-35b-q4" in models
    assert "occamy-1.0-q4" in models
    # Invariant: All roles are NOT_QUALIFIED without physical Nexus Learning receipts
    for item in models.values():
        for role, qual in item.role_qualifications.items():
            assert qual == QUALIFICATION_NOT_QUALIFIED


def test_inspect_m5_host():
    inv = inspect_m5_host()
    assert inv.memory is not None
    if sys.platform == "darwin":
        assert inv.cpu_brand != ""
    else:
        assert inv.cpu_brand == "UNKNOWN"
    assert len(inv.runtimes) >= 2
    assert len(inv.models) >= 2
