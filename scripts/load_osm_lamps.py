#!/usr/bin/env python3
"""
Load OSM street lamp nodes from data/kyiv_lamps.geojson into the street_lamps table.

Run AFTER extracting lamps from the .pbf (see README):
    docker exec svitliachok_api_dev python scripts/load_osm_lamps.py

The GeoJSON is produced by:
    osmium tags-filter data/kyiv_only.pbf n/highway=street_lamp -o data/kyiv_lamps.osm.pbf
    osmium export data/kyiv_lamps.osm.pbf -f geojson --geometry-types=point -o data/kyiv_lamps.geojson
"""

import asyncio
import json
import os
import sys

import asyncpg

# Inside the Docker container the env override uses db:5432; locally use localhost.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://admin:pass@db:5432/db",
).replace("postgresql+asyncpg://", "postgresql://")

GEOJSON_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "kyiv_lamps.geojson")


def parse_osm_id(raw: str) -> int | None:
    """Parse osmium export's '@id' field, e.g. 'node/123456' → 123456."""
    try:
        return int(raw.split("/")[-1])
    except (ValueError, AttributeError):
        return None


async def main() -> None:
    geojson_path = os.path.abspath(GEOJSON_PATH)
    if not os.path.exists(geojson_path):
        print(f"ERROR: {geojson_path} not found.")
        print("Run the osmium extraction commands first (see README).")
        sys.exit(1)

    print(f"Reading {geojson_path} …")
    with open(geojson_path, encoding="utf-8") as fh:
        data = json.load(fh)

    features = data.get("features", [])
    print(f"Parsed {len(features):,} features")

    ids, lons, lats, lamp_types, refs = [], [], [], [], []
    skipped = 0
    for idx, feat in enumerate(features, start=1):
        try:
            coords = feat["geometry"]["coordinates"]
            props  = feat.get("properties") or {}
            lons.append(float(coords[0]))
            lats.append(float(coords[1]))
            ids.append(idx)                                   # surrogate sequential id
            # Prefer lamp:type; fall back to lit= tag; None if unknown
            lamp_types.append(
                props.get("lamp:type")
                or props.get("lamp_colour")
                or props.get("lit")   # "yes" / "no" — still useful metadata
                or None
            )
            refs.append(props.get("ref") or None)
        except Exception:
            skipped += 1


    if skipped:
        print(f"Skipped {skipped:,} malformed features")

    print(f"Connecting to database …")
    conn = await asyncpg.connect(DATABASE_URL)

    print(f"Inserting {len(ids):,} lamps (ON CONFLICT DO NOTHING) …")
    await conn.execute(
        """
        INSERT INTO street_lamps (id, geom, lamp_type, ref)
        SELECT
            unnest($1::bigint[]),
            ST_SetSRID(ST_MakePoint(unnest($2::float8[]), unnest($3::float8[])), 4326),
            unnest($4::text[]),
            unnest($5::text[])
        ON CONFLICT (id) DO NOTHING
        """,
        ids, lons, lats, lamp_types, refs,
    )

    count = await conn.fetchval("SELECT COUNT(*) FROM street_lamps")
    print(f"Done. street_lamps now has {count:,} rows.")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
