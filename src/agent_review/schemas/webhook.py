from pydantic import BaseModel


class PullRequestInfo(BaseModel):
    number: int
    draft: bool = False
    head_sha: str
    base_sha: str


class SenderInfo(BaseModel):
    login: str
    type: str


class RepositoryInfo(BaseModel):
    full_name: str


class InstallationInfo(BaseModel):
    id: int


class GitHubWebhookPayload(BaseModel):
    action: str
    pull_request: PullRequestInfo
    sender: SenderInfo
    repository: RepositoryInfo
    installation: InstallationInfo


class WebhookHeaders(BaseModel):
    event: str
    delivery_id: str
    signature: str | None
