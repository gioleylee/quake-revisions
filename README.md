# Quake Revisions

An append-only SQLite pipeline for earthquake catalog snapshots. It ingests USGS GeoJSON, preserves revised event records, and generates calendar-month reports. The included January 2024 snapshot imports **623 events** and can be replayed offline.

## Run

Use Python 3.11+ with SQLite 3.24+.

```sh
python catalog.py --db quakes.sqlite import data/jan-2024.geojson
python summarize.py quakes.sqlite 2024-01
python catalog.py --db quakes.sqlite history us6000m0xl
python catalog.py --db quakes.sqlite events --as-of 1735689600000
python -m unittest -v
```

The [January report](january-report.json) includes daily UTC counts and the five largest events by the magnitude reported by USGS. The largest in this snapshot was the M7.5 Noto Peninsula event.

## Pipeline behavior

- An import stores the SHA-256 of the raw file. Replaying the same bytes inserts zero rows.
- An event revision is keyed by its USGS event ID and source update timestamp. Overlapping files can supply the same normalized revision. If they disagree on stored fields for the same key, the transaction rolls back.
- Current views choose the most recently updated imported version of each ID. Late-arriving older revisions remain in history. The optional as-of cutoff refers to the USGS update time and can only reconstruct versions present in the imported files.
- The importer stores eight normalized fields and treats source IDs as stable keys. It does not resolve event merges or infer deletions from missing IDs. The bundled historical download contains the latest versions returned by that query when it was fetched, so revision behavior is exercised by synthetic multi-import tests.

## Data provenance

The [USGS Earthquake Catalog query](https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime=2024-01-01&endtime=2024-02-01&minmagnitude=4.5&eventtype=earthquake&orderby=time-asc) selected earthquakes from January 2024 at magnitude 4.5 and above. The frozen file has SHA-256 `dc15351764f812f8c7b2e35213aaee93b1913bbba379de4519f4fbba83194608`. Rerunning the query may return revised records. See the [USGS Event API documentation](https://earthquake.usgs.gov/fdsnws/event/1/swagger.json).
