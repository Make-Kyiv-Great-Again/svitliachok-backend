# Path Finder Backend

The goal of this project is to build a core logic of Svitliachok

# Tech Stack
- main: Python FastAPI
- database: Postgres
- path finding: pgRouting

# How To Set Up Dev Postgres

launch Postgres with needed extensions
``` bash
docker-compose up -d db
```

run EVERYTHING in the data directory
``` bash
mkdir data && cd data
```

download Ukraine map data
``` bash
wget https://download.geofabrik.de/europe/ukraine-latest.osm.pbf
```

optimize the map and extract only the data about Kyiv and Zhytomyr with osmium
``` bash
docker run --rm -v $(pwd):/data debian:bookworm-slim bash -c "\
  apt-get update && apt-get install -y osmium-tool && \
  osmium extract -b 30.2,50.3,30.8,50.6 /data/ukraine-latest.osm.pbf -o /data/kyiv_only.pbf --overwrite && \
  osmium extract -b 28.5,50.1,28.8,50.4 /data/ukraine-latest.osm.pbf -o /data/zhytomyr_only.pbf --overwrite && \
  osmium merge /data/kyiv_only.pbf /data/zhytomyr_only.pbf -o /data/svitliachok_cities.pbf --overwrite"
```

install osm2po
``` bash
wget https://osm2po.de/releases/osm2po-5.5.8.zip
unzip osm2po-5.5.8.zip -d osm2po
rm osm2po-5.5.8.zip
```

configure osm2po for pedestrian routing (create an `osm2po.config` in the `data` directory)
```bash
# This creates a pedestrian-focused config that ignores car-only roads and uses distance for cost
cat << 'EOF' > osm2po.config
wtr.flagList = car, bike, foot, rail, ferry, poly
wtr.finalMask = foot

wtr.tag.highway.pedestrian = 1, 62, 5, foot
wtr.tag.highway.track =      1, 71, 5, foot
wtr.tag.highway.footway =    1, 91, 5, foot
wtr.tag.highway.steps =      1, 92, 5, foot
wtr.tag.highway.path =       1, 72, 5, foot

wtr.tag.highway.residential =   1, 41, 5, foot
wtr.tag.highway.living_street = 1, 63, 5, foot
wtr.tag.highway.service =       1, 51, 5, foot
wtr.tag.highway.primary =       1, 15, 5, foot
wtr.tag.highway.secondary =     1, 21, 5, foot
wtr.tag.highway.tertiary =      1, 31, 5, foot
wtr.tag.highway.unclassified =  1, 43, 5, foot
EOF
```

generate the pgRouting topology with osm2po (./data/svitliachok/svitliachok_2po_4pgr.sql)
``` bash
docker run --rm -v $(pwd):/data -w /data eclipse-temurin:11-jre \
  java -Xmx2g -jar osm2po/osm2po-core-5.5.8-signed.jar \
  config=osm2po.config \
  prefix=svitliachok \
  postp.0.class=de.cm.osm2po.plugins.postp.PgRoutingWriter \
  svitliachok_cities.pbf
```

finally exit data dir
``` bash
cd ..
```

load the data into Postgres (the SQL file automatically drops the old table before loading)
``` bash
docker exec -i svitliachok_db_dev psql -U admin -d db < data/svitliachok/svitliachok_2po_4pgr.sql
```

add the dynamic cost column (our FastAPI app does this automatically on startup, but you can also do it manually)
``` sql
ALTER TABLE svitliachok_2po_4pgr 
    ADD COLUMN dynamic_cost FLOAT, 
    ADD COLUMN is_blackout BOOLEAN DEFAULT false;
UPDATE svitliachok_2po_4pgr SET dynamic_cost = cost, is_blackout = false;
CREATE INDEX idx_svitliachok_dynamic_cost ON svitliachok_2po_4pgr (dynamic_cost);
CREATE INDEX idx_svitliachok_is_blackout ON svitliachok_2po_4pgr (is_blackout);
```

verify inside psql
``` sql
WITH start_node AS (
    SELECT source FROM svitliachok_2po_4pgr
    ORDER BY geom_way <-> ST_SetSRID(ST_MakePoint(30.5222, 50.4475), 4326) LIMIT 1
),
end_node AS (
    SELECT target FROM svitliachok_2po_4pgr
    ORDER BY geom_way <-> ST_SetSRID(ST_MakePoint(30.5133, 50.4488), 4326) LIMIT 1
)
SELECT seq, node, cost FROM pgr_dijkstra(
    'SELECT id, source, target, cost, reverse_cost FROM svitliachok_2po_4pgr',
    (SELECT source FROM start_node), (SELECT target FROM end_node), false
);
```