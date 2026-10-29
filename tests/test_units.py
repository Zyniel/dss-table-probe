"""Checks that need no database: settings, name matching, staleness, metric values, SQL files.

    python tests/test_units.py
"""
import os
import re

import harness
from harness import check, finish

harness.install_fake_dataiku()

from tableprobes import database, location, metrics, settings, statistics, storage  # noqa: E402

# --- settings ------------------------------------------------------------------------------
default = settings.read_settings({})
check("settings: defaults", default.read_connection is None and default.oracle_dictionary == "auto"
      and default.stale_pct == 10.0, default)
given = settings.read_settings({"read_connection": "ADMIN", "oracle_dictionary": "dba", "stale_pct": "5"})
check("settings: values given", given.read_connection == "ADMIN" and given.oracle_dictionary == "dba"
      and given.stale_pct == 5.0, given)
check("settings: empty connection = the dataset's", settings.read_settings({"read_connection": ""}).read_connection
      is None)
for wrong in ({"oracle_dictionary": "all"}, {"stale_pct": 0}):
    try:
        settings.read_settings(wrong)
        check("settings: %s rejected" % wrong, False)
    except ValueError:
        check("settings: %s rejected" % wrong, True)

# --- name matching -------------------------------------------------------------------------


def candidate(schema_name, table_name, kind="TABLE"):
    return {"schema_name": schema_name, "table_name": table_name, "kind": kind}


both_cases = [candidate("S", "ORDERS"), candidate("S", "Orders")]
check("match: exact name first", location.best_matches(both_cases, "S", "Orders") == [both_cases[1]])
check("match: ignoring case when nothing is exact",
      len(location.best_matches(both_cases, "S", "orders")) == 2)
check("match: the exact table name when only the schema differs in case",
      location.best_matches(both_cases, "s", "Orders") == [both_cases[1]])
with_public = [candidate("PUBLIC", "ORDERS", "SYNONYM"), candidate("APPX", "orders")]
check("match: the schema's object before a public synonym, even ignoring case",
      location.best_matches(with_public, "APPX", "ORDERS") == [with_public[1]])
check("match: a public synonym when the schema has nothing",
      location.best_matches([with_public[0]], "APPX", "ORDERS") == [with_public[0]])
check("match: nothing", location.best_matches([], "S", "T") == [])
mview = [candidate("S", "MV", "MATERIALIZED VIEW"), candidate("S", "MV", "TABLE")]
check("match: a materialized view is read through its table", location.first_by_kind(mview)["kind"] == "TABLE")

placeholders = location.table_placeholders(location.Table("O'NEIL", "T", "TABLE", None))
check("placeholders: quotes doubled, no oid on Oracle",
      placeholders == {"owner": "'O''NEIL'", "table": "'T'", "table_oid": "NULL"}, placeholders)
check("placeholders: PostgreSQL oid", location.table_placeholders(location.Table("s", "t", "TABLE", 16398))
      ["table_oid"] == "16398")

# --- the dataset's table -------------------------------------------------------------------


def dataset_error(dataset):
    try:
        location.dataset_table(dataset)
        return ""
    except ValueError as error:
        return str(error)


check("dataset: not SQL", "not a SQL dataset" in dataset_error(
    harness.FakeDataset("PG_APP", None, None, location_type="FS")))
check("dataset: SQL query dataset", "no table" in dataset_error(harness.FakeDataset("PG_APP", "s", None)))
check("dataset: other database", "is on MySQL" in dataset_error(
    harness.FakeDataset("PG_APP", "s", "t", database_type="MySQL")))
check("dataset: variable not resolved", "not resolved" in dataset_error(
    harness.FakeDataset("PG_APP", "${projectKey}", "t")))
written = location.dataset_table(harness.FakeDataset("ORA_APP", "", "T"))
check("dataset: empty schema = no schema", written.schema is None and written.engine == "oracle", written)

# --- staleness and percentages -------------------------------------------------------------
check("dml %: share of the rows", statistics.dml_percent(1000, 400) == 40.0)
check("dml %: analyzed empty then written", statistics.dml_percent(0, 5) == 100.0)
check("dml %: nothing written", statistics.dml_percent(0, 0) == 0.0)
check("dml %: unknown", statistics.dml_percent(1000, None) is None)
a_date = ("2026-10-28T09:00:00.000Z", "DATE")
check("stale: never analyzed", statistics.stale_flag(None, None, None, 10) == "YES")
check("stale: truncated since", statistics.stale_flag(a_date, 0.0, "YES", 10) == "YES")
check("stale: at the threshold", statistics.stale_flag(a_date, 10.0, "NO", 10) == "YES")
check("stale: below", statistics.stale_flag(a_date, 9.99, "NO", 10) == "NO")
check("stale: changes unknown", statistics.stale_flag(a_date, None, None, 10) is None)
check("dead rows %", statistics.dead_rows_percent(900, 100) == 10.0
      and statistics.dead_rows_percent(0, 0) == 0.0 and statistics.dead_rows_percent(None, 1) is None)

# --- metric values -------------------------------------------------------------------------
check("value: NaN is missing", metrics.as_int(float("nan")) is None and metrics.as_text(float("nan")) is None)
check("value: float read as int", metrics.as_int(1000.0) == 1000 and isinstance(metrics.as_int(1000.0), int))
check("value: empty text is missing", metrics.as_text("  ") is None)
check("value: date", metrics.as_date("2026-10-28T09:00:00.000Z") == ("2026-10-28T09:00:00.000Z", "DATE"))
check("value: missing metrics dropped", metrics.without_missing({"a": 0, "b": None, "c": "NO"}) == {"a": 0, "c": "NO"})
check("distinct values: lists split, sorted, empty left out",
      storage.distinct_values(["NONE", "BASIC,NONE", None, float("nan"), ""]) == ["BASIC", "NONE"])

# --- SQL files -----------------------------------------------------------------------------
names = sorted(os.listdir(os.path.join(database.SQL_DIR, "oracle")))
check("SQL: the same files on both engines",
      names == sorted(os.listdir(os.path.join(database.SQL_DIR, "postgresql"))), names)
for name in names:
    path = os.path.join(database.SQL_DIR, "oracle", name)
    with open(path, encoding="utf-8") as sql_file:
        text = sql_file.read()
    statement = database.read_sql("oracle", name[:-4])
    check("oracle/%s keeps SQL*Plus rules: no blank line in the statement, no &" % name,
          "\n\n" not in statement and "&" not in statement)
    check("oracle/%s: sent without comments nor final ;" % name,
          not statement.rstrip().endswith(";") and "\n--" not in "\n" + statement)
    placeholders_used = set(re.findall(r"{{(\w+)}}", statement))
    known = {"owner", "table", "table_oid", "schema", "public_owner", "quoted_table"}
    known.update(database.ORACLE_VIEWS["dba"])
    check("oracle/%s: every placeholder is known" % name, placeholders_used <= known, placeholders_used - known)
check("Oracle views: the same names in both modes",
      set(database.ORACLE_VIEWS["dba"]) == set(database.ORACLE_VIEWS["user"]))
try:
    database.fill_placeholders("SELECT {{a}} FROM {{b}}", {"a": "1"})
    check("placeholder left: rejected", False)
except ValueError as error:
    check("placeholder left: rejected", "{{b}}" in str(error), error)

finish()
