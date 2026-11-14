"""Read-only inspection of public GitHub issues linked by task boards.

Issue bodies are untrusted data. This module fetches metadata only and never
executes commands or follows links embedded in issue text.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


API_ROOT = "https://api.github.com/repos"
USER_AGENT = "AI-Worker/0.2 (+https://github.com/Mohammaderz/Ai-Worker)"
MAX_RESPONSE_BYTES = 1024 * 1024


class GitHubIssueError(RuntimeError):
    pass


@dataclass(slots=True)
class ResearchBrief:
    url: str
    title: str
    repository: str
    number: int
    state: str
    body: str
    labels: list[str]
    updated_at: str

    def to_dict(self) -> dict:
        return asdict(self)


def parse_github_issue_url(value: str) -> tuple[str, str, int]:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or parsed.query
            or parsed.fragment
        ):
            raise GitHubIssueError("Only canonical public github.com issue URLs are supported")
        match = re.fullmatch(
            r"/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/issues/([1-9][0-9]*)/?",
            parsed.path,
        )
        if not match:
            raise GitHubIssueError("URL must point to /owner/repository/issues/number")
        owner, repository, number = match.groups()
        if repository.endswith(".git"):
            raise GitHubIssueError("Repository URL is not an issue URL")
        return owner, repository, int(number)
    except (TypeError, ValueError) as exc:
        if isinstance(exc, GitHubIssueError):
            raise
        raise GitHubIssueError("Invalid GitHub issue URL") from exc


def inspect_github_issue(url: str, timeout: int = 15) -> ResearchBrief:
    owner, repository, number = parse_github_issue_url(url)
    api_url = f"{API_ROOT}/{owner}/{repository}/issues/{number}"
    request = Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise GitHubIssueError("GitHub issue response exceeded the 1 MiB safety limit")
        data = json.loads(raw.decode("utf-8"))
    except GitHubIssueError:
        raise
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise GitHubIssueError(f"Could not inspect public GitHub issue: {exc}") from exc

    if not isinstance(data, dict):
        raise GitHubIssueError("Unexpected GitHub API response")
    if "pull_request" in data:
        raise GitHubIssueError("This URL resolves to a pull request; only issues are supported")
    returned_url = data.get("html_url") or url
    parsed_returned = urlsplit(returned_url)
    if parsed_returned.scheme != "https" or parsed_returned.hostname != "github.com":
        raise GitHubIssueError("GitHub API returned a non-canonical issue URL")

    labels = data.get("labels") or []
    if not isinstance(labels, list):
        labels = []
    label_names = [
        str(label.get("name"))
        for label in labels
        if isinstance(label, dict) and label.get("name")
    ]
    return ResearchBrief(
        url=returned_url,
        title=str(data.get("title") or "Untitled issue"),
        repository=f"{owner}/{repository}",
        number=number,
        state=str(data.get("state") or "unknown"),
        body=str(data.get("body") or ""),
        labels=label_names,
        updated_at=str(data.get("updated_at") or ""),
    )
