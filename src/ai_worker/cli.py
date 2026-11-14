import argparse
from ai_worker.report import write_report
from ai_worker.scoring import evaluate
from ai_worker.sources.jobbi import FeedError, fetch_gigs
from ai_worker.storage import connect, upsert_gigs

def main() -> int:
    parser = argparse.ArgumentParser(prog="ai-worker")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("--limit", type=int, default=100)
    scan.add_argument("--min-reward", type=float, default=5.0)
    scan.add_argument("--db", default="data/ai_worker.sqlite3")
    scan.add_argument("--output", default="reports/latest.md")
    args = parser.parse_args()
    if args.command == "scan":
        try:
            gigs = fetch_gigs(args.limit)
        except FeedError as exc:
            print(f"ERROR: {exc}")
            return 2
        db = connect(args.db)
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
        db.close()
        print(f"Fetched: {len(gigs)} | Qualified: {len(ranked)} | Filtered: {rejected}")
        print(f"Report: {report}")
        return 0
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
