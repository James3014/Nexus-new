from typing import Protocol, Dict, Any, runtime_checkable

@runtime_checkable
class ILLMClient(Protocol):
    """
    🛡️ Decoupled LLM Client Interface
    Defines the contract for calling LLM models.
    """
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        timeout: int | None = None,
        options: Dict[str, Any] | None = None,
        api_type: str = "generate"
    ) -> str:
        """Execute a text generation call."""
        ...


class OllamaLLMClient:
    """
    ⚙️ Ollama LLM Client Wrapper
    Wraps dynamic ollama generate functions with backward-compatible signature reflection.
    """
    def __init__(self, generate_fn: Any):
        self.generate_fn = generate_fn

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        timeout: int | None = None,
        options: Dict[str, Any] | None = None,
        api_type: str = "generate"
    ) -> str:
        import inspect
        try:
            sig = inspect.signature(self.generate_fn)
            kwargs = {}
            if "model" in sig.parameters:
                kwargs["model"] = model
            if "timeout" in sig.parameters and timeout is not None:
                kwargs["timeout"] = timeout
            if "options" in sig.parameters and options is not None:
                kwargs["options"] = options
            if "api_type" in sig.parameters:
                kwargs["api_type"] = api_type
            if kwargs:
                return self.generate_fn(system_prompt, user_prompt, **kwargs)
        except (TypeError, ValueError):
            pass
        return self.generate_fn(system_prompt, user_prompt)
