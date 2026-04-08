import pytest
from nexus.core.armor_engine import ArmorFactory, BaseArmorEngine

def test_armor_factory_dispatch():
    try:
        python_armor = ArmorFactory.get_armor("python")
        assert isinstance(python_armor, BaseArmorEngine)
        assert python_armor.armor_type == "python"
    except (ImportError, AttributeError):
        pytest.fail("ArmorFactory or BaseArmorEngine not implemented yet")

def test_rust_armor_dispatch():
    rust_armor = ArmorFactory.get_armor("rust")
    assert rust_armor.armor_type == "rust"
