-- =============================================================================
-- table.sql (Oracle)
-- Partitioning and LOB columns of one table. One row.
-- -----------------------------------------------------------------------------
-- partitioned      YES for a partitioned table
-- n_partitions     partitions of the table
-- n_subpartitions  subpartitions of the table (composite partitioning)
-- n_lob_columns    LOB columns (CLOB, BLOB, NCLOB...), and LOB attributes of object columns
-- Placeholders: {{owner}}, {{table}} as literals; dictionary views {{tables}},
-- {{tab_partitions}}, {{tab_subpartitions}}, {{lobs}}
-- =============================================================================
SELECT t.partitioned,
       (SELECT COUNT(*)
        FROM   {{tab_partitions}} p
        WHERE  p.table_owner = t.owner
        AND    p.table_name  = t.table_name)                            AS n_partitions,
       (SELECT COUNT(*)
        FROM   {{tab_subpartitions}} sp
        WHERE  sp.table_owner = t.owner
        AND    sp.table_name  = t.table_name)                           AS n_subpartitions,
       (SELECT COUNT(*)
        FROM   {{lobs}} l
        WHERE  l.owner      = t.owner
        AND    l.table_name = t.table_name)                             AS n_lob_columns
FROM   {{tables}} t
WHERE  t.owner      = {{owner}}
AND    t.table_name = {{table}};
