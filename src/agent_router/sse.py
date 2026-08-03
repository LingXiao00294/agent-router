"""Incrementally decode bounded Server-Sent Events streams."""

from __future__ import annotations

import re
from dataclasses import dataclass

_LINE_END_RE = rb"(?:\r\n|\r(?!\n)|(?<!\r)\n)"
_EVENT_SEPARATOR_RE = re.compile(_LINE_END_RE + _LINE_END_RE)
_LINE_SPLIT_RE = re.compile(rb"\r\n|\r|\n")
_MAX_SEPARATOR_BYTES = 4
_DEFAULT_MAX_EVENT_BYTES = 1024 * 1024


class SSEDecodeError(ValueError):
    """Raised when an SSE event exceeds the decoder's configured size limit."""


@dataclass(frozen=True, slots=True)
class SSEEvent:
    """Represent one decoded SSE event with its joined data payload."""

    event: str
    data: bytes


class SSEDecoder:
    """Decode complete SSE events across arbitrary byte chunk boundaries.

    The decoder follows SSE field rules for comments, optional spaces after
    colons, arbitrary field order, and multiple ``data`` lines. Incomplete
    events remain buffered until a blank line arrives. The size limit bounds
    memory use when an upstream never terminates an event.

    Args:
        max_event_bytes: Maximum bytes allowed before an event separator.

    Raises:
        ValueError: If ``max_event_bytes`` is not positive.
    """

    def __init__(self, max_event_bytes: int = _DEFAULT_MAX_EVENT_BYTES) -> None:
        if max_event_bytes <= 0:
            raise ValueError("max_event_bytes must be positive")
        self._max_event_bytes = max_event_bytes
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> list[SSEEvent]:
        """Consume bytes and return every newly completed SSE event.

        Args:
            chunk: Next raw byte chunk from the upstream response.

        Returns:
            Complete events terminated by an SSE blank line. Events without
            any ``data`` field are ignored as required by the SSE dispatch
            rules.

        Raises:
            SSEDecodeError: If a complete or buffered event exceeds the size
                limit.
        """
        previous_length = len(self._buffer)
        self._buffer.extend(chunk)
        events: list[SSEEvent] = []
        search_from = max(0, previous_length - (_MAX_SEPARATOR_BYTES - 1))
        separator = _EVENT_SEPARATOR_RE.search(self._buffer, search_from)
        while separator is not None:
            raw_event = bytes(self._buffer[: separator.start()])
            del self._buffer[: separator.end()]
            self._check_size(raw_event)
            event = self._parse_event(raw_event)
            if event is not None:
                events.append(event)
            separator = _EVENT_SEPARATOR_RE.search(self._buffer)
        self._check_size(self._buffer)
        return events

    def _check_size(self, raw_event: bytes | bytearray) -> None:
        if len(raw_event) > self._max_event_bytes:
            self._buffer.clear()
            raise SSEDecodeError(f"SSE event exceeds {self._max_event_bytes} bytes")

    @staticmethod
    def _parse_event(raw_event: bytes) -> SSEEvent | None:
        event_type = "message"
        data_lines: list[bytes] = []
        for line in _LINE_SPLIT_RE.split(raw_event):
            if not line or line.startswith(b":"):
                continue
            field, separator, value = line.partition(b":")
            if separator and value.startswith(b" "):
                value = value[1:]
            if field == b"event":
                event_type = value.decode("utf-8", errors="replace") or "message"
            elif field == b"data":
                data_lines.append(value)
        if not data_lines:
            return None
        return SSEEvent(event=event_type, data=b"\n".join(data_lines))
