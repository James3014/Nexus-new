from __future__ import annotations

import hashlib
import json
import os
import subprocess
from typing import Any, Callable, Mapping, Sequence

from langchain_core.language_models.chat_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

OPENCLI_WEB_PROTOCOL = "nexus.opencli_web_chat.v1"
_ALLOWED_LEVELS = frozenset({"fast", "balanced", "advanced", "very-high", "pro"})


class OpenCLIWebModelError(RuntimeError):
    """Bounded failure from the ChatGPT Web transport."""


def _message_role(message: BaseMessage) -> str:
    if message.type == "human":
        return "user"
    if message.type == "ai":
        return "assistant"
    return str(message.type)


def _jsonable_content(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_jsonable_content(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _jsonable_content(item) for key, item in value.items()}
    return str(value)


def _message_payload(message: BaseMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": _message_role(message),
        "content": _jsonable_content(message.content),
    }
    if isinstance(message, AIMessage) and message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": str(call.get("id") or ""),
                "name": str(call.get("name") or ""),
                "arguments": dict(call.get("args") or {}),
            }
            for call in message.tool_calls
        ]
    if isinstance(message, ToolMessage):
        payload["tool_call_id"] = str(message.tool_call_id)
    return payload


def _tool_name(tool: Mapping[str, Any]) -> str:
    function = tool.get("function")
    if not isinstance(function, Mapping):
        return ""
    name = function.get("name")
    return str(name) if isinstance(name, str) else ""


def _tool_call_id(name: str, arguments: Mapping[str, Any], raw: str) -> str:
    canonical = json.dumps(
        {"name": name, "arguments": dict(arguments), "raw": raw},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return "opencli_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


class OpenCLIWebChatModel(BaseChatModel):
    """LangChain chat-model bridge backed by ChatGPT Web through OpenCLI.

    The bridge deliberately owns no repository tools and no Nexus authority. It
    only translates LangChain messages/tool declarations into one ChatGPT Web
    model turn and converts an explicit web response back into an ``AIMessage``.
    Tool execution remains inside Deep Agents / the external Open SWE runtime.

    Retained-conversation recovery and stricter response-schema enforcement are
    intentionally separate follow-up gates; this W3 bridge uses a fresh ChatGPT
    conversation for each model turn.
    """

    executable: str = "opencli"
    intelligence_level: str = "very-high"
    profile: str = ""
    timeout_seconds: int = 120
    site_session: str = "ephemeral"
    disable_streaming: bool = True

    @property
    def model_name(self) -> str:
        """Provider-native identifier used by the Deep Agents harness registry."""
        return self.intelligence_level

    @property
    def _llm_type(self) -> str:
        return "opencli-chatgpt-web"

    def _get_ls_params(self, stop: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
        params = dict(super()._get_ls_params(stop=stop, **kwargs))
        params["ls_provider"] = "opencli_chatgpt"
        params["ls_model_name"] = self.intelligence_level
        return params

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {
            "executable": self.executable,
            "intelligence_level": self.intelligence_level,
            "site_session": self.site_session,
        }

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        formatted = [convert_to_openai_tool(tool) for tool in tools]
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        return self.bind(tools=formatted, **kwargs)

    def _environment(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.profile:
            env["OPENCLI_PROFILE"] = self.profile
        return env

    def _run(self, argv: Sequence[str]) -> str:
        try:
            result = subprocess.run(
                list(argv),
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds + 5,
                shell=False,
                env=self._environment(),
            )
        except FileNotFoundError as exc:
            raise OpenCLIWebModelError("OPENCLI_NOT_FOUND") from exc
        except subprocess.TimeoutExpired as exc:
            raise OpenCLIWebModelError("OPENCLI_WEB_TIMEOUT") from exc
        if result.returncode != 0:
            raise OpenCLIWebModelError("OPENCLI_WEB_PROCESS_FAILURE")
        return result.stdout or ""

    def _select_intelligence_level(self) -> None:
        if self.intelligence_level not in _ALLOWED_LEVELS:
            raise OpenCLIWebModelError("OPENCLI_WEB_MODEL_LEVEL_INVALID")
        self._run(
            [
                self.executable,
                "chatgpt",
                "model",
                self.intelligence_level,
                "--site-session",
                self.site_session,
                "-f",
                "json",
            ]
        )

    def _render_prompt(
        self,
        messages: Sequence[BaseMessage],
        tools: Sequence[Mapping[str, Any]],
        tool_choice: str | None,
    ) -> str:
        envelope = {
            "protocol": OPENCLI_WEB_PROTOCOL,
            "role": "model_transport_only",
            "rules": [
                "Repository tools are executed by the external Open SWE runtime, not by ChatGPT Web.",
                "If a tool is needed, return one JSON object with type=tool_call, name, and arguments.",
                "If no tool is needed, return one JSON object with type=final and content.",
                "Do not claim that a tool ran unless a later tool message reports its result.",
            ],
            "messages": [_message_payload(message) for message in messages],
            "tools": [dict(tool) for tool in tools],
            "tool_choice": tool_choice or "auto",
        }
        return json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _extract_ask_response(stdout: str) -> str:
        try:
            rows = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise OpenCLIWebModelError("OPENCLI_WEB_RESPONSE_INVALID") from exc
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], Mapping):
            raise OpenCLIWebModelError("OPENCLI_WEB_RESPONSE_INVALID")
        response = rows[0].get("response")
        if not isinstance(response, str) or not response.strip():
            raise OpenCLIWebModelError("OPENCLI_WEB_RESPONSE_INVALID")
        return response.strip()

    @staticmethod
    def _response_message(response: str, tools: Sequence[Mapping[str, Any]]) -> AIMessage:
        allowed = {name for tool in tools if (name := _tool_name(tool))}
        try:
            envelope = json.loads(response)
        except json.JSONDecodeError:
            return AIMessage(content=response)
        if not isinstance(envelope, Mapping):
            return AIMessage(content=response)
        kind = envelope.get("type")
        if kind == "final" and isinstance(envelope.get("content"), str):
            return AIMessage(content=str(envelope["content"]))
        if kind != "tool_call":
            return AIMessage(content=response)
        name = envelope.get("name")
        arguments = envelope.get("arguments")
        if not isinstance(name, str) or name not in allowed or not isinstance(arguments, Mapping):
            raise OpenCLIWebModelError("OPENCLI_WEB_TOOL_CALL_INVALID")
        args = dict(arguments)
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": name,
                    "args": args,
                    "id": _tool_call_id(name, args, response),
                    "type": "tool_call",
                }
            ],
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager
        tools = kwargs.get("tools") or []
        if not isinstance(tools, Sequence) or isinstance(tools, (str, bytes)):
            raise OpenCLIWebModelError("OPENCLI_WEB_TOOLS_INVALID")
        normalized_tools = [dict(tool) for tool in tools if isinstance(tool, Mapping)]
        if len(normalized_tools) != len(tools):
            raise OpenCLIWebModelError("OPENCLI_WEB_TOOLS_INVALID")
        tool_choice = kwargs.get("tool_choice")
        if tool_choice is not None and not isinstance(tool_choice, str):
            raise OpenCLIWebModelError("OPENCLI_WEB_TOOL_CHOICE_INVALID")

        self._select_intelligence_level()
        prompt = self._render_prompt(messages, normalized_tools, tool_choice)
        stdout = self._run(
            [
                self.executable,
                "chatgpt",
                "ask",
                prompt,
                "--new",
                "--timeout",
                str(self.timeout_seconds),
                "--site-session",
                self.site_session,
                "-f",
                "json",
            ]
        )
        response = self._extract_ask_response(stdout)
        message = self._response_message(response, normalized_tools)
        return ChatResult(generations=[ChatGeneration(message=message)])
