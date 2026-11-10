"""Import USGS GeoJSON and query an append-only earthquake revision ledger."""

import argparse
import hashlib
import json
import math
import sqlite3
from contextlib import closing
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS revisions (
    event_id TEXT NOT NULL,
    updated_ms INTEGER NOT NULL,
    occurred_ms INTEGER NOT NULL,
    magnitude REAL,
    place TEXT,
    longitude REAL NOT NULL,
    latitude REAL NOT NULL,
    depth_km REAL NOT NULL,
    PRIMARY KEY (event_id, updated_ms)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS imports (
    sha256 TEXT PRIMARY KEY,
    features INTEGER NOT NULL,
    inserted INTEGER NOT NULL
) WITHOUT ROWID;
"""

LATEST = """
WITH latest AS (
    SELECT event_id, MAX(updated_ms) AS updated_ms
    FROM revisions WHERE (? IS NULL OR updated_ms <= ?)
    GROUP BY event_id
)
"""


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def normalize(feature):
    try:
        event_id = feature["id"]
        properties = feature["properties"]
        occurred = properties["time"]
        updated = properties["updated"]
        magnitude = properties["mag"]
        place = properties["place"]
        geometry = feature["geometry"]
        if feature["type"] != "Feature" or geometry["type"] != "Point":
            raise ValueError("expected a Point feature")
        longitude, latitude, depth = geometry["coordinates"]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("invalid earthquake feature structure") from error
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("event id must be a nonempty string")
    if any(type(value) is not int or not -(2**63) <= value < 2**63 for value in (occurred, updated)):
        raise ValueError(f"{event_id}: expected integer UTC timestamps in milliseconds")
    if not all(map(number, (longitude, latitude, depth))) or not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
        raise ValueError(f"{event_id}: invalid longitude, latitude, or depth")
    if (magnitude is not None and not number(magnitude)) or (place is not None and not isinstance(place, str)):
        raise ValueError(f"{event_id}: invalid magnitude or place")
    return event_id, updated, occurred, magnitude, place, longitude, latitude, depth


def ingest(database, raw):
    collection = json.loads(raw)
    if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection":
        raise ValueError("expected a GeoJSON FeatureCollection")
    features = collection.get("features")
    if not isinstance(features, list):
        raise ValueError("expected a list of features")
    digest = hashlib.sha256(raw).hexdigest()
    with closing(sqlite3.connect(database)) as db:
        db.executescript(SCHEMA)
        with db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM imports WHERE sha256 = ?", (digest,)).fetchone():
                return {"sha256": digest, "features": len(features), "inserted": 0, "replay": True}
            inserted = 0
            for feature in features:
                row = normalize(feature)
                result = db.execute(
                    "INSERT INTO revisions VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING", row
                )
                if result.rowcount:
                    inserted += 1
                else:
                    stored = db.execute(
                        "SELECT * FROM revisions WHERE event_id = ? AND updated_ms = ?", row[:2]
                    ).fetchone()
                    if stored != row:
                        raise ValueError(f"{row[0]}: conflicting content for revision {row[1]}")
            db.execute("INSERT INTO imports VALUES (?, ?, ?)", (digest, len(features), inserted))
    return {"sha256": digest, "features": len(features), "inserted": inserted, "replay": False}


def read_rows(database, sql, params=()):
    uri = Path(database).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute(sql, params)]


def events(database, as_of=None):
    return read_rows(database, LATEST + """
        SELECT r.* FROM revisions AS r JOIN latest USING (event_id, updated_ms)
        ORDER BY occurred_ms, event_id
    """, (as_of, as_of))


def history(database, event_id):
    return read_rows(database, "SELECT * FROM revisions WHERE event_id = ? ORDER BY updated_ms", (event_id,))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("import").add_argument("geojson", type=Path)
    commands.add_parser("events").add_argument("--as-of", type=int, metavar="UNIX_MS")
    commands.add_parser("history").add_argument("event_id")
    args = parser.parse_args()
    try:
        if args.command == "import":
            result = ingest(args.db, args.geojson.read_bytes())
        elif args.command == "events":
            result = events(args.db, args.as_of)
        else:
            result = history(args.db, args.event_id)
    except (ValueError, OSError, OverflowError, sqlite3.Error) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
