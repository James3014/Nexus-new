import pytest
from pydantic import ValidationError
from nexus.models.config_models import GovernanceConfig

def test_governance_config_validation():
    # 測試正常加載
    raw_data = {"enforce_level": "p0", "wiki_sync_mandatory": True}
    config = GovernanceConfig(**raw_data)
    assert config.enforce_level == "p0"

    # 測試非法數據 (非法列舉值)
    with pytest.raises(ValidationError):
        GovernanceConfig(enforce_level="SUPER_STRICT", wiki_sync_mandatory="YES")
