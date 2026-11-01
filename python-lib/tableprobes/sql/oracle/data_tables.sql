-- =============================================================================
-- data_tables.sql (Oracle)
-- Storage probe, step 1 of 3: the tables holding the data of one table. Steps 2
-- (dependents.sql) and 3 (segments.sql) then name these tables and their objects as
-- literals, so every dictionary view is read by its indexes, never scanned, however
-- many objects the database holds (Exadata, thousands of partitions).
-- -----------------------------------------------------------------------------
-- One row per table: the table itself, its IOT overflow and mapping tables
-- (SYS_IOT_OVER_<n>, SYS_IOT_MAP_<n>), its nested tables (storage of nested table
-- columns). cluster_owner, cluster_name: the cluster holding the table, if any.
-- Placeholders: {{owner}}, {{table}} as literals; dictionary views {{tables}},
-- {{nested_tables}}
-- =============================================================================
SELECT t.owner, t.table_name, t.cluster_owner, t.cluster_name
FROM   {{tables}} t
WHERE  t.owner      = {{owner}}
AND    t.table_name = {{table}}
UNION ALL
SELECT t.owner, t.table_name, t.cluster_owner, t.cluster_name
FROM   {{tables}} t
WHERE  t.owner      = {{owner}}
AND    t.table_name LIKE 'SYS\_IOT\_%' ESCAPE '\'
AND    t.iot_name   = {{table}}
UNION ALL
SELECT n.owner, n.table_name, CAST(NULL AS VARCHAR2(128)), CAST(NULL AS VARCHAR2(128))
FROM   {{nested_tables}} n
WHERE  n.owner             = {{owner}}
AND    n.parent_table_name = {{table}};
