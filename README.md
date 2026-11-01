# dss-table-probe: metrics on the table behind a dataset

A DSS plugin with two custom probes for Oracle and PostgreSQL datasets. A user turns them on in the Metrics tab of a dataset and gets, as metrics, what the database knows about the dataset's table:

| Probe | What it measures |
|---|---|
| **Table storage** | the space the table takes, by family of objects: table data, indexes, LOB (TOAST on PostgreSQL), other; storage units, indexes, LOB columns, partitions, tablespaces, compression |
| **Table statistics** | optimizer statistics (rows, last analysis, rows changed since, stale or not), lifecycle (Oracle creation and last DDL), activity (PostgreSQL live and dead rows, vacuum, scans) |

The space is split into four families of objects (`table_mb`, `index_mb`, `lob_mb`, `other_mb`), the same on both engines, read from the database dictionary for this one table when the user asks.

Each metric gets its history in DSS: a dataset's growth, an index larger than its data, statistics that go stale, can be charted, checked by a data quality rule, and followed in a scenario.

## Install

- Plugins > Add plugin > Upload: `dss-table-probe-1.1.0.zip`. Or Fetch from Git repository, when the plugin is in a repository.
- No code environment: the probes run in the DSS built-in environment (Python 3.9 on DSS 13.2) and only use `dataiku` and `pandas`.

## Use

1. On an Oracle or PostgreSQL dataset: Metrics tab (Status on older versions) > Edit Metrics. Both probes are in the list of probes, as **Table storage (Oracle, PostgreSQL)** and **Table statistics (Oracle, PostgreSQL)**: turn them on.
2. Tick the metrics to compute in each probe's settings. Every metric is optional: only **Total size** (`total_mb`) is ticked by default, in the storage probe; the statistics probe has none ticked. A probe runs only the queries its ticked metrics need, and stops with an error when none is ticked.
3. Compute. The metrics appear in the list of available metrics: choose those to display.
4. Optional: compute them after each build ("Auto compute after build"), or in a scenario step "Compute metrics".

A partitioned SQL dataset keeps all its partitions in one table: the probes always describe the whole table, also when DSS computes them on one partition.

### Settings

| Setting | | Default |
|---|---|---|
| Read through connection | another DSS connection to **the same database**, e.g. an admin account with dictionary rights. The probe refuses a connection that reaches another database (Oracle: `DB_UNIQUE_NAME/CON_NAME`; PostgreSQL: server start time and database). The user computing the metrics must be allowed to use it | the dataset's connection |
| Oracle dictionary | `Automatic`: the DBA_ views, else those of the login user. `DBA views only`. `Login user's views only` | Automatic |
| Stale statistics threshold (%) | statistics probe, shown when `stale_stats` is ticked: `stale_stats` is YES from this % of rows changed since the last analysis | 10 (Oracle's `STALE_PERCENT`) |

### Rights on the database

| | Table storage | Table statistics |
|---|---|---|
| Oracle with `SELECT_CATALOG_ROLE` (or `SELECT ANY DICTIONARY`) | every table | every table |
| Oracle without | the tables of the login user only: Oracle shows the segments of other schemas in `DBA_SEGMENTS` only. The probe says which grant is missing | every table the login user may read (`ALL_` views) |
| PostgreSQL | any role | any role. `avg_row_bytes` needs SELECT on the table (`pg_stats` hides the columns a role cannot read) |

The accounts of DSS connections usually own the tables they write: the dataset's own connection is enough. For a dataset reading someone else's table on Oracle, choose an admin connection in "Read through connection".

The probe's sessions show as module `DSS_TABLE_PROBE` with the query as action (Oracle, `GV$SESSION` on a RAC), or application `dss table probe <query>` (PostgreSQL, `pg_stat_activity`). Each query reads the dictionary filtered on the one table.

### Which table

The table comes from the dataset settings, with variables resolved by DSS. When the dataset has no schema, the connection's default applies (Oracle: current schema, including `ALTER SESSION SET CURRENT_SCHEMA` in post-connect statements; PostgreSQL: the schema where the `search_path` finds the table), and on Oracle public synonyms too. In the database, names are looked up as written, or as the database stores unquoted names (upper case on Oracle, lower case on PostgreSQL): `orders` finds `ORDERS` on Oracle. Only when neither exists are names compared ignoring case; two objects matching that way is an error. Oracle synonyms are followed to their table, not through a database link.

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
| `compression` | Oracle only: compression setting of the data (`NONE`, `BASIC`, `ADVANCED`, Exadata Hybrid Columnar Compression `QUERY LOW`/`QUERY HIGH`/`ARCHIVE LOW`/`ARCHIVE HIGH`...), read on the subpartitions, else the partitions, else the table; comma separated when they differ |

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
| `created`, `last_ddl`, `days_since_ddl` | Oracle | creation and last DDL of the table (`DBA_OBJECTS`) |
| `logging` | both | Oracle `LOGGING` (none on a partitioned table: set per partition); PostgreSQL NO for an unlogged table |
| `parallel_degree` | Oracle | `DEGREE` |
| `live_rows`, `dead_rows`, `dead_rows_pct` | PostgreSQL | live and dead row versions, dead in % of both |
| `last_vacuum`, `days_since_vacuum` | PostgreSQL | latest vacuum, manual or automatic |
| `seq_scans`, `index_scans` | PostgreSQL | scans since the statistics counters were reset |

Dates are DSS date metrics, in UTC. Oracle dictionary dates follow the server's clock: they are converted with its current offset. A metric the database cannot give (statistics never gathered, a column of the other engine) is left out rather than stored empty.

Right after a load, by the table's own account and without any grant:

- Sizes are exact on both engines.
- Oracle 21c and later include the changes still held in memory, on every instance of a RAC (`GV$DML_STATS`): rows inserted show in `dml_since_analyzed` as soon as they are committed (tested on 21c and 26ai, single instance). Older versions may only show them once the database writes them to the dictionary; `DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO` forces it, but needs `ANALYZE ANY`. Each statistics gathering resets these counts.
- PostgreSQL counts the changes once the writing session is done: at once when it disconnects, within about 10 seconds when it stays connected and idle (tested on 16). The counters restart with `pg_stat_reset()` or after a crash.
- `row_estimate` and `last_analyzed` describe the last statistics gathering, not the load: a load into an analyzed table shows as `stale_stats = YES` once it changes more than the threshold.

## Oracle on Exadata and RAC

The Oracle queries are written for large databases:

- Every dictionary view is filtered on the owner and the names of the table's objects, written as literals, so Oracle reads the dictionary through its indexes. The storage probe works in three steps for that: the tables holding the data (`data_tables.sql`), their indexes and LOBs (`dependents.sql`), then their segments by name (`segments.sql`). A probe's cost depends on the table's own objects and partitions, not on the size of the database.
- The case-insensitive name lookup, which cannot use the indexes, only runs when the name is found neither as written nor in upper case.
- No `V$` view is read, so nothing depends on the instance a session lands on. The database identity used to check "Read through connection" (`DB_UNIQUE_NAME/CON_NAME`) is the same on every instance of a RAC. On 21c and later, the changes since the last analysis include those still in memory on every instance (`DBA_TAB_MODIFICATIONS` reads `GV$DML_STATS`).
- Sizes are allocated bytes: compressed bytes with Hybrid Columnar Compression.
- `DBA_TAB_STATISTICS` is not read: on Exadata it holds a second row per table for real-time statistics. `row_estimate`, `avg_row_bytes` and `last_analyzed` come from `DBA_TABLES`, the last statistics gathering.

Measured on Oracle Database Free, in a PDB where the account's schema holds 6,000 tables and a table of 1,500 partitions (6,000 segments). Database time in seconds for a probe with every metric ticked, admin views / login user's views, before and after these queries:

| | Before | After |
|---|---|---|
| Table storage, a table with a LOB and an index | 1.5 / 7.3 | 0.02 / 0.01 |
| Table storage, the 1,500-partition table | 1.9 / 9.1 | 0.8 / 1.0 |
| Table statistics, the 1,500-partition table | 1.4 / over 90 (stopped) | 0.13 / 0.30 |

Not tested on Exadata nor on a RAC: what is said of them comes from the definitions of the dictionary views.

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
├── catalog.py            the metrics of each probe: their checkboxes, ticked by default or not
├── storage.py            Table storage metrics
├── statistics.py         Table statistics metrics
├── metrics.py            values as DSS stores them (dates, missing values, ticked metrics)
├── settings.py           probe settings
└── sql/
    ├── oracle/           session, find, find_ignore_case, table, statistics;
    │                     storage in three steps: data_tables, dependents, segments
    └── postgresql/       the same shared files, same columns in the same order; storage
tests/                    see tests/README.md
```

### Changing a query

- Each SQL file runs in SQL*Plus or psql once its `{{placeholders}}` are replaced: names as literals (`'SALES_DSSWORK'`), PostgreSQL `{{table_oid}}` as a number, Oracle dictionary views (`{{segments}}` → `dba_segments`, see `ORACLE_VIEWS` in database.py).
- The files both engines have return the same columns in the same order; a column that does not exist on one engine is NULL there. A new column of `statistics.sql` is declared in `statistics.py` (text, integer, decimal or date).
- Oracle: filter every dictionary view on literal owners and names, never through a join or a subquery the optimizer may turn into a scan.
- A new metric goes in `catalog.py` and gets its checkbox in the probe's `probe.json`: the unit tests check that both list the same metrics with the same defaults.
- Oracle files keep SQL*Plus rules: no blank line inside the statement, no `&`.
- Run the tests afterwards.

## Compatibility

DSS 13.2 and later, Python 3.9 and later. Oracle 19c and later (`LISTAGG(DISTINCT)`), tested on Oracle AI Database 26ai Free. PostgreSQL 12 and later (`pg_partition_tree`, `pg_partition_ancestors`), tested on PostgreSQL 16.
