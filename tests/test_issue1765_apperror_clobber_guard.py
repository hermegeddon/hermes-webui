"""Regression tests for WebUI apperror session-snapshot clobbering.

When a terminal ``apperror`` event carries a ``d.session`` payload whose
``messages`` array is shorter than the current visible transcript (because
live streamed assistant text has not yet been persisted server-side), the
frontend must not discard the already-rendered live messages.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MESSAGES_JS = (ROOT / "static" / "messages.js").read_text(encoding="utf-8")


def _event_block(event_name: str) -> str:
    marker = f"source.addEventListener('{event_name}'"
    start = MESSAGES_JS.find(marker)
    assert start >= 0, f"missing {event_name} listener"
    brace = MESSAGES_JS.find("{", start)
    assert brace >= 0, f"missing {event_name} listener body"
    depth = 0
    i = brace
    while i < len(MESSAGES_JS):
        if MESSAGES_JS[i] == "{":
            depth += 1
        elif MESSAGES_JS[i] == "}":
            depth -= 1
            if depth == 0:
                return MESSAGES_JS[brace : i + 1]
        i += 1
    raise AssertionError(f"unclosed {event_name} listener body")


def _function_body(name: str) -> str:
    marker = f"async function {name}("
    start = MESSAGES_JS.find(marker)
    if start < 0:
        marker = f"function {name}("
        start = MESSAGES_JS.find(marker)
    assert start >= 0, f"missing function: {name}"
    brace = MESSAGES_JS.find("{", start)
    assert brace >= 0, f"missing {name} body"
    depth = 0
    i = brace
    while i < len(MESSAGES_JS):
        if MESSAGES_JS[i] == "{":
            depth += 1
        elif MESSAGES_JS[i] == "}":
            depth -= 1
            if depth == 0:
                return MESSAGES_JS[brace : i + 1]
        i += 1
    raise AssertionError(f"unclosed function body: {name}")


def _compact(text: str) -> str:
    return "".join(text.split())


def test_apperror_handler_reads_session_payload():
    body = _event_block("apperror")
    compact = _compact(body)
    assert "d.session&&typeofd.session==='object'" in compact


def test_apperror_uses_prefix_preservation_for_shorter_session_snapshot():
    """Direct apperror session replacement must use prefix-preservation logic."""
    body = _event_block("apperror")
    compact = _compact(body)
    # The handler must compute whether the server snapshot is a strict prefix
    # of the current visible transcript before replacing S.messages wholesale.
    assert "_stagedMessages.length<_currentVisibleMessages.length" in compact
    assert "_stagedMessages.every((message,idx)" in compact
    assert "_messageIdentityKey(message)" in compact
    assert "_messageIdentityKey(_currentVisibleMessages[idx])" in compact


def test_apperror_preserves_visible_suffix_when_snapshot_is_prefix():
    """If the server snapshot is a prefix, current visible suffix must survive."""
    body = _event_block("apperror")
    compact = _compact(body)
    assert "_preserveCurrentTranscript" in compact
    assert "_resolvedMessages=_preserveCurrentTranscript" in compact
    assert "_stagedMessages,..._currentVisibleMessages.slice(_stagedMessages.length)" in compact


def test_apperror_reuses_carry_forward_for_ephemeral_fields():
    """Ephemeral turn fields must still be carried across matched messages."""
    body = _event_block("apperror")
    compact = _compact(body)
    assert "_carryForwardEphemeralTurnFields" in compact


def test_apperror_payload_filter_strips_roleless_messages():
    """Server messages without a role must be filtered before merging."""
    body = _event_block("apperror")
    compact = _compact(body)
    assert "(d.session.messages||[]).filter(m=>m&&m.role)" in compact


def test_restore_settled_session_has_same_prefix_guard_shape():
    """The reference implementation in _restoreSettledSession keeps the same shape."""
    fn = _function_body("_restoreSettledSession")
    compact = _compact(fn)
    assert "_stagedMessages.length<_currentVisibleMessages.length" in compact
    assert "_stagedMessages.every((message,idx)" in compact
    assert "_preserveCurrentTranscript" in compact
    assert "_stagedMessages,..._currentVisibleMessages.slice(_stagedMessages.length)" in compact


def test_message_identity_key_exists():
    compact = _compact(MESSAGES_JS)
    assert "function_messageIdentityKey(m){" in compact
