"""Publish reproducible calendar-month summaries from the current revision view."""

import argparse
import calendar
import json
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from catalog import events


def summarize(rows, year, month):
    _, days = calendar.monthrange(year, month)
    daily_counts = Counter()
    relevant = []
    for row in rows:
        day = datetime.fromtimestamp(row["occurred_ms"] / 1000, UTC)
        if (day.year, day.month) == (year, month):
            relevant.append(row)
            daily_counts[day.day] += 1
    ranked = sorted(
        (row for row in relevant if row["magnitude"] is not None),
        key=lambda row: (-row["magnitude"], row["occurred_ms"], row["event_id"]),
    )
    return {
        "month_utc": f"{year:04}-{month:02}",
        "event_count": len(relevant),
        "daily_counts": [daily_counts[day] for day in range(1, days + 1)],
        "largest_events": ranked[:5],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("month", help="YYYY-MM")
    args = parser.parse_args()
    try:
        month = datetime.strptime(args.month, "%Y-%m")
        rows = events(args.database)
    except (ValueError, OSError, sqlite3.Error) as error:
        # A missing or unreadable database is a usage error, not a traceback.
        parser.error(str(error))
    print(json.dumps(summarize(rows, month.year, month.month), indent=2))
