"""Pure execution ports; implementations belong outside the product core."""

from dataclasses import dataclass

from product.protocol import IMPLEMENTATION_SCHEMA, PUBLIC_PROTOCOL_VERSION


@dataclass(frozen=True)
class ExecutionRequest:
    operation: str
    protocol_version: str = PUBLIC_PROTOCOL_VERSION
    implementation_schema: str = IMPLEMENTATION_SCHEMA


@dataclass(frozen=True)
class ExecutionResponse:
    observations: tuple[object, ...]
