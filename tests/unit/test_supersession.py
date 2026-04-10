import uuid

from agent_review.models import ReviewState
from agent_review.pipeline.supersession import supersede_active_runs
from tests.factories import build_review_run


async def test_new_push_supersedes_active_run(db_session) -> None:
    old_run = build_review_run(
        repo="owner/repo",
        pr_number=12,
        head_sha="a" * 40,
        delivery_id=str(uuid.uuid4()),
        state=ReviewState.PENDING,
    )
    db_session.add(old_run)
    await db_session.flush()

    superseded_ids = await supersede_active_runs(db_session, "owner/repo", 12, "b" * 40)

    assert str(old_run.id) in superseded_ids
    assert old_run.state == ReviewState.SUPERSEDED


async def test_noop_if_no_active_runs(db_session) -> None:
    superseded_ids = await supersede_active_runs(db_session, "owner/repo", 13, "a" * 40)
    assert superseded_ids == []


async def test_same_sha_not_superseded(db_session) -> None:
    run = build_review_run(
        repo="owner/repo",
        pr_number=14,
        head_sha="c" * 40,
        delivery_id=str(uuid.uuid4()),
        state=ReviewState.PENDING,
    )
    db_session.add(run)
    await db_session.flush()

    superseded_ids = await supersede_active_runs(db_session, "owner/repo", 14, "c" * 40)

    assert superseded_ids == []
    assert run.state == ReviewState.PENDING


async def test_terminal_runs_not_superseded(db_session) -> None:
    completed = build_review_run(
        repo="owner/repo",
        pr_number=15,
        head_sha="d" * 40,
        delivery_id=str(uuid.uuid4()),
        state=ReviewState.COMPLETED,
    )
    failed = build_review_run(
        repo="owner/repo",
        pr_number=15,
        head_sha="e" * 40,
        delivery_id=str(uuid.uuid4()),
        state=ReviewState.FAILED,
    )
    superseded = build_review_run(
        repo="owner/repo",
        pr_number=15,
        head_sha="f" * 40,
        delivery_id=str(uuid.uuid4()),
        state=ReviewState.SUPERSEDED,
    )
    db_session.add_all([completed, failed, superseded])
    await db_session.flush()

    superseded_ids = await supersede_active_runs(db_session, "owner/repo", 15, "g" * 40)

    assert superseded_ids == []
    assert completed.state == ReviewState.COMPLETED
    assert failed.state == ReviewState.FAILED
    assert superseded.state == ReviewState.SUPERSEDED
