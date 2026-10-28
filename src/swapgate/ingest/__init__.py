"""Trace ingestors: LiteLLM, OpenTelemetry GenAI spans, sec-MCP tool-call logs."""

from .litellm import parse_litellm
from .otel import parse_otel_span
from .secmcp import parse_secmcp

__all__ = ["parse_litellm", "parse_otel_span", "parse_secmcp"]
