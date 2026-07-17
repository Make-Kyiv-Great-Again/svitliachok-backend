-- Migration: add wifi and phone-charging info to businesses
-- Safe to run multiple times (IF NOT EXISTS equivalent via ALTER TABLE ADD COLUMN IF NOT EXISTS).
-- Apply to the running container:
--   docker exec -i <db_container> psql -U admin -d db < init-scripts/03_add_wifi_charging.sql

ALTER TABLE businesses ADD COLUMN IF NOT EXISTS has_wifi         BOOLEAN DEFAULT false NOT NULL;
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS can_charge_phone BOOLEAN DEFAULT false NOT NULL;
