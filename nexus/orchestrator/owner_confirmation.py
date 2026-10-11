"""Host-mediated Owner confirmation for authority-creating gateway tools (#1750).

An Owner decision must not be a value the model can type into tool arguments.
Confirmation is therefore requested by the gateway itself through MCP
elicitation: the host renders the draft to the human and returns the answer on
the protocol channel, outside the model's tool-call arguments.

Assurance is bounded by the host.  Form elicitation proves that the host
returned "accept" for this exact draft, request id and deadline; it carries no
cryptographic user identity.  The evidence therefore records what the host and
the local process can attest (client identity, local OS principal) and labels
the assurance level instead of claiming more.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Optional, Protocol, TextIO

ELICITATION_PROTOCOL_VERSIONS = ("2025-06-18", "2025-11-25")
NEGOTIATED_ELICITATION_PROTOCOL = "2025-06-18"
LEGACY_PROTOCOL_VERSION = "2024-11-05"
CONFIRMATION_WINDOW = timedelta(minutes=5)
ASSURANCE_LEVEL = "HOST_ELICITATION_LOCAL_SESSION"
APPROVAL_SCHEMA = {
    "type": "object",
    "properties": {
        "approve": {
            "type": "boolean",
            "title": "Approve exactly this grant",
            "description": "Approve only if you, the Owner, requested this grant.",
        }
    },
    "required": ["approve"],
}


class OwnerConfirmationError(Exception):
    """A typed refusal; the message is the stable reason code."""


@dataclass(frozen=True)
class OwnerConfirmationRequest:
    tool: str
    draft: Mapping[str, Any]
    draft_hash: str
    request_id: str
    nonce: str
    requested_at: datetime
    deadline: datetime
    message: str

    @classmethod
    def build(
        cls,
        *,
        tool: str,
        draft: Mapping[str, Any],
        summary_lines: tuple[str, ...],
        now: datetime,
        not_after: Optional[datetime] = None,
    ) -> "OwnerConfirmationRequest":
        draft_hash = hashlib.sha256(
            json.dumps(
                dict(draft), sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()
        nonce = secrets.token_hex(16)
        deadline = now + CONFIRMATION_WINDOW
        if not_after is not None and not_after < deadline:
            deadline = not_after
        message = "\n".join((
            "Nexus Owner confirmation required.",
            f"Tool: {tool}",
            *summary_lines,
            f"Draft hash: sha256:{draft_hash}",
            f"Request: {nonce[:12]}  Respond by: {deadline.isoformat()}",
            "Approve only if you requested exactly this grant.",
        ))
        return cls(
            tool=tool,
            draft=dict(draft),
            draft_hash=draft_hash,
            request_id=f"nexus-owner-confirm-{nonce}",
            nonce=nonce,
            requested_at=now,
            deadline=deadline,
            message=message,
        )


@dataclass(frozen=True)
class OwnerConfirmationEvidence:
    schema: str
    assurance_level: str
    channel: str
    tool: str
    draft_hash: str
    message_sha256: str
    request_id: str
    nonce: str
    requested_at: str
    responded_at: str
    deadline: str
    action: str
    protocol_version: str
    client_info: Mapping[str, Any]
    local_principal: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def evidence_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()


class OwnerConfirmationChannel(Protocol):
    def confirm(self, request: OwnerConfirmationRequest) -> OwnerConfirmationEvidence: ...


class UnavailableConfirmationChannel:
    """Default channel: no trusted confirmation path exists, so nothing is issued."""

    def confirm(self, request: OwnerConfirmationRequest) -> OwnerConfirmationEvidence:
        raise OwnerConfirmationError("OWNER_CONFIRMATION_CHANNEL_UNAVAILABLE")


def client_supports_form_elicitation(protocol_version: str, capabilities: Any) -> bool:
    if protocol_version not in ELICITATION_PROTOCOL_VERSIONS:
        return False
    if not isinstance(capabilities, Mapping):
        return False
    elicitation = capabilities.get("elicitation")
    if not isinstance(elicitation, Mapping):
        return False
    # 2025-06-18 declares form support as an empty object; later revisions
    # list modes explicitly.
    return not elicitation or isinstance(elicitation.get("form"), Mapping)


def local_principal() -> str:
    try:
        return f"{getpass.getuser()}@uid:{os.getuid()}"
    except Exception:
        return "unknown"


class StdioElicitationChannel:
    """Ask the host on the live stdio session and wait for its answer.

    Only the response to this request id counts.  Arguments of the pending
    tool call, other responses, and anything after the deadline cannot turn
    into an acceptance.
    """

    def __init__(
        self,
        *,
        input_stream: TextIO,
        output_stream: TextIO,
        protocol_version: str,
        client_info: Mapping[str, Any],
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._input = input_stream
        self._output = output_stream
        self._protocol_version = protocol_version
        self._client_info = dict(client_info)
        self._clock = clock

    def _write(self, message: Mapping[str, Any]) -> None:
        self._output.write(json.dumps(dict(message), sort_keys=True, ensure_ascii=False) + "\n")
        self._output.flush()

    def confirm(self, request: OwnerConfirmationRequest) -> OwnerConfirmationEvidence:
        self._write({
            "jsonrpc": "2.0",
            "id": request.request_id,
            "method": "elicitation/create",
            "params": {"message": request.message, "requestedSchema": APPROVAL_SCHEMA},
        })
        while True:
            line = self._input.readline()
            if not line:
                raise OwnerConfirmationError("OWNER_CONFIRMATION_CHANNEL_CLOSED")
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                raise OwnerConfirmationError("OWNER_CONFIRMATION_MALFORMED") from exc
            if not isinstance(message, Mapping):
                raise OwnerConfirmationError("OWNER_CONFIRMATION_MALFORMED")
            method = message.get("method")
            if method is not None:
                if method == "notifications/cancelled":
                    raise OwnerConfirmationError("OWNER_CONFIRMATION_CANCELLED")
                if "id" in message:
                    if method == "ping":
                        self._write({"jsonrpc": "2.0", "id": message["id"], "result": {}})
                    else:
                        self._write({
                            "jsonrpc": "2.0",
                            "id": message["id"],
                            "error": {
                                "code": -32000,
                                "message": "gateway is awaiting Owner confirmation",
                            },
                        })
                continue
            if message.get("id") != request.request_id:
                # A response to something else can never answer this request.
                continue
            return self._evaluate(request, message)

    def _evaluate(
        self, request: OwnerConfirmationRequest, message: Mapping[str, Any]
    ) -> OwnerConfirmationEvidence:
        responded_at = self._clock()
        if "error" in message:
            raise OwnerConfirmationError("OWNER_CONFIRMATION_HOST_ERROR")
        result = message.get("result")
        if not isinstance(result, Mapping):
            raise OwnerConfirmationError("OWNER_CONFIRMATION_MALFORMED")
        action = result.get("action")
        if action == "decline":
            raise OwnerConfirmationError("OWNER_CONFIRMATION_DECLINED")
        if action == "cancel":
            raise OwnerConfirmationError("OWNER_CONFIRMATION_CANCELLED")
        if action != "accept":
            raise OwnerConfirmationError("OWNER_CONFIRMATION_MALFORMED")
        content = result.get("content")
        # The answer may only say yes or no; it can never carry scope.
        if not isinstance(content, Mapping) or set(content) != {"approve"}:
            raise OwnerConfirmationError("OWNER_CONFIRMATION_MALFORMED")
        if content["approve"] is not True:
            raise OwnerConfirmationError("OWNER_CONFIRMATION_DECLINED")
        if responded_at > request.deadline:
            raise OwnerConfirmationError("OWNER_CONFIRMATION_EXPIRED")
        return OwnerConfirmationEvidence(
            schema="nexus.owner_confirmation_evidence.v1",
            assurance_level=ASSURANCE_LEVEL,
            channel="mcp_elicitation_form_stdio",
            tool=request.tool,
            draft_hash=request.draft_hash,
            message_sha256=hashlib.sha256(request.message.encode("utf-8")).hexdigest(),
            request_id=request.request_id,
            nonce=request.nonce,
            requested_at=request.requested_at.isoformat(),
            responded_at=responded_at.isoformat(),
            deadline=request.deadline.isoformat(),
            action="accept",
            protocol_version=self._protocol_version,
            client_info=self._client_info,
            local_principal=local_principal(),
        )


__all__ = [
    "ASSURANCE_LEVEL",
    "CONFIRMATION_WINDOW",
    "ELICITATION_PROTOCOL_VERSIONS",
    "LEGACY_PROTOCOL_VERSION",
    "NEGOTIATED_ELICITATION_PROTOCOL",
    "OwnerConfirmationChannel",
    "OwnerConfirmationError",
    "OwnerConfirmationEvidence",
    "OwnerConfirmationRequest",
    "StdioElicitationChannel",
    "UnavailableConfirmationChannel",
    "client_supports_form_elicitation",
    "local_principal",
]
