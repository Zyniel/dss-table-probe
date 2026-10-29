-- =============================================================================
-- session.sql (PostgreSQL)
-- Who the connection is and which database it reaches. One row.
-- -----------------------------------------------------------------------------
-- login_user      role of the connection
-- current_schema  first schema of the search_path
-- table_schema    schema where the search_path finds the table, NULL when it finds none:
--                 the schema of a dataset that has none
-- database_id     server start time and database: two connections giving the same value
--                 reach the same database. Readable by any role
-- Placeholders: {{quoted_table}} the table name, quoted as an identifier, as a literal
-- =============================================================================
SELECT current_user                                                     AS login_user,
       current_schema()                                                 AS current_schema,
       (SELECT n.nspname
        FROM   pg_class c
               JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE  c.oid = to_regclass({{quoted_table}}))                   AS table_schema,
       to_char(pg_postmaster_start_time() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US')
       || '/' || current_database()                                     AS database_id;
