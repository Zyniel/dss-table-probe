"""Runs the SQL files of sql/<engine>/ on a database, through a DSS connection.

Each SQL file runs as-is in SQL*Plus or psql once its placeholders {{name}} are replaced:
names and values given by the probe (always as SQL literals, see sql_literal), and on
Oracle the dictionary views to read (DBA_ or ALL_/USER_, see ORACLE_VIEWS).
"""
import logging
import os
from typing import Dict

import pandas as pd
from dataiku import SQLExecutor2

ENGINES = ("oracle", "postgresql")

SQL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sql")

# Run before each query, so that DBAs recognise the sessions:
# - Oracle: module DSS_TABLE_PROBE, action = the query (GV$SESSION)
# - PostgreSQL: application_name "dss table probe <query>" (pg_stat_activity)
SESSION_TAG = {
    "oracle": "BEGIN DBMS_APPLICATION_INFO.SET_MODULE(module_name => 'DSS_TABLE_PROBE', "
              "action_name => '%s'); END;",
    "postgresql": "SET application_name = 'dss table probe %s'",
}

# Oracle dictionary views read by the SQL files, by mode (see settings.py)
#   dba   every schema. Needs SELECT_CATALOG_ROLE or SELECT ANY DICTIONARY
#   user  what any login user can read: ALL_ views. Segments only exist in DBA_SEGMENTS
#         and USER_SEGMENTS: the sizes of a table of another schema cannot be read
ORACLE_VIEWS = {
    "dba": {
        "objects": "dba_objects",
        "synonyms": "dba_synonyms",
        "tables": "dba_tables",
        "external_tables": "dba_external_tables",
        "nested_tables": "dba_nested_tables",
        "indexes": "dba_indexes",
        "lobs": "dba_lobs",
        "segments": "dba_segments",
        "tab_partitions": "dba_tab_partitions",
        "tab_subpartitions": "dba_tab_subpartitions",
        "tab_modifications": "dba_tab_modifications",
    },
    "user": {
        "objects": "all_objects",
        "synonyms": "all_synonyms",
        "tables": "all_tables",
        "external_tables": "all_external_tables",
        "nested_tables": "all_nested_tables",
        "indexes": "all_indexes",
        "lobs": "all_lobs",
        "segments": "(SELECT USER AS owner, us.* FROM user_segments us)",
        "tab_partitions": "all_tab_partitions",
        "tab_subpartitions": "all_tab_subpartitions",
        "tab_modifications": "all_tab_modifications",
    },
}

# Oracle errors of a connection that may not read the DBA_ views
ORACLE_MISSING_GRANT_ERRORS = ("ORA-00942", "ORA-01031", "ORA-04043")

logger = logging.getLogger(__name__)


def sql_literal(value: str) -> str:
    """value as a SQL string literal, its quotes doubled. Names from the dataset settings
    are never pasted into the SQL as they are."""
    return "'" + str(value).replace("'", "''") + "'"


def read_sql(engine: str, name: str) -> str:
    """Text of sql/<engine>/<name>.sql as sent to the database: comment lines and the final
    semicolon removed."""
    path = os.path.join(SQL_DIR, engine, name + ".sql")

    kept_lines = []
    with open(path, encoding="utf-8") as sql_file:
        for line in sql_file:
            if line.lstrip().startswith("--"):
                continue
            kept_lines.append(line)

    sql = "".join(kept_lines)
    sql = sql.strip()
    sql = sql.rstrip(";")
    return sql


def fill_placeholders(sql: str, values: Dict[str, str]) -> str:
    """sql with each {{name}} replaced by values[name]. Raises an error when a placeholder
    is left, so a SQL file never reaches the database half filled."""
    for name in values:
        sql = sql.replace("{{" + name + "}}", values[name])

    if "{{" in sql:
        start = sql.index("{{")
        end = sql.index("}}", start) + 2
        raise ValueError("placeholder %s has no value" % sql[start:end])
    return sql


def is_missing_grant(error: Exception) -> bool:
    """True when an Oracle error says the connection may not read a dictionary view."""
    message = str(error)
    for code in ORACLE_MISSING_GRANT_ERRORS:
        if code in message:
            return True
    return False


class Database(object):
    """A database reached through a DSS connection.

    engine      "oracle" or "postgresql"
    executor    SQLExecutor2 of the connection
    label       name of the connection, for the messages
    oracle_dictionary
                "auto", "dba" or "user" (see settings.py). In "auto", the first query
                that fails for a missing grant switches the database to "user" for good
    """

    def __init__(self, engine: str, executor: SQLExecutor2, label: str, oracle_dictionary: str = "auto"):
        if engine not in ENGINES:
            raise ValueError("unknown engine %r, expected one of %s" % (engine, ", ".join(ENGINES)))
        self.engine = engine
        self.executor = executor
        self.label = label
        self.oracle_dictionary = oracle_dictionary
        # views read now: "dba" unless the user asked for "user"
        self.oracle_views = "user" if oracle_dictionary == "user" else "dba"

    def query(self, name: str, values: Dict[str, str]) -> pd.DataFrame:
        """Result of sql/<engine>/<name>.sql with its placeholders filled. Column names are
        in lower case. On Oracle in "auto", a missing grant on the DBA_ views makes the
        query run again on the ALL_/USER_ views."""
        try:
            return self.run(name, values)
        except Exception as error:
            if self.engine != "oracle" or not is_missing_grant(error):
                raise
            can_fall_back = self.oracle_dictionary == "auto" and self.oracle_views == "dba"
            if not can_fall_back:
                raise PermissionError("Connection %s may not read the Oracle dictionary views it needs (%s). "
                                      "Grant SELECT_CATALOG_ROLE (or SELECT ANY DICTIONARY) to its account, or set "
                                      "Oracle dictionary to Automatic in the probe settings"
                                      % (self.label, str(error).splitlines()[0])) from error
            logger.info("Connection %s may not read the DBA_ views (%s): reading the views of "
                        "its login user", self.label, str(error).splitlines()[0])
            self.oracle_views = "user"
            return self.run(name, values)

    def run(self, name: str, values: Dict[str, str]) -> pd.DataFrame:
        """Run one SQL file in a tagged session."""
        all_values = dict(values)
        if self.engine == "oracle":
            all_values.update(ORACLE_VIEWS[self.oracle_views])

        sql = read_sql(self.engine, name)
        sql = fill_placeholders(sql, all_values)
        session_tag = SESSION_TAG[self.engine] % name

        result = self.executor.query_to_df(sql, pre_queries=[session_tag], infer_from_schema=True)

        # Oracle returns upper-case column names, PostgreSQL lower-case ones
        result = result.rename(columns=str.lower)
        return result
