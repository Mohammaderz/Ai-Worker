from ai_worker import cli
from ai_worker.sandbox import SandboxResult


def test_cli_sandbox_run_invokes_runner(monkeypatch, tmp_path, capsys):
    root = tmp_path / "scratch"
    root.mkdir()
    workspace = root / "task"
    workspace.mkdir()
    captured = {}

    def fake_runner(workspace_arg, command, **kwargs):
        captured["workspace"] = workspace_arg
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SandboxResult(0, "passed", "")

    monkeypatch.setattr(cli, "run_in_sandbox", fake_runner)
    monkeypatch.setattr(
        "sys.argv",
        [
            "ai-worker", "sandbox", "run",
            "--workspace", str(workspace),
            "--scratch-root", str(root),
            "--timeout", "90",
            "--", "python", "-m", "pytest",
        ],
    )

    assert cli.main() == 0
    assert captured["command"] == ["python", "-m", "pytest"]
    assert captured["kwargs"]["timeout_seconds"] == 90
    assert "passed" in capsys.readouterr().out



def test_cli_plan_uses_local_planner(monkeypatch, capsys):
    from types import SimpleNamespace

    captured = {}

    def fake_inspect(url):
        captured["url"] = url
        return "brief"

    def fake_plan(brief, model=None, timeout=300):
        captured["brief"] = brief
        captured["model"] = model
        captured["timeout"] = timeout
        return SimpleNamespace(to_dict=lambda: {"summary": "Plan ready"})

    monkeypatch.setattr(cli, "inspect_github_issue", fake_inspect)
    monkeypatch.setattr(cli, "plan_github_issue", fake_plan)
    monkeypatch.setattr(
        "sys.argv",
        ["ai-worker", "plan", "--url", "https://github.com/acme/widget/issues/42",
         "--model", "local-coder", "--timeout", "120"],
    )

    assert cli.main() == 0
    assert captured["brief"] == "brief"
    assert captured["model"] == "local-coder"
    assert captured["timeout"] == 120
    assert "Plan ready" in capsys.readouterr().out



def test_cli_patch_draft_uses_local_developer(monkeypatch, capsys, tmp_path):
    from types import SimpleNamespace

    workspace = tmp_path / "repo"
    workspace.mkdir()
    captured = {}

    monkeypatch.setattr(cli, "inspect_github_issue", lambda url: "issue")

    def fake_draft(brief, workspace_arg, model=None, timeout=600):
        captured["brief"] = brief
        captured["workspace"] = workspace_arg
        captured["model"] = model
        return SimpleNamespace(status="patch", diff="diff --git a/x b/x", to_dict=lambda: {"summary": "Draft ready"})

    monkeypatch.setattr(cli, "draft_patch", fake_draft)
    monkeypatch.setattr(
        "sys.argv",
        ["ai-worker", "patch", "draft", "--url", "https://github.com/a/b/issues/1",
         "--workspace", str(workspace), "--model", "local"],
    )

    assert cli.main() == 0
    assert captured["brief"] == "issue"
    assert captured["model"] == "local"
    assert "Draft ready" in capsys.readouterr().out


def test_cli_patch_apply_uses_sandbox(monkeypatch, capsys, tmp_path):
    from types import SimpleNamespace

    root = tmp_path / "scratch"
    root.mkdir()
    workspace = root / "repo"
    workspace.mkdir()
    diff_file = tmp_path / "change.patch"
    diff_file.write_text("diff text", encoding="utf-8")
    captured = {}

    def fake_apply(diff, workspace_arg, **kwargs):
        captured["diff"] = diff
        captured["workspace"] = workspace_arg
        captured["kwargs"] = kwargs
        return SimpleNamespace(applied=True, message="Patch applied.", changed_files=["x.py"], stderr="")

    monkeypatch.setattr(cli, "apply_patch_in_sandbox", fake_apply)
    monkeypatch.setattr(
        "sys.argv",
        ["ai-worker", "patch", "apply", "--diff-file", str(diff_file),
         "--workspace", str(workspace), "--scratch-root", str(root)],
    )

    assert cli.main() == 0
    assert captured["diff"] == "diff text"
    assert captured["kwargs"]["scratch_root"] == str(root)
    assert "Patch applied." in capsys.readouterr().out



def test_cli_prepare_clones_public_issue_repository(monkeypatch, capsys, tmp_path):
    from types import SimpleNamespace

    root = tmp_path / "scratch"
    workspace = root / "task-42"
    captured = {}
    monkeypatch.setattr(cli, "inspect_github_issue", lambda url: SimpleNamespace(repository="acme/widget"))

    def fake_clone(repository, workspace_arg, **kwargs):
        captured["repository"] = repository
        captured["workspace"] = workspace_arg
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            path=str(workspace),
            repository=repository,
            message="Cloned",
        )

    monkeypatch.setattr(cli, "clone_public_github_repo", fake_clone)
    monkeypatch.setattr(
        "sys.argv",
        ["ai-worker", "prepare", "--url", "https://github.com/acme/widget/issues/42",
         "--workspace", str(workspace), "--scratch-root", str(root)],
    )

    assert cli.main() == 0
    assert captured["repository"] == "acme/widget"
    assert captured["kwargs"]["scratch_root"] == str(root)
    assert "Cloned" in capsys.readouterr().out



def test_cli_pipeline_refreshes_and_resolves_jobbi_gig(monkeypatch, capsys, tmp_path):
    from types import SimpleNamespace

    captured = {}
    fake_gig = SimpleNamespace(
        id="algora:task-42",
        url="https://github.com/acme/widget/issues/42",
        reward_amount=25,
        currency="USD",
    )
    fake_db = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(cli, "fetch_gigs", lambda limit: ["fresh-gig"])
    monkeypatch.setattr(cli, "connect", lambda path: fake_db)
    monkeypatch.setattr(cli, "upsert_gigs", lambda db, gigs: captured.update(db=db, gigs=gigs))
    monkeypatch.setattr(cli, "resolve_eligible_gig", lambda gig_id, gigs, min_reward: fake_gig)

    def fake_pipeline(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return SimpleNamespace(status="ready_for_human_review", to_dict=lambda: {"status": "ready_for_human_review"})

    monkeypatch.setattr(cli, "run_pipeline", fake_pipeline)
    monkeypatch.setattr(
        "sys.argv",
        ["ai-worker", "pipeline", "--gig-id", "algora:task-42",
         "--db", str(tmp_path / "ledger.sqlite3"),
         "--scratch-root", str(tmp_path / "scratch"),
         "--output-root", str(tmp_path / "proposals"), "--reviewer-model", "review-coder"],
    )

    assert cli.main() == 0
    assert captured["gigs"] == ["fresh-gig"]
    assert captured["url"] == fake_gig.url
    assert captured["kwargs"]["reward_amount"] == 25
    assert captured["kwargs"]["currency"] == "USD"
    assert captured["kwargs"]["reviewer_model"] == "review-coder"
    assert "ready_for_human_review" in capsys.readouterr().out
