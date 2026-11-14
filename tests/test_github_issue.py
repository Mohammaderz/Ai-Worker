import io
import json

import pytest

from ai_worker.sources.github_issue import (
    GitHubIssueError,
    inspect_github_issue,
    parse_github_issue_url,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return json.dumps(self.payload).encode("utf-8")


def test_parse_canonical_github_issue_url():
    assert parse_github_issue_url("https://github.com/acme/widget/issues/42") == (
        "acme", "widget", 42
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/acme/widget/issues/42",
        "https://evil.example/acme/widget/issues/42",
        "https://github.com/acme/widget/pull/42",
        "https://user:pass@github.com/acme/widget/issues/42",
        "https://github.com/acme/widget/issues/42?redirect=evil",
    ],
)
def test_reject_unsupported_issue_urls(url):
    with pytest.raises(GitHubIssueError):
        parse_github_issue_url(url)


def test_inspect_fetches_only_public_issue_metadata(monkeypatch):
    payload = {
        "html_url": "https://github.com/acme/widget/issues/42",
        "title": "Fix API retry handling",
        "state": "open",
        "body": "Add tests for retry backoff.",
        "labels": [{"name": "bug"}, {"name": "good first issue"}],
        "updated_at": "2026-11-14T10:00:00Z",
    }
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        seen["headers"] = dict(request.header_items())
        return FakeResponse(payload)

    monkeypatch.setattr("ai_worker.sources.github_issue.urlopen", fake_urlopen)
    brief = inspect_github_issue("https://github.com/acme/widget/issues/42")

    assert brief.title == "Fix API retry handling"
    assert brief.state == "open"
    assert brief.labels == ["bug", "good first issue"]
    assert seen["url"] == "https://api.github.com/repos/acme/widget/issues/42"
    assert seen["timeout"] == 15


def test_reject_pull_request_response(monkeypatch):
    payload = {
        "html_url": "https://github.com/acme/widget/pull/42",
        "pull_request": {"url": "https://api.github.com/repos/acme/widget/pulls/42"},
    }
    monkeypatch.setattr(
        "ai_worker.sources.github_issue.urlopen",
        lambda request, timeout: FakeResponse(payload),
    )
    with pytest.raises(GitHubIssueError):
        inspect_github_issue("https://github.com/acme/widget/issues/42")
