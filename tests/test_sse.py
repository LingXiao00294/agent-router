from __future__ import annotations

import pytest

from agent_router.sse import SSEDecodeError, SSEDecoder, SSEEvent


def test_decoder_joins_data_lines_across_chunks() -> None:
    decoder = SSEDecoder()
    raw = (
        b': keepalive\r\nevent: message_delta\r\ndata: {"usage":\r\n'
        b'data: {"output_tokens": 7}}\r\n\r\n'
    )
    events: list[SSEEvent] = []

    for byte in raw:
        events.extend(decoder.feed(bytes((byte,))))

    assert events == [
        SSEEvent(
            event="message_delta",
            data=b'{"usage":\n{"output_tokens": 7}}',
        )
    ]


def test_decoder_returns_multiple_events_and_ignores_data_less_blocks() -> None:
    decoder = SSEDecoder()

    events = decoder.feed(b"id: 1\n\ndata: first\n\ndata: second\ndata: line\n\n")

    assert events == [
        SSEEvent(event="message", data=b"first"),
        SSEEvent(event="message", data=b"second\nline"),
    ]


def test_decoder_rejects_an_unterminated_oversized_event() -> None:
    decoder = SSEDecoder(max_event_bytes=8)

    with pytest.raises(SSEDecodeError, match="exceeds 8 bytes"):
        decoder.feed(b"data: 123")
