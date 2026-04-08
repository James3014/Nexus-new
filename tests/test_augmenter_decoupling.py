import pytest
from pathlib import Path
from nexus.services.implementation_pack import ImplementationPackGenerator

def test_ipack_generator_without_augmenter():
    # 嘗試傳入 None 作為 augmenter，模擬解耦後的行為
    try:
        gen = ImplementationPackGenerator(Path("."), "T1", augmenter=None)
        res = gen.generate({"goal": "test"})
        assert "wisdom_boosted" not in res or res.get("wisdom_boosted") is False
    except TypeError:
        pytest.fail("ImplementationPackGenerator does not support augmenter injection yet")

