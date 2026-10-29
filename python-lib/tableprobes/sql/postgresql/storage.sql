-- =============================================================================
-- storage.sql (PostgreSQL)
-- The storage of one table: one row per object of the table and tablespace. The
-- partitions of the table (every level) are summed under the table, the partitions of an
-- index under the index of the table they come from, as Oracle sums partitions.
-- A dataset pointing at a partition gets that partition and the partitions below it.
-- -----------------------------------------------------------------------------
-- family          TABLE   table data: the table, or all its partitions
--                 INDEX   indexes
--                 LOB     TOAST tables and their indexes: values stored out of line,
--                         the PostgreSQL counterpart of Oracle LOB segments
--                 OTHER   sequences owned by the table's columns (serial, identity)
-- storage_class   TABLE, INDEX, TOAST TABLE, TOAST INDEX, SEQUENCE
-- object_owner, object_name
--                 schema and name of the object (a partition index: the index of the
--                 table it comes from)
-- tablespace_name pg_default (or the database default) when the object has none
-- n_segments      relations with storage summed in the row. An index of a partitioned
--                 table has no storage of its own: 0 when the table has no partition
-- size_bytes      all forks: main, free space map, visibility map, init
-- compression     Oracle only, NULL
-- Placeholders: {{table_oid}}
-- =============================================================================
WITH
-- the table and, when it is partitioned, its partitions at every level
tree AS (
  SELECT c.oid, c.relkind, c.relispartition, c.reltablespace, c.reltoastrelid
  FROM   pg_class c
  WHERE  c.oid = {{table_oid}}
  OR     c.oid IN (SELECT p.relid
                   FROM   pg_partition_tree(CAST({{table_oid}} AS oid)) p)
),
db AS (
  SELECT d.dattablespace AS default_ts
  FROM   pg_database d
  WHERE  d.datname = current_database()
),
-- every relation of the table, with the object it is summed under
rel AS (
  -- table data: a partitioned table has none of its own, its partitions hold it
  SELECT t.oid, 'TABLE' AS family, 'TABLE' AS storage_class,
         CAST({{table_oid}} AS oid) AS object_oid, true AS has_storage, t.reltablespace
  FROM   tree t
  WHERE  t.relkind IN ('r', 'm')
  UNION ALL
  -- indexes: the index of a partition goes under the index of the table it comes from
  -- (its ancestor defined on the table); an index created on a partition alone stays itself
  SELECT i.oid, 'INDEX', 'INDEX',
         COALESCE((SELECT CAST(a.relid AS oid)
                   FROM   pg_partition_ancestors(i.oid) a
                          JOIN pg_index ax ON ax.indexrelid = a.relid
                   WHERE  ax.indrelid = {{table_oid}}),
                  i.oid),
         i.relkind = 'i', i.reltablespace
  FROM   pg_index x
         JOIN pg_class i ON i.oid = x.indexrelid
         JOIN tree t     ON t.oid = x.indrelid
  WHERE  i.relkind IN ('i', 'I')
  UNION ALL
  -- TOAST tables
  SELECT tt.oid, 'LOB', 'TOAST TABLE', tt.oid, true, tt.reltablespace
  FROM   tree t
         JOIN pg_class tt ON tt.oid = t.reltoastrelid
  UNION ALL
  -- TOAST indexes
  SELECT ti.oid, 'LOB', 'TOAST INDEX', ti.oid, true, ti.reltablespace
  FROM   tree t
         JOIN pg_index x  ON x.indrelid = t.reltoastrelid
         JOIN pg_class ti ON ti.oid = x.indexrelid
  UNION ALL
  -- sequences owned by a column of the table: serial (dependency 'a'), identity ('i')
  SELECT s.oid, 'OTHER', 'SEQUENCE', s.oid, true, s.reltablespace
  FROM   pg_depend d
         JOIN pg_class s ON s.oid = d.objid
  WHERE  d.classid    = CAST('pg_class' AS regclass)
  AND    d.refclassid = CAST('pg_class' AS regclass)
  AND    d.refobjid IN (SELECT t.oid FROM tree t)
  AND    d.deptype IN ('a', 'i')
  AND    s.relkind = 'S'
)
SELECT r.family,
       r.storage_class,
       n.nspname                                                        AS object_owner,
       o.relname                                                        AS object_name,
       ts.spcname                                                       AS tablespace_name,
       COUNT(*) FILTER (WHERE r.has_storage)                            AS n_segments,
       SUM(pg_relation_size(r.oid, 'main') + pg_relation_size(r.oid, 'fsm')
           + pg_relation_size(r.oid, 'vm') + pg_relation_size(r.oid, 'init'))
                                                                        AS size_bytes,
       CAST(NULL AS text)                                               AS compression
FROM   rel r
       CROSS JOIN db
       JOIN pg_class o       ON o.oid = r.object_oid
       JOIN pg_namespace n   ON n.oid = o.relnamespace
       JOIN pg_tablespace ts ON ts.oid = CASE WHEN r.reltablespace = 0 THEN db.default_ts
                                              ELSE r.reltablespace
                                         END
GROUP  BY r.family, r.storage_class, n.nspname, o.relname, ts.spcname
ORDER  BY r.family, size_bytes DESC;
