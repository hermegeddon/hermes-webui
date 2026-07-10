"""Regression tests for issue #1765 false-positive "No response from provider".

When the agent returns a soft partial result but the transcript already
contains a final assistant answer for the current turn, the WebUI settlement
path must not downgrade the turn to the generic ``no_response`` card. Hard
failures and tool-limit outcomes must remain terminal.
"""
from __future__ import annotations

from api.streaming import (
    _agent_result_terminal_failure,
    _assistant_reply_added_after_current_turn,
    _classify_provider_error,
    _merged_transcript_lacks_final_assistant_answer,
)


_PREV = [
    {"role": "user", "content": "hi", "id": "u1"},
    {"role": "assistant", "content": "hello", "id": "a1"},
]
_USER_TEXT = "what is 2+2"
_RESULT_MESSAGES = _PREV + [
    {"role": "user", "content": _USER_TEXT, "id": "u2"},
    {"role": "assistant", "content": "2 + 2 equals 4.", "id": "a2"},
]


def _make_result(status: str, *, partial: bool = False, failed: bool = False, error=None) -> dict:
    result: dict = {"status": status, "messages": list(_RESULT_MESSAGES)}
    if partial:
        result["partial"] = True
    if failed:
        result["failed"] = True
    if error is not None:
        result["error"] = error
    return result


def test_failed_result_with_final_answer_is_still_detected_as_terminal():
    """An answer does not erase the failed result's terminal shape."""
    result = _make_result("failed")
    assert _agent_result_terminal_failure(result)
    assert _assistant_reply_added_after_current_turn(
        result["messages"], list(_PREV), _USER_TEXT
    )
    assert not _merged_transcript_lacks_final_assistant_answer(
        _PREV, list(_PREV), result["messages"], _USER_TEXT, drop_replayed_assistant=False
    )

    _last_err = result.get("error") or ""
    classification = _classify_provider_error(
        str(_last_err) if _last_err else "",
        _last_err,
        silent_failure=not bool(_last_err),
    )
    # The classifier still returns no_response for empty errors. Settlement may
    # suppress it only for a soft partial result, not this hard failure.
    assert classification["type"] == "no_response"


def test_terminal_failure_suppression_requires_final_assistant_answer():
    """A failed result without a final answer must still be terminal."""
    result = _make_result("failed")
    # Drop the assistant answer so the transcript lacks a final answer.
    result["messages"] = result["messages"][:-1]
    assert _agent_result_terminal_failure(result)
    assert not _assistant_reply_added_after_current_turn(
        result["messages"], list(_PREV), _USER_TEXT
    )
    assert _merged_transcript_lacks_final_assistant_answer(
        _PREV, list(_PREV), result["messages"], _USER_TEXT, drop_replayed_assistant=False
    )


def test_partial_terminal_failure_with_final_answer_is_not_downgraded():
    """A partial result that produced a final answer should not be downgraded."""
    result = _make_result("partial", partial=True)
    assert _agent_result_terminal_failure(result)
    assert not _merged_transcript_lacks_final_assistant_answer(
        _PREV, list(_PREV), result["messages"], _USER_TEXT, drop_replayed_assistant=False
    )


def test_failed_flag_with_final_answer_is_still_detected_as_terminal():
    """A failed=True flag remains terminal even when an answer exists."""
    result = _make_result("ok", failed=True)
    assert _agent_result_terminal_failure(result)
    assert not _merged_transcript_lacks_final_assistant_answer(
        _PREV, list(_PREV), result["messages"], _USER_TEXT, drop_replayed_assistant=False
    )


def test_existing_soft_partial_suppression_still_allows_no_response_without_answer():
    """A partial result with no final answer must remain a terminal no_response."""
    result = _make_result("partial", partial=True)
    result["messages"] = result["messages"][:-1]
    _last_err = ""
    classification = _classify_provider_error(
        str(_last_err) if _last_err else "",
        _last_err,
        silent_failure=not bool(_last_err),
    )
    assert classification["type"] == "no_response"
    assert _merged_transcript_lacks_final_assistant_answer(
        _PREV, list(_PREV), result["messages"], _USER_TEXT, drop_replayed_assistant=False
    )


def test_concrete_provider_error_still_emits_error_even_with_final_answer():
    """A result that carries a real provider error should still surface that error."""
    result = _make_result("failed", error="HTTP 429: quota exceeded")
    assert _agent_result_terminal_failure(result)
    assert not _merged_transcript_lacks_final_assistant_answer(
        _PREV, list(_PREV), result["messages"], _USER_TEXT, drop_replayed_assistant=False
    )
    _last_err = result.get("error") or ""
    classification = _classify_provider_error(
        str(_last_err) if _last_err else "",
        _last_err,
        silent_failure=not bool(_last_err),
    )
    assert classification["type"] == "quota_exhausted"
