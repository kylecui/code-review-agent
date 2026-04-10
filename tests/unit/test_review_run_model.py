from datetime import datetime
from uuid import uuid4

import pytest

from agent_review.models.enums import ReviewState, TriggerEvent
from agent_review.models.review_run import InvalidTransition, ReviewRun


def _make_review_run(state: ReviewState) -> ReviewRun:
    return ReviewRun(
        id=uuid4(),
        repo="org/repo",
        pr_number=1,
        head_sha="a" * 40,
        base_sha="b" * 40,
        installation_id=123,
        attempt=1,
        state=state,
        trigger_event=TriggerEvent.OPENED,
        delivery_id=f"delivery-{uuid4()}",
    )


def test_all_valid_transitions_succeed() -> None:
    for from_state, to_states in ReviewRun.VALID_TRANSITIONS.items():
        for to_state in to_states:
            run = _make_review_run(from_state)
            run.transition(to_state)
            assert run.state == to_state


def test_terminal_states_invalid_to_any_state() -> None:
    terminal_states = {ReviewState.COMPLETED, ReviewState.FAILED, ReviewState.SUPERSEDED}
    for terminal in terminal_states:
        for target in ReviewState:
            run = _make_review_run(terminal)
            with pytest.raises(InvalidTransition):
                run.transition(target)


def test_non_adjacent_transitions_raise() -> None:
    invalid_pairs = [
        (ReviewState.PENDING, ReviewState.COLLECTING),
        (ReviewState.CLASSIFYING, ReviewState.REASONING),
        (ReviewState.COLLECTING, ReviewState.PUBLISHING),
        (ReviewState.NORMALIZING, ReviewState.COMPLETED),
        (ReviewState.REASONING, ReviewState.SUPERSEDED),
        (ReviewState.DECIDING, ReviewState.CLASSIFYING),
        (ReviewState.PUBLISHING, ReviewState.PENDING),
    ]

    for from_state, to_state in invalid_pairs:
        if to_state in ReviewRun.VALID_TRANSITIONS[from_state]:
            continue
        run = _make_review_run(from_state)
        with pytest.raises(InvalidTransition):
            run.transition(to_state)


def test_is_terminal_for_terminal_states() -> None:
    assert _make_review_run(ReviewState.COMPLETED).is_terminal
    assert _make_review_run(ReviewState.FAILED).is_terminal
    assert _make_review_run(ReviewState.SUPERSEDED).is_terminal


def test_is_active_for_non_terminal_states() -> None:
    non_terminal_states = [
        ReviewState.PENDING,
        ReviewState.CLASSIFYING,
        ReviewState.COLLECTING,
        ReviewState.NORMALIZING,
        ReviewState.REASONING,
        ReviewState.DECIDING,
        ReviewState.PUBLISHING,
    ]

    for state in non_terminal_states:
        assert _make_review_run(state).is_active


def test_completed_at_set_on_terminal_transition() -> None:
    run = _make_review_run(ReviewState.PUBLISHING)
    assert run.completed_at is None

    run.transition(ReviewState.COMPLETED)

    assert run.completed_at is not None
    assert isinstance(run.completed_at, datetime)
