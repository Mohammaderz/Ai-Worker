import argparse
import json
from pathlib import Path

from ai_worker.developer import PatchError, apply_patch_in_sandbox, draft_patch
from ai_worker.planner import OllamaError, plan_github_issue
from ai_worker.report import write_report
from ai_worker.sandbox import DEFAULT_IMAGE, SandboxError, run_in_sandbox
from ai_worker.scoring import evaluate
from ai_worker.sources.github_issue import GitHubIssueError, inspect_github_issue
from ai_worker.sources.jobbi import FeedError, fetch_gigs
from ai_worker.storage import connect, upsert_gigs


def main() -> int:
    parser = argparse.ArgumentParser(prog="ai-worker")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("--url", required=True)

    plan = sub.add_parser("plan")
    plan.add_argument("--url", required=True)
    plan.add_argument("--model")
    plan.add_argument("--timeout", type=int, default=300)

    patch = sub.add_parser("patch")
    patch_sub = patch.add_subparsers(dest="patch_command", required=True)
    patch_draft = patch_sub.add_parser("draft")
    patch_draft.add_argument("--url", required=True)
    patch_draft.add_argument("--workspace", required=True)
    patch_draft.add_argument("--model")
    patch_draft.add_argument("--timeout", type=int, default=600)
    patch_draft.add_argument("--diff-output")
    patch_apply = patch_sub.add_parser("apply")
    patch_apply.add_argument("--diff-file", required=True)
    patch_apply.add_argument("--workspace", required=True)
    patch_apply.add_argument("--scratch-root", required=True)
    patch_apply.add_argument("--image", default=DEFAULT_IMAGE)
    patch_apply.add_argument("--timeout", type=int, default=120)

    scan = sub.add_parser("scan")
    scan.add_argument("--limit", type=int, default=100)
    scan.add_argument("--min-reward", type=float, default=5.0)
    scan.add_argument("--db", default="data/ai_worker.sqlite3")
    scan.add_argument("--output", default="reports/latest.md")

    sandbox = sub.add_parser("sandbox")
    sandbox_sub = sandbox.add_subparsers(dest="sandbox_command", required=True)
    sandbox_run = sandbox_sub.add_parser("run")
    sandbox_run.add_argument("--workspace", required=True)
    sandbox_run.add_argument("--scratch-root", required=True)
    sandbox_run.add_argument("--image", default=DEFAULT_IMAGE)
    sandbox_run.add_argument("--timeout", type=int, default=600)
    sandbox_run.add_argument("task_command", nargs=argparse.REMAINDER)

    args = parser.parse_args()
    if args.command == "inspect":
        try:
            brief = inspect_github_issue(args.url)
        except GitHubIssueError as exc:
            print(f"ERROR: {exc}")
            return 2
        print(json.dumps(brief.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "plan":
        try:
            brief = inspect_github_issue(args.url)
            task_plan = plan_github_issue(brief, model=args.model, timeout=args.timeout)
        except (GitHubIssueError, OllamaError) as exc:
            print(f"ERROR: {exc}")
            return 2
        print(json.dumps(task_plan.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "patch" and args.patch_command == "draft":
        try:
            brief = inspect_github_issue(args.url)
            proposal = draft_patch(
                brief, args.workspace, model=args.model, timeout=args.timeout
            )
        except (GitHubIssueError, PatchError) as exc:
            print(f"ERROR: {exc}")
            return 2
        if args.diff_output and proposal.diff:
            try:
                Path(args.diff_output).write_text(proposal.diff, encoding="utf-8")
            except OSError as exc:
                print(f"ERROR: could not save patch: {exc}")
                return 2
        print(json.dumps(proposal.to_dict(), ensure_ascii=False, indent=2))
        return 0 if proposal.diff else 3

    if args.command == "patch" and args.patch_command == "apply":
        try:
            diff = Path(args.diff_file).read_text(encoding="utf-8")
            result = apply_patch_in_sandbox(
                diff,
                args.workspace,
                scratch_root=args.scratch_root,
                image=args.image,
                timeout_seconds=args.timeout,
            )
        except (OSError, PatchError, SandboxError) as exc:
            print(f"ERROR: {exc}")
            return 2
        print(result.message)
        if result.changed_files:
            print("Changed files: " + ", ".join(result.changed_files))
        if result.stderr:
            print(result.stderr)
        return 0 if result.applied else 4

    if args.command == "scan":
        try:
            gigs = fetch_gigs(args.limit)
        except FeedError as exc:
            print(f"ERROR: {exc}")
            return 2
        db = connect(args.db)
        try:
            upsert_gigs(db, gigs)
            ranked, rejected = [], 0
            for gig in gigs:
                ok, score, reasons = evaluate(gig, args.min_reward)
                if ok:
                    ranked.append((gig, score, reasons))
                else:
                    rejected += 1
            ranked.sort(key=lambda row: row[1], reverse=True)
            report = write_report(ranked, args.output)
        finally:
            db.close()
        print(f"Fetched: {len(gigs)} | Qualified: {len(ranked)} | Filtered: {rejected}")
        print(f"Report: {report}")
        return 0

    if args.command == "sandbox" and args.sandbox_command == "run":
        task_command = args.task_command
        if task_command and task_command[0] == "--":
            task_command = task_command[1:]
        try:
            result = run_in_sandbox(
                args.workspace,
                task_command,
                scratch_root=args.scratch_root,
                image=args.image,
                timeout_seconds=args.timeout,
            )
        except SandboxError as exc:
            print(f"ERROR: {exc}")
            return 2
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        if result.stderr:
            print(result.stderr, end="" if result.stderr.endswith("\n") else "\n")
        print(f"Sandbox exit code: {result.exit_code}")
        return result.exit_code

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
