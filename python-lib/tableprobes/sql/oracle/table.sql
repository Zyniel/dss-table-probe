-- =============================================================================
-- table.sql (Oracle)
-- Partitioning, LOB columns and compression of one table. One row.
-- -----------------------------------------------------------------------------
-- partitioned      YES for a partitioned table
-- n_partitions     partitions of the table (interval partitions created so far)
-- n_subpartitions  subpartitions of the table (composite partitioning)
-- n_lob_columns    LOB columns (CLOB, BLOB, NCLOB...), and LOB attributes of object columns
-- compression      compression of the data: NONE, BASIC, ADVANCED, QUERY LOW|HIGH,
--                  ARCHIVE LOW|HIGH (Exadata Hybrid Columnar Compression)...; read on the
--                  subpartitions, else the partitions, else the table; comma separated
--                  when they differ
-- Placeholders: {{owner}}, {{table}} as literals; dictionary views {{tables}},
-- {{tab_partitions}}, {{tab_subpartitions}}, {{lobs}}
-- =============================================================================
WITH
partitions AS (
  SELECT COUNT(*)                                                       AS n_partitions,
         LISTAGG(DISTINCT DECODE(p.compression, 'ENABLED', p.compress_for, 'NONE'), ',')
           WITHIN GROUP (ORDER BY DECODE(p.compression, 'ENABLED', p.compress_for, 'NONE'))
                                                                        AS compression
  FROM   {{tab_partitions}} p
  WHERE  p.table_owner = {{owner}}
  AND    p.table_name  = {{table}}
),
subpartitions AS (
  SELECT COUNT(*)                                                       AS n_subpartitions,
         LISTAGG(DISTINCT DECODE(sp.compression, 'ENABLED', sp.compress_for, 'NONE'), ',')
           WITHIN GROUP (ORDER BY DECODE(sp.compression, 'ENABLED', sp.compress_for, 'NONE'))
                                                                        AS compression
  FROM   {{tab_subpartitions}} sp
  WHERE  sp.table_owner = {{owner}}
  AND    sp.table_name  = {{table}}
),
lob_columns AS (
  SELECT COUNT(*)                                                       AS n_lob_columns
  FROM   {{lobs}} l
  WHERE  l.owner      = {{owner}}
  AND    l.table_name = {{table}}
)
SELECT t.partitioned,
       p.n_partitions,
       sp.n_subpartitions,
       l.n_lob_columns,
       CASE
         WHEN sp.n_subpartitions > 0 THEN sp.compression
         WHEN p.n_partitions > 0     THEN p.compression
         ELSE DECODE(t.compression, 'ENABLED', t.compress_for, 'NONE')
       END                                                              AS compression
FROM   {{tables}} t
       CROSS JOIN partitions p
       CROSS JOIN subpartitions sp
       CROSS JOIN lob_columns l
WHERE  t.owner      = {{owner}}
AND    t.table_name = {{table}};
