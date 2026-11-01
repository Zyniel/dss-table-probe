-- =============================================================================
-- find_ignore_case.sql (Oracle)
-- The objects whose owner and name match the dataset's ignoring case. Runs only when
-- find.sql finds nothing (a quoted mixed-case name written another way in the dataset):
-- comparing in upper case cannot use the dictionary indexes, so the objects of the
-- matching schemas are read one by one.
-- Same columns, placeholders and dictionary views as find.sql.
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
WHERE  (UPPER(o.owner) = UPPER({{schema}}) OR o.owner = {{public_owner}})
AND    UPPER(o.object_name) = UPPER({{table}})
AND    o.object_type IN ('TABLE', 'MATERIALIZED VIEW', 'VIEW', 'SYNONYM')
AND    o.subobject_name IS NULL;
