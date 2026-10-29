-- =============================================================================
-- find.sql (PostgreSQL)
-- The relations whose schema and name match the dataset's, ignoring case: the probe keeps
-- the exact match first (see location.py).
-- -----------------------------------------------------------------------------
-- table_oid       oid of the relation, used by the other queries
-- kind            TABLE, PARTITIONED TABLE, MATERIALIZED VIEW, FOREIGN TABLE, VIEW
-- target_schema, target_table, target_db_link
--                 Oracle synonyms only, NULL here
-- Placeholders: {{schema}}, {{table}} as literals
-- =============================================================================
SELECT c.oid                                                            AS table_oid,
       n.nspname                                                        AS schema_name,
       c.relname                                                        AS table_name,
       CASE c.relkind
         WHEN 'r' THEN 'TABLE'
         WHEN 'p' THEN 'PARTITIONED TABLE'
         WHEN 'm' THEN 'MATERIALIZED VIEW'
         WHEN 'f' THEN 'FOREIGN TABLE'
         WHEN 'v' THEN 'VIEW'
       END                                                              AS kind,
       CAST(NULL AS text)                                               AS target_schema,
       CAST(NULL AS text)                                               AS target_table,
       CAST(NULL AS text)                                               AS target_db_link
FROM   pg_class c
       JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE  lower(n.nspname) = lower({{schema}})
AND    lower(c.relname) = lower({{table}})
AND    c.relkind IN ('r', 'p', 'm', 'f', 'v');
