# Opportunity portfolio and workload controls

The `ai-worker scan` command produces a shortlist, not an automatic commitment.

- `--max-opportunities` caps the number of recommendations in one report (default 5).
- `--max-active` caps the number of tasks already marked claimed, in progress, submitted, or accepted in the local outcome ledger (default 5).
- The remaining recommendation capacity is `max(0, max_active - active_count)`.
- Source diversification limits the shortlist to two opportunities per source by default.
- Duplicate IDs and non-finite scores are ignored.
- All existing eligibility, escrow, payout-evidence, HTTPS, acceptance-criteria, and risk gates run before portfolio selection.

The ledger only counts statuses explicitly recorded by the operator. It cannot detect commitments made outside AI-Worker, and it does not estimate task duration or probability of acceptance. Advertised rewards are not expected earnings. No task is claimed, submitted, or paid automatically.
