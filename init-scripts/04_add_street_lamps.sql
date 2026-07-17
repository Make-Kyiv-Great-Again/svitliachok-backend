-- Migration: street lamps from OpenStreetMap
-- Apply with:
--   docker exec -i svitliachok_db_dev psql -U admin -d db < init-scripts/04_add_street_lamps.sql

CREATE TABLE IF NOT EXISTS street_lamps (
    id         BIGINT PRIMARY KEY,             -- OSM node id
    geom       GEOMETRY(Point, 4326) NOT NULL,
    lamp_type  VARCHAR(50),                    -- lamp:type tag (LED, sodium, …) — may be null
    ref        VARCHAR(50),                    -- OSM ref tag — may be null
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_street_lamps_geom ON street_lamps USING GIST (geom);
