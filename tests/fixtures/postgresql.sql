-- Test data of the PostgreSQL container, run as the superuser with psql.
-- probe_app: a plain role, owner of its tables, like the account of a DSS connection.
-- dbmon:     pg_monitor only, like a monitoring admin connection.
-- Their passwords are test values of this local container only.
CREATE ROLE probe_app LOGIN PASSWORD 'probe_app';
CREATE ROLE dbmon LOGIN PASSWORD 'dbmon' IN ROLE pg_monitor;
CREATE TABLESPACE sales_dsswork_index LOCATION '/var/lib/postgresql/ts_index';
GRANT CREATE ON TABLESPACE sales_dsswork_index TO probe_app;
CREATE DATABASE appdb OWNER probe_app;
CREATE DATABASE otherdb OWNER probe_app;
\c appdb probe_app
CREATE SCHEMA sales_dsswork;
CREATE SCHEMA fin_dssout;
CREATE SCHEMA appx;
-- large text values go to TOAST; an index in another tablespace; a serial column
CREATE TABLE sales_dsswork."SALES_orders" (id serial PRIMARY KEY, payload text, amount numeric, doc jsonb);
INSERT INTO sales_dsswork."SALES_orders" (payload, amount)
SELECT (SELECT string_agg(md5(g::text || i::text), '') FROM generate_series(1, 150) i), g
FROM   generate_series(1, 3000) g;
CREATE INDEX "SALES_orders_amount" ON sales_dsswork."SALES_orders"(amount) TABLESPACE sales_dsswork_index;
-- same name in lower case: exact names win over case-insensitive matches
CREATE TABLE sales_dsswork.sales_orders (id int);
-- identity column, no out-of-line column
CREATE TABLE appx.events (id bigint GENERATED ALWAYS AS IDENTITY, at timestamp, n int);
INSERT INTO appx.events (at, n) SELECT now(), g FROM generate_series(1, 2000) g;
-- partitioned table, two levels, with a partitioned index
CREATE TABLE fin_dssout.ledger (id int, d date, region text, amount numeric) PARTITION BY RANGE (d);
CREATE TABLE fin_dssout.ledger_2025 PARTITION OF fin_dssout.ledger FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE fin_dssout.ledger_2026 PARTITION OF fin_dssout.ledger FOR VALUES FROM ('2026-01-01') TO ('2027-01-01')
  PARTITION BY LIST (region);
CREATE TABLE fin_dssout.ledger_2026_eu PARTITION OF fin_dssout.ledger_2026 FOR VALUES IN ('EU');
CREATE TABLE fin_dssout.ledger_2026_us PARTITION OF fin_dssout.ledger_2026 FOR VALUES IN ('US');
CREATE INDEX ledger_d ON fin_dssout.ledger(d);
INSERT INTO fin_dssout.ledger
SELECT g, DATE '2025-06-01' + (g % 400), CASE WHEN g % 2 = 0 THEN 'EU' ELSE 'US' END, g
FROM   generate_series(1, 20000) g;
-- partitioned table without any partition yet
CREATE TABLE fin_dssout.empty_parent (id int, d date) PARTITION BY RANGE (d);
CREATE INDEX empty_parent_d ON fin_dssout.empty_parent(d);
CREATE MATERIALIZED VIEW appx.mv_totals AS SELECT n % 10 AS k, count(*) AS c FROM appx.events GROUP BY 1;
CREATE VIEW appx.v_events AS SELECT * FROM appx.events;
CREATE UNLOGGED TABLE appx.scratch (a int);
INSERT INTO appx.scratch SELECT generate_series(1, 100);
-- no autovacuum on the tables changed below: it would analyze them again and reset the
-- changes the tests count
ALTER TABLE appx.events SET (autovacuum_enabled = false);
ALTER TABLE fin_dssout.ledger_2025 SET (autovacuum_enabled = false);
ALTER TABLE fin_dssout.ledger_2026_eu SET (autovacuum_enabled = false);
ALTER TABLE fin_dssout.ledger_2026_us SET (autovacuum_enabled = false);
-- flush the counts of the inserts above before ANALYZE resets them, or they are added after
-- it and counted as changes since the analysis
SELECT pg_stat_force_next_flush();
ANALYZE sales_dsswork."SALES_orders";
ANALYZE appx.events;
ANALYZE fin_dssout.ledger;
-- changes after the statistics
UPDATE appx.events SET n = n + 1 WHERE id <= 300;
DELETE FROM fin_dssout.ledger WHERE id <= 500;
SELECT pg_stat_force_next_flush();
-- the search_path of the account finds tables of sales_dsswork without schema
ALTER ROLE probe_app IN DATABASE appdb SET search_path = sales_dsswork, public;
\c otherdb probe_app
CREATE SCHEMA sales_dsswork;
CREATE TABLE sales_dsswork."SALES_orders" (id int);
INSERT INTO sales_dsswork."SALES_orders" SELECT generate_series(1, 100);
