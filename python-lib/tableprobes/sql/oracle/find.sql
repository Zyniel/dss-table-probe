-- =============================================================================
-- find.sql (Oracle)
-- The objects named as the dataset says, or in upper case as Oracle stores unquoted
-- names: indexed lookups only. find_ignore_case.sql runs when this finds nothing.
-- The probe keeps the exact match first, then follows synonyms (see location.py).
-- -----------------------------------------------------------------------------
-- table_oid       PostgreSQL only, NULL here
-- kind            TABLE, MATERIALIZED VIEW, VIEW, SYNONYM. A materialized view also has
--                 its container TABLE of the same name: the probe keeps the TABLE row
-- target_schema, target_table, target_db_link
--                 what a synonym points to
-- Placeholders: {{schema}}, {{table}} as literals; {{public_owner}} 'PUBLIC' when the
-- dataset has no schema (public synonyms are then looked at too), else NULL;
-- dictionary views {{objects}}, {{synonyms}}
-- =============================================================================
SELECT CAST(NULL AS NUMBER)                                             AS table_oid,
       o.owner                                                          AS schema_name,
       o.object_name                                                    AS table_name,
       o.object_type                                                    AS kind,
       s.table_owner                                                    AS target_schema,
       s.table_name                                                     AS target_table,
       s.db_link                                                        AS target_db_link
FROM   {{objects}} o
       LEFT JOIN {{synonyms}} s ON  o.object_type = 'SYNONYM'
                                AND s.owner        = o.owner
                                AND s.synonym_name = o.object_name
WHERE  o.owner IN ({{schema}}, UPPER({{schema}}), {{public_owner}})
AND    o.object_name IN ({{table}}, UPPER({{table}}))
AND    o.object_type IN ('TABLE', 'MATERIALIZED VIEW', 'VIEW', 'SYNONYM')
AND    o.subobject_name IS NULL;
