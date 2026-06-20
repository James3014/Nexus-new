"""
Env Lane Failure Taxonomy v1.0

Classifies REPRO_ENVIRONMENT_FAILURE into precise categories.
Each category maps to:
- agent_fixable: bool (can Nexus fix this?)
- expected_stop_layer: str (where should pipeline stop?)
- claim_eligible: bool (default false for env failures)
"""
from enum import Enum


class EnvFailureTaxonomy(str, Enum):
    """Authoritative env lane failure taxonomy."""
    
    # Agent-fixable: Nexus can handle these with deterministic recipes
    DEPENDENCY_MISMATCH = "DEPENDENCY_MISMATCH"
    IMPORT_NOISE = "IMPORT_NOISE"
    VERSION_DRIFT = "VERSION_DRIFT"
    CEXTENSION_MOCK = "CEXTENSION_MOCK"
    REPRO_NOT_REPRODUCED = "REPRO_NOT_REPRODUCED"
    REPRO_WORKSPACE_MISSING = "REPRO_WORKSPACE_MISSING"
    REPO_NOT_MOUNTED = "REPO_NOT_MOUNTED"
    REPO_NOT_WRITABLE = "REPO_NOT_WRITABLE"
    WORKDIR_MISMATCH = "WORKDIR_MISMATCH"
    TEST_ASSET_MISSING = "TEST_ASSET_MISSING"
    REPRO_ALREADY_FIXED = "REPRO_ALREADY_FIXED"
    
    # Externally blocked: not fixable by Nexus
    TOOLCHAIN_MISSING = "TOOLCHAIN_MISSING"
    PRIVILEGE_REQUIRED = "PRIVILEGE_REQUIRED"
    BENCHMARK_INFO_INSUFFICIENT = "BENCHMARK_INFO_INSUFFICIENT"


# Taxonomy → metadata mapping
TAXONOMY_META = {
    EnvFailureTaxonomy.DEPENDENCY_MISMATCH: {
        "agent_fixable": True,
        "expected_stop_layer": "env_resolver",
        "claim_eligible": False,
        "description": "Missing or version-conflicting dependencies",
    },
    EnvFailureTaxonomy.IMPORT_NOISE: {
        "agent_fixable": True,
        "expected_stop_layer": "env_resolver",
        "claim_eligible": False,
        "description": "Import/compiler noise obscuring the real bug",
    },
    EnvFailureTaxonomy.VERSION_DRIFT: {
        "agent_fixable": True,
        "expected_stop_layer": "env_resolver",
        "claim_eligible": False,
        "description": "Known API drift (e.g., numpy 2.x breaking changes)",
    },
    EnvFailureTaxonomy.CEXTENSION_MOCK: {
        "agent_fixable": True,
        "expected_stop_layer": "env_resolver",
        "claim_eligible": False,
        "description": "C-extension compilation failure, mockable",
    },
    EnvFailureTaxonomy.REPRO_NOT_REPRODUCED: {
        "agent_fixable": True,
        "expected_stop_layer": "reprorunner",
        "claim_eligible": False,
        "description": "Bug could not be reproduced even after env cleanup",
    },
    EnvFailureTaxonomy.REPRO_WORKSPACE_MISSING: {
        "agent_fixable": True,
        "expected_stop_layer": "reprorunner",
        "claim_eligible": False,
        "description": "Workspace or reproduce script not set up",
    },
    EnvFailureTaxonomy.REPO_NOT_MOUNTED: {
        "agent_fixable": True,
        "expected_stop_layer": "reprorunner",
        "claim_eligible": False,
        "description": "Repository directory not mounted or accessible",
    },
    EnvFailureTaxonomy.REPO_NOT_WRITABLE: {
        "agent_fixable": True,
        "expected_stop_layer": "reprorunner",
        "claim_eligible": False,
        "description": "Repository directory exists but is not writable",
    },
    EnvFailureTaxonomy.WORKDIR_MISMATCH: {
        "agent_fixable": True,
        "expected_stop_layer": "reprorunner",
        "claim_eligible": False,
        "description": "Repository exists at different path than expected",
    },
    EnvFailureTaxonomy.TEST_ASSET_MISSING: {
        "agent_fixable": True,
        "expected_stop_layer": "reprorunner",
        "claim_eligible": False,
        "description": "Test fixture or reproduce script missing from workspace",
    },
    EnvFailureTaxonomy.REPRO_ALREADY_FIXED: {
        "agent_fixable": False,
        "expected_stop_layer": "reprorunner",
        "claim_eligible": False,
        "description": "Bug already fixed in current version, nothing to patch",
    },
    EnvFailureTaxonomy.TOOLCHAIN_MISSING: {
        "agent_fixable": False,
        "expected_stop_layer": "env_resolver",
        "claim_eligible": False,
        "description": "Required compiler/toolchain not available",
    },
    EnvFailureTaxonomy.PRIVILEGE_REQUIRED: {
        "agent_fixable": False,
        "expected_stop_layer": "env_resolver",
        "claim_eligible": False,
        "description": "Operation requires elevated privileges",
    },
    EnvFailureTaxonomy.BENCHMARK_INFO_INSUFFICIENT: {
        "agent_fixable": False,
        "expected_stop_layer": "env_resolver",
        "claim_eligible": False,
        "description": "Benchmark provides insufficient info to reproduce",
    },
}


def classify_env_failure(reason: str, env_resolution: dict, env_denoise: dict) -> EnvFailureTaxonomy:
    """
    Classify an environment failure into the taxonomy.
    
    Priority order:
    1. Check env_resolution for explicit external block
    2. Check env_denoise for agent-fixable signals
    3. Classify by reason string patterns
    4. Default to DEPENDENCY_MISMATCH (conservative)
    """
    # 1. External block from env_resolution
    if env_resolution.get("external_block") or env_resolution.get("blocked_reason"):
        if "PRIVILEGE" in str(env_resolution.get("blocked_reason", "")).upper():
            return EnvFailureTaxonomy.PRIVILEGE_REQUIRED
        if "TOOLCHAIN" in str(env_resolution.get("blocked_reason", "")).upper():
            return EnvFailureTaxonomy.TOOLCHAIN_MISSING
        if "INFO" in str(env_resolution.get("blocked_reason", "")).upper():
            return EnvFailureTaxonomy.BENCHMARK_INFO_INSUFFICIENT
        return EnvFailureTaxonomy.TOOLCHAIN_MISSING
    
    # 2. Agent-fixable from env_denoise
    if env_denoise and any(v for v in env_denoise.values() if v):
        # Check what kind of denoise was attempted
        denoise_str = str(env_denoise).lower()
        if "mock" in denoise_str or "extension" in denoise_str or "cext" in denoise_str:
            return EnvFailureTaxonomy.CEXTENSION_MOCK
        if "import" in denoise_str or "compile" in denoise_str:
            return EnvFailureTaxonomy.IMPORT_NOISE
        if "version" in denoise_str or "drift" in denoise_str:
            return EnvFailureTaxonomy.VERSION_DRIFT
        return EnvFailureTaxonomy.DEPENDENCY_MISMATCH
    
    # 3. Classify by reason string
    reason_upper = reason.upper()
    
    if "NOT_REPRODUCED" in reason_upper or "REPRO_NOT_REPRODUCED" in reason_upper:
        return EnvFailureTaxonomy.REPRO_NOT_REPRODUCED
    
    if "ALREADY_FIXED" in reason_upper:
        return EnvFailureTaxonomy.REPRO_ALREADY_FIXED
    
    if "WORKSPACE_MISSING" in reason_upper or "No such file or directory" in reason:
        if "reproduce_bug.py" in reason or "repro" in reason.lower():
            return EnvFailureTaxonomy.TEST_ASSET_MISSING
        if "repo" in reason.lower() or "workspace" in reason.lower():
            return EnvFailureTaxonomy.REPO_NOT_MOUNTED
        return EnvFailureTaxonomy.REPRO_WORKSPACE_MISSING
    
    if any(kw in reason_upper for kw in ["BINARY_MISSING", "TOOLCHAIN", "COMPILER"]):
        return EnvFailureTaxonomy.TOOLCHAIN_MISSING
    
    if any(kw in reason_upper for kw in ["PRIVILEGE", "PERMISSION"]):
        return EnvFailureTaxonomy.PRIVILEGE_REQUIRED
    
    if any(kw in reason_upper for kw in ["MOCK", "CEXTENSION", "C_EXTENSION"]):
        return EnvFailureTaxonomy.CEXTENSION_MOCK
    
    if any(kw in reason_upper for kw in ["IMPORT", "COMPILE", "SYNTAX"]):
        return EnvFailureTaxonomy.IMPORT_NOISE
    
    if any(kw in reason_upper for kw in ["VERSION", "DRIFT", "VIOLATION"]):
        return EnvFailureTaxonomy.VERSION_DRIFT
    
    # 4. Default: dependency mismatch (conservative — agent should have tried)
    return EnvFailureTaxonomy.DEPENDENCY_MISMATCH
