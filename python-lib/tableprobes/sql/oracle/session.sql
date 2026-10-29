-- =============================================================================
-- session.sql (Oracle)
-- Who the connection is and which database it reaches. One row.
-- -----------------------------------------------------------------------------
-- login_user      user of the connection
-- current_schema  schema of unqualified names: the schema of a dataset that has none
--                 (ALTER SESSION SET CURRENT_SCHEMA in post-connect statements included)
-- table_schema    PostgreSQL only, NULL here
-- database_id     DB_UNIQUE_NAME / container: two connections giving the same value reach
--                 the same database (the same PDB of the same physical copy)
-- Placeholders: {{quoted_table}}, not used on Oracle
-- =============================================================================
SELECT USER                                                             AS login_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')                         AS current_schema,
       CAST(NULL AS VARCHAR2(128))                                      AS table_schema,
       SYS_CONTEXT('USERENV', 'DB_UNIQUE_NAME') || '/' || SYS_CONTEXT('USERENV', 'CON_NAME')
                                                                        AS database_id
FROM   dual;
