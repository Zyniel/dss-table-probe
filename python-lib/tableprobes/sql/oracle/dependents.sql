-- =============================================================================
-- dependents.sql (Oracle)
-- Storage probe, step 2 of 3: the indexes and LOBs of the tables found by
-- data_tables.sql, and the index of their cluster. The tables are named as literals.
-- -----------------------------------------------------------------------------
-- family          TABLE   the top index of an index-organised table: it holds the data
--                 INDEX   indexes on the tables, also those owned by another schema
--                 LOB     LOB segments and their LOB indexes
--                 OTHER   the index of the cluster holding the table
-- storage_class   INDEX, LOBSEGMENT or LOBINDEX: the kind of segment holding the object
-- object_owner, object_name
--                 owner and name of the object, as in DBA_SEGMENTS
-- Placeholders: {{owner}} as a literal; {{table_names}} the tables, as a list of literals
-- ('ORDERS', 'SYS_IOT_OVER_73434'); {{cluster_filter}} the clusters, as
-- (i.table_owner = 'APPX' AND i.table_name = 'CUST_CL'), or 1 = 0 without cluster;
-- dictionary views {{indexes}}, {{lobs}}
-- =============================================================================
WITH
-- the LOB columns of the tables, read once for their segments and their indexes
lob_columns AS (
  SELECT /*+ MATERIALIZE */
         l.owner, l.segment_name, l.index_name
  FROM   {{lobs}} l
  WHERE  l.owner = {{owner}}
  AND    l.table_name IN {{table_names}}
)
SELECT i.owner                                                          AS object_owner,
       i.index_name                                                     AS object_name,
       CASE WHEN i.index_type = 'IOT - TOP' THEN 'TABLE' ELSE 'INDEX' END AS family,
       'INDEX'                                                          AS storage_class
FROM   {{indexes}} i
WHERE  i.table_owner = {{owner}}
AND    i.table_name IN {{table_names}}
AND    i.index_type <> 'LOB'
UNION ALL
SELECT c.owner, c.segment_name, 'LOB', 'LOBSEGMENT'
FROM   lob_columns c
UNION ALL
SELECT c.owner, c.index_name, 'LOB', 'LOBINDEX'
FROM   lob_columns c
UNION ALL
SELECT i.owner, i.index_name, 'OTHER', 'INDEX'
FROM   {{indexes}} i
WHERE  i.table_type = 'CLUSTER'
AND    ({{cluster_filter}});
