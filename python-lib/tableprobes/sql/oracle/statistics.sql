-- =============================================================================
-- statistics.sql (Oracle)
-- Optimizer statistics, lifecycle and changes of one table. One row.
-- Same columns as the PostgreSQL file, in the same order: a column that does not exist
-- on Oracle is NULL, and the probe returns no metric for it.
-- Every dictionary view is filtered on the owner and name of the table, as literals.
-- -----------------------------------------------------------------------------
-- row_estimate, avg_row_bytes, last_analyzed  from DBA_TABLES (NUM_ROWS, AVG_ROW_LEN,
--                  LAST_ANALYZED): NULL before the first gathering. DBA_TAB_STATISTICS is
--                  not read: on Exadata it holds a second row per table with real-time
--                  statistics
-- dml_since_analyzed and its split by kind, truncated_since_analyzed
--                  DBA_TAB_MODIFICATIONS, table level. On 21c and later it adds the
--                  changes still in memory on every instance of a RAC (GV$DML_STATS):
--                  committed rows show at once. Older versions may need
--                  DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO (ANALYZE ANY). Reset by each
--                  statistics gathering
-- created, last_ddl  DBA_OBJECTS
-- Dates are UTC, ISO 8601: what DSS reads as a date metric. Dictionary dates are in the
-- time zone of the server's clock (SYSDATE), converted with its current offset.
-- days_since_*: decimal days.
-- Placeholders: {{owner}}, {{table}} as literals; dictionary views {{tables}},
-- {{objects}}, {{tab_modifications}}, {{external_tables}}
-- =============================================================================
WITH
clock AS (
  SELECT TO_CHAR(SYSTIMESTAMP, 'TZH:TZM')                               AS server_offset
  FROM   dual
),
table_object AS (
  SELECT o.created, o.last_ddl_time
  FROM   {{objects}} o
  WHERE  o.owner          = {{owner}}
  AND    o.object_name    = {{table}}
  AND    o.object_type    = 'TABLE'
  AND    o.subobject_name IS NULL
),
changes AS (
  SELECT m.inserts, m.updates, m.deletes, m.truncated
  FROM   {{tab_modifications}} m
  WHERE  m.table_owner       = {{owner}}
  AND    m.table_name        = {{table}}
  AND    m.partition_name    IS NULL
  AND    m.subpartition_name IS NULL
),
kinds AS (
  SELECT (SELECT COUNT(*)
          FROM   {{objects}} mv
          WHERE  mv.owner       = {{owner}}
          AND    mv.object_name = {{table}}
          AND    mv.object_type = 'MATERIALIZED VIEW')                  AS is_mview,
         (SELECT COUNT(*)
          FROM   {{external_tables}} x
          WHERE  x.owner      = {{owner}}
          AND    x.table_name = {{table}})                              AS is_external
  FROM   dual
)
SELECT CASE
         WHEN t.temporary = 'Y'          THEN 'TEMPORARY'
         WHEN k.is_external > 0          THEN 'EXTERNAL'
         WHEN k.is_mview > 0             THEN 'MATERIALIZED VIEW'
         WHEN t.iot_type = 'IOT'         THEN 'INDEX ORGANIZED'
         WHEN t.cluster_name IS NOT NULL THEN 'CLUSTERED'
         WHEN t.partitioned = 'YES'      THEN 'PARTITIONED'
         ELSE 'HEAP'
       END                                                              AS table_kind,
       t.num_rows                                                       AS row_estimate,
       t.avg_row_len                                                    AS avg_row_bytes,
       TO_CHAR(SYS_EXTRACT_UTC(FROM_TZ(CAST(t.last_analyzed AS TIMESTAMP), c.server_offset)),
               'YYYY-MM-DD"T"HH24:MI:SS".000Z"')                       AS last_analyzed,
       ROUND(SYSDATE - t.last_analyzed, 3)                              AS days_since_analyzed,
       NVL(m.inserts, 0) + NVL(m.updates, 0) + NVL(m.deletes, 0)        AS dml_since_analyzed,
       NVL(m.inserts, 0)                                                AS inserts_since_analyzed,
       NVL(m.updates, 0)                                                AS updates_since_analyzed,
       NVL(m.deletes, 0)                                                AS deletes_since_analyzed,
       NVL(m.truncated, 'NO')                                           AS truncated_since_analyzed,
       TO_CHAR(SYS_EXTRACT_UTC(FROM_TZ(CAST(o.created AS TIMESTAMP), c.server_offset)),
               'YYYY-MM-DD"T"HH24:MI:SS".000Z"')                       AS created,
       TO_CHAR(SYS_EXTRACT_UTC(FROM_TZ(CAST(o.last_ddl_time AS TIMESTAMP), c.server_offset)),
               'YYYY-MM-DD"T"HH24:MI:SS".000Z"')                       AS last_ddl,
       ROUND(SYSDATE - o.last_ddl_time, 3)                              AS days_since_ddl,
       t.logging,
       TRIM(t.degree)                                                   AS parallel_degree,
       CAST(NULL AS NUMBER)                                             AS live_rows,
       CAST(NULL AS NUMBER)                                             AS dead_rows,
       CAST(NULL AS VARCHAR2(30))                                       AS last_vacuum,
       CAST(NULL AS NUMBER)                                             AS days_since_vacuum,
       CAST(NULL AS NUMBER)                                             AS seq_scans,
       CAST(NULL AS NUMBER)                                             AS index_scans
FROM   {{tables}} t
       CROSS JOIN clock c
       CROSS JOIN kinds k
       LEFT JOIN table_object o ON 1 = 1
       LEFT JOIN changes m      ON 1 = 1
WHERE  t.owner      = {{owner}}
AND    t.table_name = {{table}};
