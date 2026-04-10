from agent_review.schemas.webhook import (
    GitHubWebhookPayload,
    InstallationInfo,
    PullRequestInfo,
    RepositoryInfo,
    SenderInfo,
    WebhookHeaders,
)


def test_github_webhook_payload_valid_construction() -> None:
    payload = GitHubWebhookPayload(
        action="opened",
        pull_request=PullRequestInfo(
            number=42,
            draft=False,
            head_sha="a" * 40,
            base_sha="b" * 40,
        ),
        sender=SenderInfo(login="octocat", type="User"),
        repository=RepositoryInfo(full_name="owner/repo"),
        installation=InstallationInfo(id=1234),
    )

    assert payload.action == "opened"
    assert payload.pull_request.number == 42
    assert payload.repository.full_name == "owner/repo"
    assert payload.installation.id == 1234


def test_webhook_headers_valid_construction() -> None:
    headers = WebhookHeaders(
        event="pull_request",
        delivery_id="delivery-123",
        signature="sha256=abc123",
    )

    assert headers.event == "pull_request"
    assert headers.delivery_id == "delivery-123"
    assert headers.signature == "sha256=abc123"


def test_sender_info_type_field_accepts_user_or_bot_values() -> None:
    user_sender = SenderInfo(login="alice", type="User")
    bot_sender = SenderInfo(login="renovate[bot]", type="Bot")

    assert user_sender.type == "User"
    assert bot_sender.type == "Bot"


def test_pull_request_info_draft_true_and_false() -> None:
    draft_true = PullRequestInfo(
        number=1,
        draft=True,
        head_sha="c" * 40,
        base_sha="d" * 40,
    )
    draft_false = PullRequestInfo(
        number=2,
        draft=False,
        head_sha="e" * 40,
        base_sha="f" * 40,
    )

    assert draft_true.draft is True
    assert draft_false.draft is False
