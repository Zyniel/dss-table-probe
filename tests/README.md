# Tests

Run against two local test databases in Docker. No DSS is needed: `harness.py` stands in for the `dataiku` module (`SQLExecutor2`, `dataiku.metric`) and runs the SQL inside the containers; `FakeDataset` stands in for a SQL dataset.

```
python tests/setup_containers.py   # start the containers, load the test data (safe to run again)
python tests/test_units.py         # no database: settings, name matching, staleness, values, SQL files
python tests/test_probes.py        # both probes, run as DSS runs probe.py, on both engines
```

Each test prints one line per check (`ok` or `FAIL`) and exits with 1 when a check fails.

| Container | Image | Test data |
|---|---|---|
| `probes-pg` | `postgres:16-alpine` | [fixtures/postgresql.sql](fixtures/postgresql.sql): TOAST, a serial and an identity column, an index in another tablespace, partitions on two levels, a partitioned table without partition, a materialized view, a view, an unlogged table, two names differing by case, a second database |
| `probes-ora` | `gvenzl/oracle-free:latest` | [fixtures/oracle.sql](fixtures/oracle.sql): a LOB, an index of another schema, composite partitioning with a compressed partition and a partitioned LOB, an IOT with overflow, a nested table, a clustered table, a materialized view, a temporary table, a table without segment, a table restored from the recycle bin, a view, private and public synonyms, two names differing by case |

Other images (a registry mirror): `PROBES_PG_IMAGE`, `PROBES_ORA_IMAGE`. Other container names: `PROBES_PG_CONTAINER`, `PROBES_ORA_CONTAINER`.

The test connections and their accounts:

| Connection | Database | Account |
|---|---|---|
| `PG_APP` | PostgreSQL `appdb` | `probe_app`: plain role, owner of the tables |
| `PG_ADMIN` | PostgreSQL `appdb` | `dbmon`: `pg_monitor` |
| `PG_OTHER` | PostgreSQL `otherdb` | `probe_app` |
| `ORA_APP` | Oracle `FREEPDB1` | `probe_app`: no dictionary grant, owner of `APP_ORDERS`, may SELECT `SALES_DSSWORK.ORDERS` |
| `ORA_ADMIN` | Oracle `FREEPDB1` | `dbmon`: `SELECT_CATALOG_ROLE` |

Their passwords are test values of these local containers only. Autovacuum is off on the PostgreSQL tables the tests change, so the changes counted since the last analysis stay as the fixture left them.
