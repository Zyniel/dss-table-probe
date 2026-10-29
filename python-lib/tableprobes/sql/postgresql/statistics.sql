-- =============================================================================
-- statistics.sql (PostgreSQL)
-- Optimizer statistics and activity of one table. One row. A partitioned table sums its
-- leaf partitions (the latest analysis and vacuum among them).
-- Same columns as the Oracle file, in the same order: a column that does not exist on
-- PostgreSQL is NULL, and the probe returns no metric for it.
-- -----------------------------------------------------------------------------
-- row_estimate     reltuples: NULL before the first ANALYZE or VACUUM
-- avg_row_bytes    sum of the average width of the columns (pg_stats)
-- dml_since_analyzed  rows inserted, updated or deleted since the last analysis
--                     (n_mod_since_analyze)
-- Dates are UTC, ISO 8601: what DSS reads as a date metric. days_since_*: decimal days.
-- Activity counters (live/dead rows, scans) restart with pg_stat_reset() or a crash.
-- Placeholders: {{table_oid}}
-- =============================================================================
WITH
-- the relations holding the rows: the table itself, or the leaf partitions of a
-- partitioned table (pg_partition_tree gives no row for a table that is not partitioned)
leaves AS (
  SELECT l.reltuples, s.n_mod_since_analyze, s.n_live_tup, s.n_dead_tup, s.seq_scan, s.idx_scan,
         GREATEST(s.last_analyze, s.last_autoanalyze)                   AS analyzed,
         GREATEST(s.last_vacuum, s.last_autovacuum)                     AS vacuumed
  FROM   pg_class l
         LEFT JOIN pg_stat_all_tables s ON s.relid = l.oid
  WHERE  (l.oid = {{table_oid}} AND l.relkind <> 'p')
  OR     l.oid IN (SELECT p.relid
                   FROM   pg_partition_tree(CAST({{table_oid}} AS oid)) p
                   WHERE  p.isleaf)
),
summed AS (
  SELECT CASE WHEN MAX(lv.reltuples) >= 0
              THEN SUM(GREATEST(lv.reltuples, 0))
         END                                                            AS row_estimate,
         MAX(lv.analyzed)                                               AS analyzed,
         SUM(lv.n_mod_since_analyze)                                    AS dml_since_analyzed,
         SUM(lv.n_live_tup)                                             AS live_rows,
         SUM(lv.n_dead_tup)                                             AS dead_rows,
         MAX(lv.vacuumed)                                               AS vacuumed,
         SUM(lv.seq_scan)                                               AS seq_scans,
         SUM(lv.idx_scan)                                               AS index_scans
  FROM   leaves lv
)
SELECT CASE
         WHEN c.relkind = 'p'        THEN 'PARTITIONED'
         WHEN c.relkind = 'm'        THEN 'MATERIALIZED VIEW'
         WHEN c.relkind = 'f'        THEN 'FOREIGN'
         WHEN c.relpersistence = 't' THEN 'TEMPORARY'
         WHEN c.relpersistence = 'u' THEN 'UNLOGGED'
         ELSE 'HEAP'
       END                                                              AS table_kind,
       ROUND(CAST(s.row_estimate AS numeric))                           AS row_estimate,
       (SELECT SUM(st.avg_width)
        FROM   pg_stats st
        WHERE  st.schemaname = n.nspname
        AND    st.tablename  = c.relname
        AND    st.inherited  = (c.relkind = 'p'))                       AS avg_row_bytes,
       to_char(s.analyzed AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS".000Z"')
                                                                        AS last_analyzed,
       ROUND(CAST(EXTRACT(EPOCH FROM now() - s.analyzed) / 86400 AS numeric), 3)
                                                                        AS days_since_analyzed,
       s.dml_since_analyzed,
       CAST(NULL AS bigint)                                             AS inserts_since_analyzed,
       CAST(NULL AS bigint)                                             AS updates_since_analyzed,
       CAST(NULL AS bigint)                                             AS deletes_since_analyzed,
       CAST(NULL AS text)                                               AS truncated_since_analyzed,
       CAST(NULL AS text)                                               AS last_dml,
       CAST(NULL AS text)                                               AS created,
       CAST(NULL AS text)                                               AS last_ddl,
       CAST(NULL AS numeric)                                            AS days_since_ddl,
       CASE WHEN c.relpersistence = 'u' THEN 'NO' ELSE 'YES' END        AS logging,
       CAST(NULL AS text)                                               AS parallel_degree,
       s.live_rows,
       s.dead_rows,
       to_char(s.vacuumed AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS".000Z"')
                                                                        AS last_vacuum,
       ROUND(CAST(EXTRACT(EPOCH FROM now() - s.vacuumed) / 86400 AS numeric), 3)
                                                                        AS days_since_vacuum,
       s.seq_scans,
       s.index_scans
FROM   pg_class c
       JOIN pg_namespace n ON n.oid = c.relnamespace
       CROSS JOIN summed s
WHERE  c.oid = {{table_oid}};
