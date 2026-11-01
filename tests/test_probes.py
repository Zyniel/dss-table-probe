"""The two probes on the test containers, run as DSS runs them: probe.py with its config.

    python tests/setup_containers.py
    python tests/test_probes.py
"""
import os
import re
import runpy

import harness
from harness import FakeDataset, check, finish

harness.install_fake_dataiku()

import dataiku  # noqa: E402  (the stand-in)

from tableprobes import catalog, database  # noqa: E402

PROBES = os.path.join(harness.REPO, "python-probes")
ISO_UTC = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.000Z$")

STORAGE_SIZES = ("total_mb", "table_mb", "index_mb", "lob_mb", "other_mb")
STORAGE_SEGMENTS = ("total_segments", "table_segments", "index_segments", "lob_segments", "other_segments")


def ticked(groups):
    """A config with every metric of a probe ticked."""
    config = {}
    for metric in catalog.all_metrics(groups):
        config["metric_" + metric.name] = True
    return config


ALL_STORAGE = ticked(catalog.STORAGE_GROUPS)
ALL_STATISTICS = ticked(catalog.STATISTICS_GROUPS)


def probe(name, dataset, config):
    """Run python-probes/<name>/probe.py as DSS does: config as a global, process()."""
    namespace = runpy.run_path(os.path.join(PROBES, name, "probe.py"), init_globals={"config": config})
    return namespace["process"](dataset, "ALL")


def storage(connection, schema, table, config=None):
    """The storage probe with every metric ticked, and the settings of config."""
    return probe("table-storage", FakeDataset(connection, schema, table), dict(ALL_STORAGE, **(config or {})))


def statistics(connection, schema, table, config=None):
    """The statistics probe with every metric ticked, and the settings of config."""
    return probe("table-statistics", FakeDataset(connection, schema, table),
                 dict(ALL_STATISTICS, **(config or {})))


def queries_since(start):
    """Names of the SQL files run since harness.QUERIES had start entries, from the session
    tag each query runs after."""
    names = []
    for _connection, _sql, pre_queries in harness.QUERIES[start:]:
        tag = re.search(r"action_name => '(\w+)'|dss table probe (\w+)", " ".join(pre_queries or []))
        if tag:
            names.append(tag.group(1) or tag.group(2))
    return names


def error_of(function, *arguments):
    """Text of the error function(*arguments) raises, "" when it raises none."""
    try:
        function(*arguments)
        return ""
    except Exception as error:
        return "%s: %s" % (type(error).__name__, error)


def families_add_up(metrics):
    sizes = round(metrics["table_mb"] + metrics["index_mb"] + metrics["lob_mb"] + metrics["other_mb"], 3)
    segments = (metrics["table_segments"] + metrics["index_segments"] + metrics["lob_segments"]
                + metrics["other_segments"])
    return abs(sizes - metrics["total_mb"]) <= 0.002 and segments == metrics["total_segments"]


# =========================================================================================
# PostgreSQL
# =========================================================================================
orders = storage("PG_APP", "sales_dsswork", "SALES_orders")
check("pg storage: every size and segment metric", all(name in orders for name in STORAGE_SIZES + STORAGE_SEGMENTS),
      orders)
check("pg storage: the families add up to the total", families_add_up(orders), orders)
check("pg storage: TOAST table and index are LOB", orders["lob_segments"] == 2 and orders["lob_mb"] > 10, orders)
check("pg storage: the serial sequence is OTHER", orders["other_segments"] == 1 and orders["other_mb"] > 0, orders)
check("pg storage: PK and amount indexes", orders["n_indexes"] == 2 and orders["index_segments"] == 2, orders)
check("pg storage: text and jsonb can go out of line", orders["n_lob_columns"] == 2, orders)
check("pg storage: index in its own tablespace",
      orders["tablespaces"] == "pg_default,sales_dsswork_index" and orders["n_tablespaces"] == 2, orders)
check("pg storage: not partitioned",
      orders["partitioned"] == "NO" and orders["n_partitions"] == 0 and orders["n_subpartitions"] == 0, orders)
check("pg storage: no compression metric (Oracle only)", "compression" not in orders, orders)

lower_case = storage("PG_APP", "sales_dsswork", "sales_orders")
check("pg: the exact name wins over a match ignoring case", lower_case["total_mb"] < orders["total_mb"]
      and lower_case["n_indexes"] == 0, lower_case)
check("pg: a dataset without schema finds the table through the search_path",
      storage("PG_APP", None, "SALES_orders") == orders)
check("pg: schema written in another case", storage("PG_APP", "SALES_DSSWORK", "SALES_orders") == orders)
start = len(harness.QUERIES)
storage("PG_APP", "sales_dsswork", "SALES_orders")
check("pg: exact names are found without the case-insensitive lookup",
      "find_ignore_case" not in queries_since(start), queries_since(start))
start = len(harness.QUERIES)
check("pg: a name written in another case, found ignoring case",
      storage("PG_OTHER", "sales_dsswork", "Sales_Orders")["table_segments"] == 1
      and "find_ignore_case" in queries_since(start))
check("pg: two names equal ignoring case, none as written nor in lower case, are refused",
      "several objects" in error_of(storage, "PG_APP", "sales_dsswork", "lINES"))

ledger = storage("PG_APP", "fin_dssout", "ledger")
check("pg storage: partitioned table, 2 partitions, 2 subpartitions",
      ledger["partitioned"] == "YES" and ledger["n_partitions"] == 2 and ledger["n_subpartitions"] == 2, ledger)
check("pg storage: data of the 3 leaf partitions summed", ledger["table_segments"] == 3 and ledger["table_mb"] > 0.5,
      ledger)
check("pg storage: the partition indexes are one index", ledger["n_indexes"] == 1 and ledger["index_segments"] == 3,
      ledger)
partition = storage("PG_APP", "fin_dssout", "ledger_2026")
check("pg storage: a dataset on a partition gets its subtree, its own index",
      partition["table_segments"] == 2 and partition["n_indexes"] == 1 and partition["n_partitions"] == 2
      and partition["n_subpartitions"] == 0, partition)
empty_parent = storage("PG_APP", "fin_dssout", "empty_parent")
check("pg storage: partitioned without partition: 0 MB, its index counted",
      empty_parent["total_mb"] == 0 and empty_parent["total_segments"] == 0 and empty_parent["n_indexes"] == 1,
      empty_parent)
events = storage("PG_APP", "appx", "events")
check("pg storage: the identity sequence is OTHER", events["other_segments"] == 1 and events["n_lob_columns"] == 0,
      events)
check("pg storage: a materialized view has storage", storage("PG_APP", "appx", "mv_totals")["table_segments"] == 1)

check("pg: a view has no storage", "is a VIEW" in error_of(storage, "PG_APP", "appx", "v_events"))
check("pg: a missing table", "not found" in error_of(storage, "PG_APP", "appx", "nothing_here"))

admin = storage("PG_APP", "sales_dsswork", "SALES_orders", {"read_connection": "PG_ADMIN"})
check("pg: read through a pg_monitor connection, same figures", admin == orders, admin)
check("pg: a read connection on another database is refused",
      "reaches database" in error_of(storage, "PG_APP", "sales_dsswork", "SALES_orders",
                                     {"read_connection": "PG_OTHER"}))

stats = statistics("PG_APP", "fin_dssout", "ledger")
check("pg statistics: partitioned, rows of the leaves", stats["table_kind"] == "PARTITIONED"
      and stats["row_estimate"] == 20000, stats)
check("pg statistics: 500 rows deleted since the analysis", stats["dml_since_analyzed"] == 500
      and stats["dml_pct_since_analyzed"] == round(100.0 * 500 / stats["row_estimate"], 2)
      and stats["stale_stats"] == "NO", stats)
check("pg statistics: stale at a 2 % threshold",
      statistics("PG_APP", "fin_dssout", "ledger", {"stale_pct": 2})["stale_stats"] == "YES")
check("pg statistics: dates are DSS dates, UTC", ISO_UTC.match(stats["last_analyzed"][0]) is not None
      and stats["last_analyzed"][1] == "DATE", stats["last_analyzed"])
check("pg statistics: activity", stats["live_rows"] >= 0 and "dead_rows_pct" in stats and "seq_scans" in stats, stats)
check("pg statistics: no Oracle-only metric", not any(name in stats for name in
      ("created", "last_ddl", "inserts_since_analyzed", "truncated_since_analyzed", "parallel_degree")), stats)
check("pg statistics: average row width from pg_stats", statistics("PG_APP", "sales_dsswork", "SALES_orders")
      ["avg_row_bytes"] > 0)
check("pg statistics: an unlogged table", statistics("PG_APP", "appx", "scratch")["logging"] == "NO")
check("pg statistics: a materialized view",
      statistics("PG_APP", "appx", "mv_totals")["table_kind"] == "MATERIALIZED VIEW")

# =========================================================================================
# Oracle
# =========================================================================================
ora_orders = storage("ORA_ADMIN", "SALES_DSSWORK", "ORDERS")
check("ora storage: the families add up to the total", families_add_up(ora_orders), ora_orders)
check("ora storage: data, LOB segment and LOB index",
      ora_orders["table_segments"] == 1 and ora_orders["lob_segments"] == 2 and ora_orders["lob_mb"] > 20, ora_orders)
check("ora storage: 3 indexes, one owned by another schema", ora_orders["n_indexes"] == 3, ora_orders)
check("ora storage: DATA, INDEX and the other schema's tablespace",
      ora_orders["tablespaces"] == "SALES_DSSWORK_DATA,SALES_DSSWORK_INDEX,USERS", ora_orders)
check("ora storage: 1 LOB column, not compressed", ora_orders["n_lob_columns"] == 1
      and ora_orders["compression"] == "NONE", ora_orders)
check("ora: pg and Oracle give the same storage metrics", set(ora_orders) == set(orders) | {"compression"},
      set(ora_orders) ^ set(orders))

check("ora: an exact mixed-case name", storage("ORA_ADMIN", "SALES_DSSWORK", "Orders")["total_mb"]
      < ora_orders["total_mb"])
check("ora: a name written in lower case is the upper-case table, as Oracle reads unquoted names",
      storage("ORA_ADMIN", "sales_dsswork", "orders") == ora_orders)
check("ora: two names equal ignoring case, none as written nor in upper case, are refused",
      "several objects" in error_of(storage, "ORA_ADMIN", "SALES_DSSWORK", "LINES"))
start = len(harness.QUERIES)
storage("ORA_ADMIN", "SALES_DSSWORK", "ORDERS")
check("ora: the storage reads data_tables, dependents, segments, table; no case-insensitive lookup",
      [name for name in queries_since(start) if name not in ("session", "find")]
      == ["data_tables", "dependents", "segments", "table"], queries_since(start))
check("ora: a private synonym is followed", storage("ORA_ADMIN", "APPX", "ORDERS_SYN") == ora_orders)
check("ora: a public synonym, for a dataset without schema", storage("ORA_ADMIN", None, "ORDERS_PUB") == ora_orders)
check("ora: a view has no storage", "is a VIEW" in error_of(storage, "ORA_ADMIN", "APPX", "V_ORDERS"))

ora_ledger = storage("ORA_ADMIN", "SALES_DSSOUT", "LEDGER")
check("ora storage: composite partitioning", ora_ledger["partitioned"] == "YES" and ora_ledger["n_partitions"] == 2
      and ora_ledger["n_subpartitions"] == 4 and ora_ledger["table_segments"] == 4, ora_ledger)
check("ora storage: compression differs between partitions", ora_ledger["compression"] == "BASIC,NONE", ora_ledger)
check("ora storage: partitioned LOB and local index",
      ora_ledger["lob_segments"] == 8 and ora_ledger["index_segments"] == 4 and ora_ledger["n_indexes"] == 1,
      ora_ledger)
iot = storage("ORA_ADMIN", "SALES_DSSOUT", "IOT_T")
check("ora storage: IOT top index and overflow are table data",
      iot["table_segments"] == 2 and iot["n_indexes"] == 0 and iot["index_mb"] == 0, iot)
docs = storage("ORA_ADMIN", "APPX", "DOCS")
check("ora storage: nested table storage is table data", docs["table_segments"] == 2 and docs["n_indexes"] == 2, docs)
cust = storage("ORA_ADMIN", "APPX", "CUST")
check("ora storage: a clustered table: the cluster and its index are OTHER",
      cust["other_segments"] == 2 and cust["other_mb"] > 0 and cust["table_segments"] == 0, cust)
empty_t = storage("ORA_ADMIN", "SALES_DSSOUT", "EMPTY_T")
check("ora storage: a table without segment: 0 MB, no tablespace, its compression setting",
      empty_t["total_mb"] == 0 and empty_t["total_segments"] == 0 and "tablespaces" not in empty_t
      and empty_t["n_tablespaces"] == 0 and empty_t["compression"] == "NONE", empty_t)
check("ora storage: the restored table keeps its BIN$ index",
      storage("ORA_ADMIN", "SALES_DSSWORK", "T_RESTORE")["n_indexes"] == 1)
check("ora storage: a materialized view", storage("ORA_ADMIN", "SALES_DSSOUT", "MV_TOTALS")["table_segments"] == 1)

# accounts without SELECT_CATALOG_ROLE
own = storage("ORA_APP", None, "APP_ORDERS")
check("ora no grant: the sizes of its own tables", own["table_segments"] == 1 and own["lob_segments"] == 2
      and own["n_indexes"] == 1, own)
check("ora no grant: the sizes of another schema's table are refused, with the grant to ask",
      "SELECT_CATALOG_ROLE" in error_of(storage, "ORA_APP", "SALES_DSSWORK", "ORDERS"))
check("ora no grant, DBA views required: refused with the grant to ask",
      "SELECT_CATALOG_ROLE" in error_of(storage, "ORA_APP", None, "APP_ORDERS", {"oracle_dictionary": "dba"}))
check("ora no grant: read through the admin connection",
      storage("ORA_APP", "SALES_DSSWORK", "ORDERS", {"read_connection": "ORA_ADMIN"}) == ora_orders)

ora_stats = statistics("ORA_ADMIN", "SALES_DSSWORK", "ORDERS")
check("ora statistics: 300 updates and 100 deletes since the analysis",
      ora_stats["dml_since_analyzed"] == 400 and ora_stats["updates_since_analyzed"] == 300
      and ora_stats["deletes_since_analyzed"] == 100 and ora_stats["inserts_since_analyzed"] == 0, ora_stats)
check("ora statistics: 40 % changed: stale", ora_stats["dml_pct_since_analyzed"] == 40.0
      and ora_stats["stale_stats"] == "YES", ora_stats)
check("ora statistics: dates are DSS dates, UTC", all(ISO_UTC.match(ora_stats[name][0]) is not None
      for name in ("last_analyzed", "created", "last_ddl")), ora_stats)
check("ora statistics: no PostgreSQL-only metric", not any(name in ora_stats for name in
      ("live_rows", "dead_rows", "last_vacuum", "seq_scans", "dead_rows_pct")), ora_stats)
check("ora statistics: read without grant through the ALL_ views",
      statistics("ORA_APP", "SALES_DSSWORK", "ORDERS") == ora_stats)
gtt = statistics("ORA_ADMIN", "SALES_DSSOUT", "GTT")
check("ora statistics: a temporary table never analyzed is stale",
      gtt["table_kind"] == "TEMPORARY" and gtt["stale_stats"] == "YES" and "row_estimate" not in gtt, gtt)
kinds = {}
for table in ("LEDGER", "IOT_T", "MV_TOTALS"):
    kinds[table] = statistics("ORA_ADMIN", "SALES_DSSOUT", table)["table_kind"]
kinds["CUST"] = statistics("ORA_ADMIN", "APPX", "CUST")["table_kind"]
check("ora statistics: table kinds", kinds == {"LEDGER": "PARTITIONED", "IOT_T": "INDEX ORGANIZED",
                                               "MV_TOTALS": "MATERIALIZED VIEW", "CUST": "CLUSTERED"}, kinds)

# =========================================================================================
# Metric checkboxes
# =========================================================================================
for engine, connection, schema, table in (("pg", "PG_APP", "fin_dssout", "ledger"),
                                          ("ora", "ORA_ADMIN", "SALES_DSSOUT", "LEDGER")):
    dataset = FakeDataset(connection, schema, table)
    start = len(harness.QUERIES)
    default = probe("table-storage", dataset, {})
    run = queries_since(start)
    check("%s checkboxes: by default the total size only" % engine, list(default) == ["total_mb"], default)
    check("%s checkboxes: the total size does not read table.sql" % engine, "table" not in run, run)
    start = len(harness.QUERIES)
    structure = probe("table-storage", dataset, {"metric_total_mb": False, "metric_partitioned": True,
                                                 "metric_n_partitions": True})
    run = queries_since(start)
    check("%s checkboxes: the partitioning only, without reading the storage" % engine,
          structure == {"partitioned": "YES", "n_partitions": 2}
          and not any(name in run for name in ("storage", "data_tables", "dependents", "segments")), (structure, run))
    check("%s checkboxes: nothing ticked in the statistics probe by default" % engine,
          "No metric is ticked" in error_of(probe, "table-statistics", dataset, {}))
    check("%s checkboxes: nothing ticked at all" % engine,
          "No metric is ticked" in error_of(probe, "table-storage", dataset, {"metric_total_mb": False}))
    picked = probe("table-statistics", dataset, {"metric_table_kind": True, "metric_row_estimate": True})
    check("%s checkboxes: the statistics ticked only" % engine,
          sorted(picked) == ["row_estimate", "table_kind"], picked)

# =========================================================================================
# Both engines
# =========================================================================================
for engine, connection in (("postgresql", "PG_APP"), ("oracle", "ORA_ADMIN")):
    executor = dataiku.SQLExecutor2(connection=connection)
    tagged = database.Database(engine, executor, connection)
    tag = database.SESSION_TAG[engine] % "storage"
    if engine == "oracle":
        sql = "SELECT module, action FROM v$session WHERE sid = SYS_CONTEXT('USERENV', 'SID')"
        expected = [["DSS_TABLE_PROBE", "storage"]]
    else:
        sql = "SELECT current_setting('application_name') AS app"
        expected = [["dss table probe storage"]]
    seen = executor.query_to_df(sql, pre_queries=[tag]).values.tolist()
    check("%s: sessions tagged for the DBAs" % engine, seen == expected, seen)

column_lists = {}
for engine, connection in (("postgresql", "PG_APP"), ("oracle", "ORA_ADMIN")):
    located_db = database.Database(engine, dataiku.SQLExecutor2(connection=connection), connection, "dba")
    if engine == "postgresql":
        values = {"table_oid": "(SELECT c.oid FROM pg_class c WHERE c.relname = 'SALES_orders')",
                  "schema": "'sales_dsswork'", "table": "'SALES_orders'", "quoted_table": "'\"SALES_orders\"'"}
    else:
        values = {"owner": "'SALES_DSSWORK'", "table": "'ORDERS'", "schema": "'SALES_DSSWORK'",
                  "public_owner": "NULL", "quoted_table": "'\"ORDERS\"'"}
    for name in ("session", "find", "find_ignore_case", "table", "statistics"):
        column_lists[(engine, name)] = list(located_db.query(name, values).columns)
for name in ("session", "find", "find_ignore_case", "table", "statistics"):
    check("%s.sql: same columns on both engines, same order" % name,
          column_lists[("postgresql", name)] == column_lists[("oracle", name)],
          (column_lists[("postgresql", name)], column_lists[("oracle", name)]))

finish()
