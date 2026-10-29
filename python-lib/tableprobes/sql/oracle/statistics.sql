-- =============================================================================
-- statistics.sql (Oracle)
-- Optimizer statistics, lifecycle and changes of one table. One row.
-- Same columns as the PostgreSQL file, in the same order: a column that does not exist
-- on Oracle is NULL, and the probe returns no metric for it.
-- -----------------------------------------------------------------------------
-- row_estimate, avg_row_bytes, last_analyzed  from the optimizer statistics (NUM_ROWS,
--                  AVG_ROW_LEN, LAST_ANALYZED): NULL before the first gathering
-- dml_since_analyzed and its split by kind, truncated_since_analyzed, last_dml
--                  DBA_TAB_MODIFICATIONS: flushed from memory every few minutes, and
--                  reset by each statistics gathering
-- created, last_ddl  DBA_OBJECTS
-- Dates are UTC, ISO 8601: what DSS reads as a date metric. Dictionary dates are in the
-- time zone of the server's clock (SYSDATE), converted with its current offset.
-- days_since_*: decimal days.
-- Placeholders: {{owner}}, {{table}} as literals; dictionary views {{tables}},
-- {{objects}}, {{tab_modifications}}, {{external_tables}}
-- =============================================================================
WITH
clock AS (
  SELECT TO_CHAR(SYSTIMESTAMP, 'TZH:TZM') AS server_offset
  FROM   dual
),
-- ISO 8601 UTC text of the dictionary dates
dates AS (
  SELECT t.owner, t.table_name,
         TO_CHAR(SYS_EXTRACT_UTC(FROM_TZ(CAST(t.last_analyzed AS TIMESTAMP), k.server_offset)),
                 'YYYY-MM-DD"T"HH24:MI:SS".000Z"')                     AS last_analyzed,
         TO_CHAR(SYS_EXTRACT_UTC(FROM_TZ(CAST(o.created AS TIMESTAMP), k.server_offset)),
                 'YYYY-MM-DD"T"HH24:MI:SS".000Z"')                     AS created,
         TO_CHAR(SYS_EXTRACT_UTC(FROM_TZ(CAST(o.last_ddl_time AS TIMESTAMP), k.server_offset)),
                 'YYYY-MM-DD"T"HH24:MI:SS".000Z"')                     AS last_ddl,
         TO_CHAR(SYS_EXTRACT_UTC(FROM_TZ(CAST(m.timestamp AS TIMESTAMP), k.server_offset)),
                 'YYYY-MM-DD"T"HH24:MI:SS".000Z"')                     AS last_dml
  FROM   {{tables}} t
         CROSS JOIN clock k
         LEFT JOIN {{objects}} o ON  o.owner          = t.owner
                                 AND o.object_name    = t.table_name
                                 AND o.object_type    = 'TABLE'
                                 AND o.subobject_name IS NULL
         LEFT JOIN {{tab_modifications}} m ON  m.table_owner = t.owner
                                           AND m.table_name  = t.table_name
                                           AND m.partition_name    IS NULL
                                           AND m.subpartition_name IS NULL
  WHERE  t.owner      = {{owner}}
  AND    t.table_name = {{table}}
)
SELECT CASE
         WHEN t.temporary = 'Y'          THEN 'TEMPORARY'
         WHEN x.table_name IS NOT NULL   THEN 'EXTERNAL'
         WHEN mv.object_name IS NOT NULL THEN 'MATERIALIZED VIEW'
         WHEN t.iot_type = 'IOT'         THEN 'INDEX ORGANIZED'
         WHEN t.cluster_name IS NOT NULL THEN 'CLUSTERED'
         WHEN t.partitioned = 'YES'      THEN 'PARTITIONED'
         ELSE 'HEAP'
       END                                                              AS table_kind,
       t.num_rows                                                       AS row_estimate,
       t.avg_row_len                                                    AS avg_row_bytes,
       d.last_analyzed,
       ROUND(SYSDATE - t.last_analyzed, 3)                              AS days_since_analyzed,
       NVL(m.inserts, 0) + NVL(m.updates, 0) + NVL(m.deletes, 0)        AS dml_since_analyzed,
       NVL(m.inserts, 0)                                                AS inserts_since_analyzed,
       NVL(m.updates, 0)                                                AS updates_since_analyzed,
       NVL(m.deletes, 0)                                                AS deletes_since_analyzed,
       NVL(m.truncated, 'NO')                                           AS truncated_since_analyzed,
       d.last_dml,
       d.created,
       d.last_ddl,
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
       JOIN dates d ON  d.owner      = t.owner
                    AND d.table_name = t.table_name
       LEFT JOIN {{objects}} o ON  o.owner          = t.owner
                               AND o.object_name    = t.table_name
                               AND o.object_type    = 'TABLE'
                               AND o.subobject_name IS NULL
       LEFT JOIN {{objects}} mv ON  mv.owner       = t.owner
                                AND mv.object_name = t.table_name
                                AND mv.object_type = 'MATERIALIZED VIEW'
       LEFT JOIN {{external_tables}} x ON  x.owner      = t.owner
                                       AND x.table_name = t.table_name
       LEFT JOIN {{tab_modifications}} m ON  m.table_owner = t.owner
                                         AND m.table_name  = t.table_name
                                         AND m.partition_name    IS NULL
                                         AND m.subpartition_name IS NULL
WHERE  t.owner      = {{owner}}
AND    t.table_name = {{table}};
