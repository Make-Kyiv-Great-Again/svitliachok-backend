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

generate the pgRouting topology with osm2po (./data/svitliachok/svitliachok_2po_4pgr.sql)
``` bash
docker run --rm -v $(pwd):/data -w /data eclipse-temurin:11-jre \
  java -Xmx2g -jar osm2po/osm2po-core-5.5.8-signed.jar \
  prefix=svitliachok \
  postp.0.class=de.cm.osm2po.plugins.postp.PgRoutingWriter \
  svitliachok_cities.pbf
```

finally exit data dir
``` bash
cd ..
```

load the data into Postgres
``` bash
docker exec -i svitliachok_db_dev psql -U admin -d db < data/svitliachok/svitliachok_2po_4pgr.sql
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