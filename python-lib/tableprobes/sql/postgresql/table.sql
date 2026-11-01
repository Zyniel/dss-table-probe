-- =============================================================================
-- table.sql (PostgreSQL)
-- Partitioning and out-of-line columns of one table. One row.
-- -----------------------------------------------------------------------------
-- partitioned      YES for a partitioned table
-- n_partitions     partitions directly under the table
-- n_subpartitions  partitions of its partitions, every level below
-- n_lob_columns    columns whose values can be stored out of line in TOAST (storage
--                  EXTENDED or EXTERNAL: text, varchar, bytea, jsonb...), the counterpart
--                  of Oracle LOB columns
-- compression      Oracle only, NULL
-- Placeholders: {{table_oid}}
-- =============================================================================
SELECT CASE WHEN c.relkind = 'p' THEN 'YES' ELSE 'NO' END                AS partitioned,
       (SELECT COUNT(*)
        FROM   pg_partition_tree(c.oid) p
        WHERE  p.level = 1)                                             AS n_partitions,
       (SELECT COUNT(*)
        FROM   pg_partition_tree(c.oid) p
        WHERE  p.level >= 2)                                            AS n_subpartitions,
       (SELECT COUNT(*)
        FROM   pg_attribute a
        WHERE  a.attrelid = c.oid
        AND    a.attnum > 0
        AND    NOT a.attisdropped
        AND    a.attstorage IN ('x', 'e'))                              AS n_lob_columns,
       CAST(NULL AS text)                                               AS compression
FROM   pg_class c
WHERE  c.oid = {{table_oid}};
