import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from catalog import events, history, ingest
from summarize import summarize


def feature(event_id, updated, magnitude):
    return {"id": event_id, "type": "Feature", "properties": {
        "time": 5, "updated": updated, "mag": magnitude, "place": None,
    }, "geometry": {"type": "Point", "coordinates": [121, 23, 10]}}


def collection(*features):
    return json.dumps({"type": "FeatureCollection", "features": features}).encode()


class CatalogTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db = Path(directory.name) / "test.sqlite"

    def test_late_old_revision_preserves_latest_and_history(self):
        newer = collection(feature("a", 30, 5.6))
        self.assertEqual(ingest(self.db, newer)["inserted"], 1)
        self.assertTrue(ingest(self.db, newer)["replay"])
        self.assertEqual(ingest(self.db, collection(feature("a", 20, 5.1)))["inserted"], 1)
        self.assertEqual(events(self.db)[0]["magnitude"], 5.6)
        self.assertEqual(events(self.db, as_of=25)[0]["magnitude"], 5.1)
        self.assertEqual([row["updated_ms"] for row in history(self.db, "a")], [20, 30])

    def test_conflict_rolls_back_entire_snapshot(self):
        ingest(self.db, collection(feature("a", 20, 5.1)))
        with self.assertRaisesRegex(ValueError, "conflicting"):
            ingest(self.db, collection(feature("b", 21, 4.6), feature("a", 20, 5.2)))
        self.assertEqual([row["event_id"] for row in events(self.db)], ["a"])

    def test_calendar_report_includes_zero_days_and_skips_unknown_magnitudes(self):
        ingest(self.db, collection(feature("a", 20, None), feature("b", 21, 5.5)))
        report = summarize(events(self.db), 1970, 1)
        self.assertEqual(report["event_count"], 2)
        self.assertEqual(report["daily_counts"], [2] + [0] * 30)
        self.assertEqual([row["event_id"] for row in report["largest_events"]], ["b"])
