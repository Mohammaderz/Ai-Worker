# Reviewer and QA result contracts

This implementation slice adds strict, serializable data contracts. It does **not** call an AI reviewer, execute repository commands, or connect review decisions to the task pipeline yet.

## Independent reviewer contract

The parser accepts a JSON string or decoded object and returns a validated ReviewResult. Malformed, oversized, unknown-field, duplicate-ID, unsafe-path, or inconsistent output raises ReviewContractError. Callers must fail closed; an exception is never an approval.

Decisions are approve, request_changes, and inconclusive. A request for changes must include at least one finding. An approval is rejected if any critical or high finding remains. Findings carry severity, concise description, file/line location where available, reproducible evidence, affected acceptance criterion, recommendation, confidence, and a verified flag. Paths must be relative and may not traverse directories or reference .git.

The module exposes REVIEW_RESPONSE_SCHEMA for a future model adapter. It does not include chain-of-thought fields and must not be extended to store private model reasoning.

## Deterministic QA result model

QACheck records a check's ID, name, status, whether it is required, argv (data only), exit code, duration, summary, and optional relative evidence path. Statuses are:

- passed
- failed
- skipped
- unavailable
- not_run

A passed check requires exit code zero; a failed check requires a non-zero exit code. Skipped, unavailable, and not-run checks have no exit code. Unavailable and not-run checks have no duration.

QAResult.overall_status is derived, never trusted from the model:
- failed if a required check failed;
- incomplete if there are no required checks or any required check did not pass;
- passed only when at least one required check exists and all required checks passed.

Optional non-passing checks remain visible through warning_check_ids; they cannot silently rewrite individual check outcomes.

## Safety and integration boundary

These classes validate records only. They do not run command, read evidence files, approve a submission, or treat a model response as trusted. The next integration step is to connect deterministic sandbox exit codes to QACheck, then pass the proposal, issue, plan, and QA evidence to a separate reviewer. Any reviewer error or inconclusive decision must keep the proposal blocked. External claims, messages, submissions, merges, and payments remain behind explicit user approval.
