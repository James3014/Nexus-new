"""G5: Backend/Model Resource Policy

Implement policy metadata for model/resource governance:
- local_7b_allowed
- local_12b_allowed_with_timeout
- local_14b_cpu_forbidden
- local_14b_gpu_requires_guard
- cloud_requires_owner_approval
- cloud result classification separate from local success
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ModelTier(Enum):
    LOCAL_3B = "local_3b"
    LOCAL_7B = "local_7b"
    LOCAL_12B = "local_12b"
    LOCAL_14B = "local_14b"
    CLOUD = "cloud"


class ResourcePolicy(Enum):
    ALLOWED = "allowed"
    ALLOWED_WITH_TIMEOUT = "allowed_with_timeout"
    FORBIDDEN = "forbidden"
    REQUIRES_GUARD = "requires_guard"
    REQUIRES_APPROVAL = "requires_approval"


@dataclass
class ModelPolicy:
    """Policy for a specific model configuration."""
    model_name: str
    model_tier: ModelTier
    resource_policy: ResourcePolicy
    timeout_seconds: int = 300
    requires_gpu: bool = False
    requires_owner_approval: bool = False
    result_classification: str = "local_success"
    notes: str = ""


# Default policies
DEFAULT_POLICIES: dict[str, ModelPolicy] = {
    "qwen2.5:3b": ModelPolicy(
        model_name="qwen2.5:3b",
        model_tier=ModelTier.LOCAL_3B,
        resource_policy=ResourcePolicy.ALLOWED,
        result_classification="local_success",
        notes="3B model — must not generate repair patches, only selector/advisor",
    ),
    "qwen2.5-coder:7b": ModelPolicy(
        model_name="qwen2.5-coder:7b",
        model_tier=ModelTier.LOCAL_7B,
        resource_policy=ResourcePolicy.ALLOWED,
        timeout_seconds=300,
        result_classification="local_success",
    ),
    "deepseek-coder:6.7b-instruct": ModelPolicy(
        model_name="deepseek-coder:6.7b-instruct",
        model_tier=ModelTier.LOCAL_7B,
        resource_policy=ResourcePolicy.ALLOWED,
        timeout_seconds=300,
        result_classification="local_success",
        notes="6.7B local model — allowed for explicit secondary-proposer/manual route use",
    ),
    "gemma4-coder-12b-q4km:latest": ModelPolicy(
        model_name="gemma4-coder-12b-q4km:latest",
        model_tier=ModelTier.LOCAL_12B,
        resource_policy=ResourcePolicy.ALLOWED_WITH_TIMEOUT,
        timeout_seconds=300,
        result_classification="local_success",
        notes="12B model — allowed with timeout, not CPU-only 14B",
    ),
    "deepseek-r1-14b-q4km:latest": ModelPolicy(
        model_name="deepseek-r1-14b-q4km:latest",
        model_tier=ModelTier.LOCAL_14B,
        resource_policy=ResourcePolicy.FORBIDDEN,
        result_classification="env_invalid",
        notes="14B CPU-only — FORBIDDEN due to OS hang risk",
    ),
    "gpt-4o": ModelPolicy(
        model_name="gpt-4o",
        model_tier=ModelTier.CLOUD,
        resource_policy=ResourcePolicy.REQUIRES_APPROVAL,
        requires_owner_approval=True,
        result_classification="cloud_success",
        notes="Cloud API — requires explicit owner approval, result classified separately",
    ),
    "claude-3-5-sonnet": ModelPolicy(
        model_name="claude-3-5-sonnet",
        model_tier=ModelTier.CLOUD,
        resource_policy=ResourcePolicy.REQUIRES_APPROVAL,
        requires_owner_approval=True,
        result_classification="cloud_success",
        notes="Cloud API — requires explicit owner approval, result classified separately",
    ),
}


class BackendResourcePolicy:
    """Manages model/resource policies."""

    def __init__(self, custom_policies: dict[str, ModelPolicy] | None = None):
        self.policies = dict(DEFAULT_POLICIES)
        if custom_policies:
            self.policies.update(custom_policies)

    def get_policy(self, model_name: str) -> ModelPolicy | None:
        """Get policy for a model."""
        return self.policies.get(model_name)

    def is_allowed(self, model_name: str) -> bool:
        """Check if model is allowed."""
        policy = self.get_policy(model_name)
        if policy is None:
            return False
        return policy.resource_policy in {
            ResourcePolicy.ALLOWED,
            ResourcePolicy.ALLOWED_WITH_TIMEOUT,
        }

    def requires_approval(self, model_name: str) -> bool:
        """Check if model requires owner approval."""
        policy = self.get_policy(model_name)
        if policy is None:
            return True
        return policy.requires_owner_approval

    def is_forbidden(self, model_name: str) -> bool:
        """Check if model is forbidden."""
        policy = self.get_policy(model_name)
        if policy is None:
            return True
        return policy.resource_policy == ResourcePolicy.FORBIDDEN

    def get_timeout(self, model_name: str) -> int:
        """Get timeout for model."""
        policy = self.get_policy(model_name)
        if policy is None:
            return 300
        return policy.timeout_seconds

    def classify_result(self, model_name: str, success: bool) -> str:
        """Classify result based on model policy."""
        policy = self.get_policy(model_name)
        if policy is None:
            return "unknown_model"
        if not success:
            return "failure"
        return policy.result_classification

    def validate_execution(
        self,
        model_name: str,
        *,
        gpu_available: bool = False,
        owner_approved: bool = False,
    ) -> tuple[bool, str]:
        """Validate if model execution is allowed."""
        policy = self.get_policy(model_name)
        if policy is None:
            return False, f"Unknown model: {model_name}"

        if policy.resource_policy == ResourcePolicy.FORBIDDEN:
            return False, f"Forbidden: {policy.notes}"

        if policy.requires_owner_approval and not owner_approved:
            return False, f"Requires owner approval: {policy.notes}"

        if policy.requires_gpu and not gpu_available:
            return False, f"Requires GPU: {policy.notes}"

        return True, "allowed"

    def list_allowed_models(self) -> list[str]:
        """List all allowed models."""
        return [
            name for name, policy in self.policies.items()
            if policy.resource_policy in {
                ResourcePolicy.ALLOWED,
                ResourcePolicy.ALLOWED_WITH_TIMEOUT,
            }
        ]

    def list_forbidden_models(self) -> list[str]:
        """List all forbidden models."""
        return [
            name for name, policy in self.policies.items()
            if policy.resource_policy == ResourcePolicy.FORBIDDEN
        ]
