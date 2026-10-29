# dss-table-probe: metrics on the table behind a dataset

A DSS plugin with two custom probes for Oracle and PostgreSQL datasets. A user turns them on in the Metrics tab of a dataset and gets, as metrics, what the database knows about the dataset's table:

| Probe | What it measures |
|---|---|
| **Table storage** | the space the table takes, by family of objects: table data, indexes, LOB (TOAST on PostgreSQL), other; storage units, indexes, LOB columns, partitions, tablespaces, compression |
| **Table statistics** | optimizer statistics (rows, last analysis, rows changed since, stale or not), lifecycle (Oracle creation, last DDL and DML), activity (PostgreSQL live and dead rows, vacuum, scans) |

The space is split into four families of objects (`table_mb`, `index_mb`, `lob_mb`, `other_mb`), the same on both engines, read from the database dictionary for this one table when the user asks.

Each metric gets its history in DSS: a dataset's growth, an index larger than its data, statistics that go stale, can be charted, checked by a data quality rule, and followed in a scenario.

## Install

- Plugins > Add plugin > Upload: `dss-table-probe-1.0.0.zip`. Or Fetch from Git repository, when the plugin is in a repository.
- No code environment: the probes run in the DSS built-in environment (Python 3.9 on DSS 13.2) and only use `dataiku` and `pandas`.

## Use

1. On an Oracle or PostgreSQL dataset: Metrics tab (Status on older versions) > Edit Metrics. Both probes are in the list of probes, as **Table storage (Oracle, PostgreSQL)** and **Table statistics (Oracle, PostgreSQL)**: turn them on.
2. Compute. The metrics appear in the list of available metrics: choose those to display.
3. Optional: compute them after each build ("Auto compute after build"), or in a scenario step "Compute metrics".

A partitioned SQL dataset keeps all its partitions in one table: the probes always describe the whole table, also when DSS computes them on one partition.

### Settings

| Setting | | Default |
|---|---|---|
| Read through connection | another DSS connection to **the same database**, e.g. an admin account with dictionary rights. The probe refuses a connection that reaches another database (Oracle: `DB_UNIQUE_NAME/CON_NAME`; PostgreSQL: server start time and database). The user computing the metrics must be allowed to use it | the dataset's connection |
| Oracle dictionary | `Automatic`: the DBA_ views, else those of the login user. `DBA views only`. `Login user's views only` | Automatic |
| Stale statistics threshold (%) | statistics probe: `stale_stats` is YES from this % of rows changed since the last analysis | 10 (Oracle's `STALE_PERCENT`) |

### Rights on the database

| | Table storage | Table statistics |
|---|---|---|
| Oracle with `SELECT_CATALOG_ROLE` (or `SELECT ANY DICTIONARY`) | every table | every table |
| Oracle without | the tables of the login user only: Oracle shows the segments of other schemas in `DBA_SEGMENTS` only. The probe says which grant is missing | every table the login user may read (`ALL_` views) |
| PostgreSQL | any role | any role. `avg_row_bytes` needs SELECT on the table (`pg_stats` hides the columns a role cannot read) |

The accounts of DSS connections usually own the tables they write: the dataset's own connection is enough. For a dataset reading someone else's table on Oracle, choose an admin connection in "Read through connection".

The probe's sessions show as module `DSS_TABLE_PROBE` with the query as action (Oracle, `V$SESSION`), or application `dss table probe <query>` (PostgreSQL, `pg_stat_activity`). Each query reads the dictionary filtered on the one table.

### Which table

The table comes from the dataset settings, with variables resolved by DSS. When the dataset has no schema, the connection's default applies (Oracle: current schema, including `ALTER SESSION SET CURRENT_SCHEMA` in post-connect statements; PostgreSQL: the schema where the `search_path` finds the table), and on Oracle public synonyms too. In the database, the exact names win, then the table name exactly, then both ignoring case; two objects matching ignoring case and none exactly is an error. Oracle synonyms are followed to their table, not through a database link.

A view, a SQL query dataset, a dataset of another database type: the probes stop with an error that says why.

## Table storage

### Families

| Family | Oracle | PostgreSQL |
|---|---|---|
| `table` | table data: heap, every partition and subpartition, IOT top index and overflow, nested table storage. A materialized view: its container table | the table, or every partition of every level |
| `index` | indexes on the table, also those owned by another schema (partitions summed: one index) | indexes (the index of each partition under the index of the table it comes from) |
| `lob` | LOB segments and their LOB indexes | TOAST tables and their indexes: values stored out of line |
| `other` | the cluster of a clustered table and its cluster index (shared with the other tables of the cluster: counted whole) | sequences owned by the table's columns: serial, identity |

The `other` objects are counted with their table: a tool summing every object of a database without attributing sequences or clusters to a table finds a `total_mb` a few KB lower.

### Metrics

| Metric | Meaning |
|---|---|
| `total_mb` | allocated space of all the table's objects, MB (1 MB = 1,048,576 bytes) |
| `table_mb`, `index_mb`, `lob_mb`, `other_mb` | the same by family; they add up to `total_mb` |
| `total_segments` | storage units: Oracle segments (one per partition or subpartition), PostgreSQL relations |
| `table_segments`, `index_segments`, `lob_segments`, `other_segments` | the same by family. 0 with data: a table without segment yet (Oracle deferred segment creation), a temporary or external table |
| `n_indexes` | indexes of the table |
| `n_lob_columns` | Oracle: LOB columns. PostgreSQL: columns whose values can go out of line to TOAST (text, varchar, bytea, jsonb...) |
| `partitioned` | YES or NO |
| `n_partitions`, `n_subpartitions` | Oracle: partitions and subpartitions. PostgreSQL: partitions directly under the table, and those of every level below |
| `n_tablespaces`, `tablespaces` | tablespaces holding the table's objects, comma separated. No `tablespaces` metric when nothing is stored |
| `compression` | Oracle only: compression of the data (`NONE`, `BASIC`, `ADVANCED`, `QUERY HIGH`...), comma separated when partitions differ |

## Table statistics

| Metric | Engine | Meaning |
|---|---|---|
| `table_kind` | both | `HEAP`, `PARTITIONED`, `MATERIALIZED VIEW`, `TEMPORARY`; Oracle `INDEX ORGANIZED`, `CLUSTERED`, `EXTERNAL`; PostgreSQL `UNLOGGED`, `FOREIGN` |
| `row_estimate` | both | rows at the last analysis (Oracle `NUM_ROWS`, PostgreSQL `reltuples`, summed over the partitions) |
| `avg_row_bytes` | both | average row length (Oracle `AVG_ROW_LEN`, PostgreSQL sum of the columns' `avg_width`) |
| `last_analyzed` | both | date of the last statistics gathering (PostgreSQL: the latest among the partitions) |
| `days_since_analyzed` | both | days since then, with decimals |
| `dml_since_analyzed` | both | rows inserted, updated or deleted since |
| `dml_pct_since_analyzed` | both | the same in % of `row_estimate` (100 for a table analyzed empty and written since) |
| `stale_stats` | both | YES when never analyzed, truncated since (Oracle), or `dml_pct_since_analyzed` reaches the threshold |
| `inserts_since_analyzed`, `updates_since_analyzed`, `deletes_since_analyzed` | Oracle | `dml_since_analyzed` split by kind |
| `truncated_since_analyzed` | Oracle | YES or NO |
| `last_dml` | Oracle | date of the last change recorded in `DBA_TAB_MODIFICATIONS` |
| `created`, `last_ddl`, `days_since_ddl` | Oracle | creation and last DDL of the table (`DBA_OBJECTS`) |
| `logging` | both | Oracle `LOGGING` (none on a partitioned table: set per partition); PostgreSQL NO for an unlogged table |
| `parallel_degree` | Oracle | `DEGREE` |
| `live_rows`, `dead_rows`, `dead_rows_pct` | PostgreSQL | live and dead row versions, dead in % of both |
| `last_vacuum`, `days_since_vacuum` | PostgreSQL | latest vacuum, manual or automatic |
| `seq_scans`, `index_scans` | PostgreSQL | scans since the statistics counters were reset |

Dates are DSS date metrics, in UTC. Oracle dictionary dates follow the server's clock: they are converted with its current offset. A metric the database cannot give (statistics never gathered, a column of the other engine) is left out rather than stored empty.

Oracle records changes in memory and writes them to `DBA_TAB_MODIFICATIONS` every few minutes, and each statistics gathering resets them: `dml_since_analyzed` can lag behind the last minutes. PostgreSQL activity counters restart with `pg_stat_reset()` or a crash.

## Checks

Examples of data quality rules (or Python checks) on these metrics:

- "Metric value in range" on `total_mb`, to warn before a table outgrows its tablespace quota.
- `stale_stats` in set `NO`, on tables read by heavy recipes.
- `index_mb` above `table_mb`, or `dead_rows_pct` above 20: maintenance to plan with the DBAs.

## Layout

```
plugin.json
python-probes/
├── table-storage/        probe.json (settings), probe.py
└── table-statistics/     probe.json, probe.py
python-lib/tableprobes/
├── location.py           which table: dataset settings, default schema, same database, names, synonyms
├── database.py           runs the SQL files: placeholders, session tag, Oracle DBA_ / ALL_ views
├── storage.py            Table storage metrics
├── statistics.py         Table statistics metrics
├── metrics.py            values as DSS stores them (dates, missing values)
├── settings.py           probe settings
└── sql/
    ├── oracle/           session, find, storage, table, statistics
    └── postgresql/       the same five files, same columns in the same order
tests/                    see tests/README.md
```

### Changing a query

- Each SQL file runs in SQL*Plus or psql once its `{{placeholders}}` are replaced: names as literals (`'SALES_DSSWORK'`), PostgreSQL `{{table_oid}}` as a number, Oracle dictionary views (`{{segments}}` → `dba_segments`, see `ORACLE_VIEWS` in database.py).
- Both engines return the same columns in the same order; a column that does not exist on one engine is NULL there. A new column of `statistics.sql` is declared in `statistics.py` (text, integer, decimal or date).
- Oracle files keep SQL*Plus rules: no blank line inside the statement, no `&`.
- Run the tests afterwards.

## Compatibility

DSS 13.2 and later, Python 3.9 and later. Oracle 19c and later (`LISTAGG(DISTINCT)`), tested on Oracle AI Database 26ai Free. PostgreSQL 12 and later (`pg_partition_tree`, `pg_partition_ancestors`), tested on PostgreSQL 16.
