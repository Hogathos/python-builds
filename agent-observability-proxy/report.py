"""M1 report: headline metrics from attempts.db via GROUP BY.

Same headline shape as v0.3 (attempts, success rate, retries, average
latency, tokens, cost), grouped by destination host / endpoint / method.

Run:  python report.py --db attempts.db
"""
from __future__ import annotations

import argparse
import sqlite3

import db as db_module


def main():
    parser = argparse.ArgumentParser(description="Proxy attempts report")
    parser.add_argument("--db", default="attempts.db")
    args = parser.parse_args()

    conn = db_module.init_db(args.db)
    totals = db_module.fetch_totals(conn)
    attempts = totals["attempts"] or 0
    successes = totals["successes"] or 0
    rate = (100.0 * successes / attempts) if attempts else 0.0
    print(f"attempts={attempts} traces={totals['traces'] or 0} "
          f"successes={successes} success_rate={rate:.1f}% "
          f"retries={totals['retries'] or 0} "
          f"avg_latency_seconds={totals['avg_latency_seconds']} "
          f"bytes_in={totals['bytes_in'] or 0} "
          f"bytes_out={totals['bytes_out'] or 0} "
          f"input_tokens={totals['input_tokens'] or 0} "
          f"cost_dollars={totals['cost_dollars'] or 0}")
    print()
    print(f"{'dest_host':<22} {'method':<7} {'endpoint':<28} "
          f"{'n':>4} {'ok':>4} {'retry':>5} {'avg_s':>8} {'b_in':>7} {'b_out':>7}")
    for row in db_module.fetch_report(conn):
        print(f"{row['dest_host']:<22} {row['method']:<7} "
              f"{row['endpoint']:<28} {row['attempts']:>4} "
              f"{row['successes']:>4} {row['retries']:>5} "
              f"{row['avg_latency_seconds']:>8} "
              f"{row['bytes_in']:>7} {row['bytes_out']:>7}")
    conn.close()


if __name__ == "__main__":
    main()
