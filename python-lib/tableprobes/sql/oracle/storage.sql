-- =============================================================================
-- storage.sql (Oracle)
-- The storage of one table: one row per object of the table and tablespace, its
-- partitions and subpartitions summed. The same families on PostgreSQL.
-- -----------------------------------------------------------------------------
-- family          TABLE   table data: heap, partitions, IOT top index and overflow,
--                         nested table storage
--                 INDEX   indexes on the table, also those owned by another schema
--                 LOB     LOB segments and their LOB indexes
--                 OTHER   the cluster holding a clustered table and its cluster index
--                         (shared with the other tables of the cluster, counted whole)
-- storage_class   TABLE, INDEX, LOBSEGMENT, LOBINDEX, CLUSTER
-- object_owner, object_name
--                 owner and name of the object
-- tablespace_name NULL for an object without any segment
-- n_segments      segments summed in the row. An object without any segment (deferred
--                 segment creation, temporary or external table) still gives one row,
--                 at 0 bytes and 0 segments, so it is counted
-- size_bytes      allocated space
-- compression     data segments only: NONE, BASIC, ADVANCED, QUERY LOW|HIGH,
--                 ARCHIVE LOW|HIGH; several values when the partitions differ
-- Live segments only: a table dropped to the recycle bin has another name.
-- Placeholders: {{owner}}, {{table}} as literals; dictionary views {{tables}},
-- {{nested_tables}}, {{indexes}}, {{lobs}}, {{segments}}, {{tab_partitions}},
-- {{tab_subpartitions}}
-- =============================================================================
WITH
-- the table and the tables holding part of its data: IOT overflow and mapping table,
-- nested table storage
data_tables AS (
  SELECT t.owner, t.table_name, t.cluster_name
  FROM   {{tables}} t
  WHERE  t.owner = {{owner}}
  AND    (t.table_name = {{table}} OR t.iot_name = {{table}})
  UNION ALL
  SELECT t.owner, t.table_name, t.cluster_name
  FROM   {{nested_tables}} n
         JOIN {{tables}} t ON  t.owner      = n.owner
                           AND t.table_name = n.table_name
  WHERE  n.owner = {{owner}}
  AND    n.parent_table_name = {{table}}
),
-- every object of the table
parts AS (
  SELECT d.owner AS object_owner, d.table_name AS object_name,
         'TABLE' AS family, 'TABLE' AS storage_class
  FROM   data_tables d
  UNION ALL
  -- the top index of an index-organised table holds its data
  SELECT i.owner, i.index_name,
         CASE WHEN i.index_type = 'IOT - TOP' THEN 'TABLE' ELSE 'INDEX' END, 'INDEX'
  FROM   {{indexes}} i
         JOIN data_tables d ON  i.table_owner = d.owner
                            AND i.table_name  = d.table_name
  WHERE  i.index_type <> 'LOB'
  UNION ALL
  SELECT l.owner, l.segment_name, 'LOB', 'LOBSEGMENT'
  FROM   {{lobs}} l
         JOIN data_tables d ON  l.owner      = d.owner
                            AND l.table_name = d.table_name
  UNION ALL
  SELECT l.owner, l.index_name, 'LOB', 'LOBINDEX'
  FROM   {{lobs}} l
         JOIN data_tables d ON  l.owner      = d.owner
                            AND l.table_name = d.table_name
  UNION ALL
  SELECT DISTINCT d.owner, d.cluster_name, 'OTHER', 'CLUSTER'
  FROM   data_tables d
  WHERE  d.cluster_name IS NOT NULL
  UNION ALL
  -- the index of that cluster
  SELECT DISTINCT i.owner, i.index_name, 'OTHER', 'INDEX'
  FROM   {{indexes}} i
         JOIN data_tables d ON  i.table_owner = d.owner
                            AND i.table_name  = d.cluster_name
  WHERE  i.table_type = 'CLUSTER'
),
-- the segments of those objects, one row per (sub)partition, with their storage class
seg AS (
  SELECT s.owner, s.segment_name, s.partition_name, s.segment_type, s.tablespace_name, s.bytes,
         CASE
           WHEN s.segment_type IN ('TABLE', 'TABLE PARTITION', 'TABLE SUBPARTITION',
                                   'NESTED TABLE')                         THEN 'TABLE'
           WHEN s.segment_type IN ('INDEX', 'INDEX PARTITION', 'INDEX SUBPARTITION') THEN 'INDEX'
           WHEN s.segment_type IN ('LOBSEGMENT', 'LOB PARTITION', 'LOB SUBPARTITION') THEN 'LOBSEGMENT'
           ELSE s.segment_type
         END                                                            AS storage_class
  FROM   {{segments}} s
  WHERE  (s.owner, s.segment_name) IN (SELECT p.object_owner, p.object_name FROM parts p)
),
-- compression of the data segments
seg_compression AS (
  SELECT g.owner, g.segment_name, g.partition_name, g.storage_class, g.tablespace_name, g.bytes,
         CASE
           WHEN g.segment_type = 'TABLE SUBPARTITION'
             THEN DECODE(sp.compression, 'ENABLED', sp.compress_for, 'NONE')
           WHEN g.segment_type = 'TABLE PARTITION'
             THEN DECODE(tp.compression, 'ENABLED', tp.compress_for, 'NONE')
           WHEN g.segment_type IN ('TABLE', 'NESTED TABLE')
             THEN DECODE(t.compression, 'ENABLED', t.compress_for, 'NONE')
         END                                                            AS compression
  FROM   seg g
         LEFT JOIN {{tables}} t ON  g.segment_type IN ('TABLE', 'NESTED TABLE')
                                AND t.owner      = g.owner
                                AND t.table_name = g.segment_name
         LEFT JOIN {{tab_partitions}} tp ON  g.segment_type = 'TABLE PARTITION'
                                         AND tp.table_owner    = g.owner
                                         AND tp.table_name     = g.segment_name
                                         AND tp.partition_name = g.partition_name
         LEFT JOIN {{tab_subpartitions}} sp ON  g.segment_type = 'TABLE SUBPARTITION'
                                            AND sp.table_owner       = g.owner
                                            AND sp.table_name        = g.segment_name
                                            AND sp.subpartition_name = g.partition_name
)
SELECT p.family,
       p.storage_class,
       p.object_owner,
       p.object_name,
       c.tablespace_name,
       COUNT(c.segment_name)                                            AS n_segments,
       NVL(SUM(c.bytes), 0)                                             AS size_bytes,
       LISTAGG(DISTINCT c.compression, ',') WITHIN GROUP (ORDER BY c.compression)
                                                                        AS compression
FROM   parts p
       LEFT JOIN seg_compression c
              ON  c.owner        = p.object_owner
              AND c.segment_name = p.object_name
              -- the partitions of a LOB index are INDEX PARTITION segments
              AND (c.storage_class = p.storage_class
                   OR (p.storage_class = 'LOBINDEX' AND c.storage_class = 'INDEX'))
GROUP  BY p.family, p.storage_class, p.object_owner, p.object_name, c.tablespace_name
ORDER  BY p.family, size_bytes DESC;
