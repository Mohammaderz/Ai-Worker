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
