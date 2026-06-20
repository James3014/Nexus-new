"""
EnvRecipeRegistry v1.0

Deterministic recipes for known environment issues.
Each recipe is a white-listed, auditable, rollback-capable action plan.
No model-generated shell commands — only registered recipes.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Callable
from pathlib import Path


@dataclass
class EnvRecipe:
    """A deterministic, white-listed environment fix recipe."""
    id: str
    trigger_signals: List[str]
    allowed_actions: List[str]  # e.g. ["pip install", "mock import"]
    rollback_hint: str
    evidence_refs: List[str] = field(default_factory=list)
    description: str = ""


class EnvRecipeRegistry:
    """
    Registry of deterministic environment fix recipes.
    Recipes are matched by trigger signals and executed as fixed action plans.
    No model inference involved — pure rule-based.
    """
    
    def __init__(self):
        self._recipes: List[EnvRecipe] = []
        self._register_builtins()
    
    def _register_builtins(self):
        """Register the initial set of high-frequency recipes."""
        self.register(EnvRecipe(
            id="numpy_api_drift",
            trigger_signals=["numpy", "numpy.core", "np.bool", "np.int", "np.float", "np.complex", "np.object", "np.str"],
            allowed_actions=["pip install 'numpy<2.0'"],
            rollback_hint="pip install 'numpy>=2.0'",
            evidence_refs=["astropy-14096-runbook"],
            description="Fix numpy 2.x API drift (removed aliases like np.bool, np.int)",
        ))
        self.register(EnvRecipe(
            id="missing_dependency_install",
            trigger_signals=["ImportError", "ModuleNotFoundError", "No module named"],
            allowed_actions=["uv pip install <package>"],
            rollback_hint="uv pip uninstall <package>",
            evidence_refs=["general"],
            description="Install missing Python dependency",
        ))
        self.register(EnvRecipe(
            id="setuptools_alignment",
            trigger_signals=["setuptools", "extension-helpers", "setup.py", "setup.cfg"],
            allowed_actions=["pip install 'setuptools<70'", "pip install extension-helpers"],
            rollback_hint="pip install 'setuptools>=70'",
            evidence_refs=["astropy-14096-runbook"],
            description="Align setuptools/extension-helpers for C-extension builds",
        ))
        self.register(EnvRecipe(
            id="cext_mock",
            trigger_signals=["gcc", "cc", "compilation error", "cannot find -l", "No module named"],
            allowed_actions=["mock C-extension import"],
            rollback_hint="remove mock import",
            evidence_refs=["astropy-14096-runbook"],
            description="Mock C-extension that fails to compile in test environment",
        ))
        self.register(EnvRecipe(
            id="import_noise_suppress",
            trigger_signals=["ImportError", "ModuleNotFoundError", "import"],
            allowed_actions=["add try/except ImportError"],
            rollback_hint="remove try/except",
            evidence_refs=["general"],
            description="Suppress non-critical import errors that obscure the real bug",
        ))
        self.register(EnvRecipe(
            id="python_version_compat",
            trigger_signals=["SyntaxError", "asyncio", "walrus", "match statement"],
            allowed_actions=["check python version", "adjust syntax for compatibility"],
            rollback_hint="restore original syntax",
            evidence_refs=["general"],
            description="Handle Python version incompatibilities",
        ))
        self.register(EnvRecipe(
            id="collections_mapping_drift",
            trigger_signals=["collections", "Mapping", "MutableMapping", "cannot import name"],
            allowed_actions=["shim collections.Mapping"],
            rollback_hint="remove shim from repro script",
            evidence_refs=["python3.10-compat"],
            description="Fix Python 3.10+ removal of collections.Mapping (moved to collections.abc)",
        ))
        self.register(EnvRecipe(
            id="sympy_mpmath_dependency",
            trigger_signals=["mpmath", "SymPy now depends on mpmath"],
            allowed_actions=["pip install mpmath"],
            rollback_hint="pip uninstall mpmath",
            evidence_refs=["sympy-runbook"],
            description="Install mpmath dependency required by sympy",
        ))
        self.register(EnvRecipe(
            id="scipy_version_align",
            trigger_signals=["scipy", "scipy.special", "scipy.stats"],
            allowed_actions=["pip install 'scipy<1.14'"],
            rollback_hint="pip install 'scipy>=1.14'",
            evidence_refs=["astropy-runbook"],
            description="Align scipy version for astropy compatibility",
        ))
        self.register(EnvRecipe(
            id="pytest_plugin_conflict",
            trigger_signals=["pytest", "pluggy", "plugin", "fixture"],
            allowed_actions=["pip install 'pytest>=7.0,<8.0'"],
            rollback_hint="pip install 'pytest>=8.0'",
            evidence_refs=["general"],
            description="Resolve pytest plugin version conflicts",
        ))
        self.register(EnvRecipe(
            id="sympy_symbol_collision",
            trigger_signals=["sympy", "Symbol", "undefined", "collision"],
            allowed_actions=["clear sympy cache", "reset symbol registry"],
            rollback_hint="no rollback needed",
            evidence_refs=["sympy-runbook"],
            description="Resolve sympy symbol registry collisions",
        ))
        self.register(EnvRecipe(
            id="django_migration_conflict",
            trigger_signals=["django", "migration", "conflict", "inconsistent"],
            allowed_actions=["python manage.py migrate --run-syncdb"],
            rollback_hint="python manage.py migrate --fake",
            evidence_refs=["django-runbook"],
            description="Resolve Django migration conflicts",
        ))
    
    def register(self, recipe: EnvRecipe):
        self._recipes.append(recipe)
    
    def match(self, signals: List[str]) -> Optional[EnvRecipe]:
        """Find the BEST matching recipe (most specific first)."""
        signals_lower = [s.lower() for s in signals]
        # Score each recipe by number of signal matches (more specific = more matches)
        scored = []
        for recipe in self._recipes:
            match_count = 0
            for trigger in recipe.trigger_signals:
                trigger_lower = trigger.lower()
                for signal in signals_lower:
                    if trigger_lower in signal or signal in trigger_lower:
                        match_count += 1
            if match_count > 0:
                scored.append((match_count, recipe))
        
        if not scored:
            return None
        
        # Return the recipe with the most signal matches (most specific)
        scored.sort(key=lambda x: -x[0])
        return scored[0][1]
    
    def match_all(self, signals: List[str]) -> List[EnvRecipe]:
        """Find all matching recipes (for analysis/debugging)."""
        signals_lower = [s.lower() for s in signals]
        matches = []
        for recipe in self._recipes:
            for trigger in recipe.trigger_signals:
                trigger_lower = trigger.lower()
                for signal in signals_lower:
                    if trigger_lower in signal or signal in trigger_lower:
                        if recipe not in matches:
                            matches.append(recipe)
                        break
        return matches
    
    def list_recipes(self) -> List[EnvRecipe]:
        return list(self._recipes)
