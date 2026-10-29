-- Test data of the Oracle container (Oracle Database Free, PDB FREEPDB1), run as SYSDBA.
-- What a probe meets behind a DSS dataset.
-- dbmon:     SELECT_CATALOG_ROLE only, like a monitoring admin connection
-- probe_app: a login user with no dictionary grant, owner of its tables, like the account
--            of a DSS connection
-- Their passwords come from the substitution variable test_pw: test values of this local
-- container only.
WHENEVER SQLERROR EXIT FAILURE
SET FEEDBACK OFF
SET VERIFY OFF
ALTER SESSION SET CONTAINER = FREEPDB1;
COLUMN dir NEW_VALUE pdb_dir NOPRINT
SELECT SUBSTR(file_name, 1, INSTR(file_name, '/', -1) - 1) AS dir FROM dba_data_files WHERE ROWNUM = 1;
CREATE TABLESPACE sales_dsswork_data  DATAFILE '&pdb_dir/sales_dsswork_data01.dbf'  SIZE 20M AUTOEXTEND ON NEXT 10M MAXSIZE 200M;
CREATE TABLESPACE sales_dsswork_index DATAFILE '&pdb_dir/sales_dsswork_index01.dbf' SIZE 10M AUTOEXTEND ON NEXT 10M MAXSIZE 100M;
CREATE USER sales_dsswork NO AUTHENTICATION DEFAULT TABLESPACE sales_dsswork_data
  QUOTA UNLIMITED ON sales_dsswork_data QUOTA 50M ON sales_dsswork_index;
CREATE USER sales_dssout NO AUTHENTICATION DEFAULT TABLESPACE users QUOTA UNLIMITED ON users;
GRANT CREATE TABLE, CREATE MATERIALIZED VIEW TO sales_dssout;
CREATE USER appx NO AUTHENTICATION DEFAULT TABLESPACE users QUOTA UNLIMITED ON users;
GRANT CREATE TYPE, CREATE TABLE, CREATE CLUSTER TO appx;
CREATE USER dbmon IDENTIFIED BY "&test_pw";
GRANT CREATE SESSION, SELECT_CATALOG_ROLE TO dbmon;
CREATE USER probe_app IDENTIFIED BY "&test_pw" DEFAULT TABLESPACE users QUOTA UNLIMITED ON users;
GRANT CREATE SESSION, CREATE TABLE, CREATE SYNONYM TO probe_app;
-- heap table with an out-of-line LOB, the PK index in DATA, an index in the INDEX
-- tablespace, an index owned by another schema
CREATE TABLE sales_dsswork.orders (id NUMBER PRIMARY KEY, payload CLOB, amount NUMBER)
  LOB (payload) STORE AS SECUREFILE (TABLESPACE sales_dsswork_data);
INSERT INTO sales_dsswork.orders
SELECT LEVEL, TO_CLOB(RPAD('x', 4000, 'x')) || RPAD('y', 4000, 'y'), LEVEL FROM dual CONNECT BY LEVEL <= 1000;
COMMIT;
CREATE INDEX sales_dsswork.orders_amount_ix ON sales_dsswork.orders (amount) TABLESPACE sales_dsswork_index;
CREATE INDEX appx.orders_by_appx_ix ON sales_dsswork.orders (amount, id);
-- mixed-case name: exact names win over case-insensitive matches
CREATE TABLE sales_dsswork."Orders" (id NUMBER);
-- composite partitioning: range then list, one partition compressed, local index,
-- partitioned LOB
CREATE TABLE sales_dssout.ledger (id NUMBER, d DATE, region VARCHAR2(2), amount NUMBER, note CLOB)
  PARTITION BY RANGE (d) SUBPARTITION BY LIST (region)
  SUBPARTITION TEMPLATE (SUBPARTITION eu VALUES ('EU'), SUBPARTITION us VALUES ('US'))
  (PARTITION p2025 VALUES LESS THAN (DATE '2026-01-01') COMPRESS BASIC,
   PARTITION p2026 VALUES LESS THAN (DATE '2027-01-01'));
INSERT INTO sales_dssout.ledger
SELECT LEVEL, DATE '2025-06-01' + MOD(LEVEL, 400), DECODE(MOD(LEVEL, 2), 0, 'EU', 'US'), LEVEL, NULL
FROM dual CONNECT BY LEVEL <= 20000;
COMMIT;
CREATE INDEX sales_dssout.ledger_d_ix ON sales_dssout.ledger (d) LOCAL;
-- index-organised table with an overflow segment
CREATE TABLE sales_dssout.iot_t (id NUMBER PRIMARY KEY, code VARCHAR2(10), notes VARCHAR2(2000))
  ORGANIZATION INDEX INCLUDING code OVERFLOW;
INSERT INTO sales_dssout.iot_t SELECT LEVEL, 'C' || LEVEL, RPAD('n', 500, 'n') FROM dual CONNECT BY LEVEL <= 500;
COMMIT;
CREATE MATERIALIZED VIEW sales_dssout.mv_totals AS
SELECT MOD(id, 10) AS k, COUNT(*) AS n FROM sales_dssout.ledger GROUP BY MOD(id, 10);
CREATE GLOBAL TEMPORARY TABLE sales_dssout.gtt (a NUMBER) ON COMMIT PRESERVE ROWS;
-- table never written to: no segment yet (deferred segment creation)
CREATE TABLE sales_dssout.empty_t (id NUMBER) SEGMENT CREATION DEFERRED;
-- dropped then restored: its index keeps a BIN$ name
CREATE TABLE sales_dsswork.t_restore AS SELECT LEVEL AS id, 'v' AS v FROM dual CONNECT BY LEVEL <= 1000;
CREATE INDEX sales_dsswork.t_restore_ix ON sales_dsswork.t_restore (id);
DROP TABLE sales_dsswork.t_restore;
FLASHBACK TABLE sales_dsswork.t_restore TO BEFORE DROP;
-- nested table storage, clustered table, view
CREATE TYPE appx.tags_t AS TABLE OF VARCHAR2(30);
/
CREATE TABLE appx.docs (id NUMBER, tags appx.tags_t) NESTED TABLE tags STORE AS docs_tags;
INSERT INTO appx.docs SELECT LEVEL, appx.tags_t('a', 'b', 'c') FROM dual CONNECT BY LEVEL <= 300;
COMMIT;
CREATE CLUSTER appx.cust_cl (cust_id NUMBER) SIZE 512;
CREATE INDEX appx.cust_cl_ix ON CLUSTER appx.cust_cl;
CREATE TABLE appx.cust (cust_id NUMBER, name VARCHAR2(50)) CLUSTER appx.cust_cl (cust_id);
INSERT INTO appx.cust SELECT LEVEL, 'c' || LEVEL FROM dual CONNECT BY LEVEL <= 200;
COMMIT;
GRANT SELECT ON sales_dsswork.orders TO appx;
CREATE VIEW appx.v_orders AS SELECT id, amount FROM sales_dsswork.orders;
-- private and public synonyms to ORDERS
CREATE SYNONYM appx.orders_syn FOR sales_dsswork.orders;
CREATE PUBLIC SYNONYM orders_pub FOR sales_dsswork.orders;
-- the plain account: its own table with a LOB and an index; it can read ORDERS
CREATE TABLE probe_app.app_orders (id NUMBER PRIMARY KEY, doc BLOB);
INSERT INTO probe_app.app_orders SELECT LEVEL, UTL_RAW.CAST_TO_RAW(RPAD('z', 2000, 'z')) FROM dual CONNECT BY LEVEL <= 500;
COMMIT;
GRANT SELECT ON sales_dsswork.orders TO probe_app;
EXEC DBMS_STATS.GATHER_SCHEMA_STATS('SALES_DSSWORK')
EXEC DBMS_STATS.GATHER_SCHEMA_STATS('SALES_DSSOUT')
EXEC DBMS_STATS.GATHER_SCHEMA_STATS('APPX')
EXEC DBMS_STATS.GATHER_SCHEMA_STATS('PROBE_APP')
-- changes after the statistics, flushed to DBA_TAB_MODIFICATIONS
UPDATE sales_dsswork.orders SET amount = amount + 1 WHERE id <= 300;
DELETE FROM sales_dsswork.orders WHERE id > 900;
COMMIT;
EXEC DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO
EXIT
