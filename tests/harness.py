"""Shared by the tests: a stand-in for the dataiku module that runs the SQL inside the test
containers, a stand-in for a DSS dataset, and a check() that counts failures.

DSS connections of the tests (passwords: test values of the local containers only):

| Connection | Database                    | Account                                     |
|------------|-----------------------------|---------------------------------------------|
| PG_APP     | PostgreSQL appdb            | probe_app: plain role, owner of the tables  |
| PG_ADMIN   | PostgreSQL appdb            | dbmon: pg_monitor                           |
| PG_OTHER   | PostgreSQL otherdb          | probe_app                                   |
| ORA_APP    | Oracle FREEPDB1             | probe_app: no dictionary grant              |
| ORA_ADMIN  | Oracle FREEPDB1             | dbmon: SELECT_CATALOG_ROLE                  |
"""
import io
import os
import subprocess
import sys
import types
from typing import Any, Dict, List, Optional

sys.dont_write_bytecode = True
import pandas as pd  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "python-lib"))

PG_CONTAINER = os.environ.get("PROBES_PG_CONTAINER", "probes-pg")
ORA_CONTAINER = os.environ.get("PROBES_ORA_CONTAINER", "probes-ora")
# Test values of the local containers only
ORACLE_TEST_PASSWORD = "Probe_Test_1"
PG_CONNECTIONS = {
    "PG_APP": ("probe_app", "probe_app", "appdb"),
    "PG_ADMIN": ("dbmon", "dbmon", "appdb"),
    "PG_OTHER": ("probe_app", "probe_app", "otherdb"),
}
ORA_CONNECTIONS = {
    "ORA_APP": "probe_app",
    "ORA_ADMIN": "dbmon",
}

FAILURES: List[str] = []

# every query the stand-in executor ran: (connection, sql, pre_queries)
QUERIES: List[Any] = []


def check(label: str, condition: bool, detail: Any = "") -> None:
    """Print ok or FAIL for one check, with detail when it fails."""
    if condition:
        print("ok    %s" % label)
        return
    print("FAIL  %s  -> %s" % (label, detail))
    FAILURES.append(label)


def finish() -> None:
    """Print the number of failures and exit with 1 when there is any."""
    print("\n%d failure(s)" % len(FAILURES))
    if FAILURES:
        sys.exit(1)
    sys.exit(0)


def psql(user: str, password: str, database: str, script: str) -> subprocess.CompletedProcess:
    """Run a psql script in the PostgreSQL container, CSV output."""
    command = ["docker", "exec", "-i", "-e", "PGPASSWORD=" + password, PG_CONTAINER, "psql", "-X", "-q",
               "-v", "ON_ERROR_STOP=1", "--csv", "-h", "127.0.0.1", "-U", user, "-d", database]
    return subprocess.run(command, input=script, capture_output=True, text=True, encoding="utf-8")


def sqlplus(user: str, script: str) -> subprocess.CompletedProcess:
    """Run a SQL*Plus script in the Oracle container, on FREEPDB1."""
    logon = "%s/%s@//localhost/FREEPDB1" % (user, ORACLE_TEST_PASSWORD)
    command = ["docker", "exec", "-i", ORA_CONTAINER, "sqlplus", "-s", "-L", logon]
    return subprocess.run(command, input=script, capture_output=True, text=True, encoding="utf-8")


class FakeExecutor(object):
    """Stand-in for SQLExecutor2: SQLExecutor2(connection=...) or SQLExecutor2(dataset=...)."""

    def __init__(self, connection: Optional[str] = None, dataset: Any = None):
        if dataset is not None:
            connection = dataset.connection
        if connection not in PG_CONNECTIONS and connection not in ORA_CONNECTIONS:
            raise Exception("Connection %s does not exist" % connection)
        self.connection = connection

    def query_to_df(self, sql: str, pre_queries: Optional[List[str]] = None,
                    infer_from_schema: bool = False) -> pd.DataFrame:
        QUERIES.append((self.connection, sql, pre_queries))
        if self.connection in ORA_CONNECTIONS:
            return self.oracle(sql, pre_queries or [])
        return self.postgresql(sql, pre_queries or [])

    def postgresql(self, sql: str, pre_queries: List[str]) -> pd.DataFrame:
        user, password, database = PG_CONNECTIONS[self.connection]
        script = ""
        for pre_query in pre_queries:
            script = script + pre_query + ";\n"
        script = script + sql + ";\n"
        run = psql(user, password, database, script)
        if run.returncode != 0:
            raise Exception(run.stderr.strip())
        if run.stdout.strip() == "":
            return pd.DataFrame()
        return pd.read_csv(io.StringIO(run.stdout), keep_default_na=True)

    def oracle(self, sql: str, pre_queries: List[str]) -> pd.DataFrame:
        """PL/SQL pre-queries run with a slash, as JDBC runs them as one statement."""
        user = ORA_CONNECTIONS[self.connection]
        script = ("WHENEVER SQLERROR EXIT FAILURE\nSET MARKUP CSV ON\nSET SQLBLANKLINES ON\n"
                  "SET PAGESIZE 50000 FEEDBACK OFF\n")
        for pre_query in pre_queries:
            if pre_query.upper().startswith("BEGIN"):
                script = script + pre_query + "\n/\n"
            else:
                script = script + pre_query + ";\n"
        script = script + sql + ";\nEXIT\n"
        run = sqlplus(user, script)
        if run.returncode != 0:
            raise Exception(run.stdout[-1500:])
        if run.stdout.strip() == "":
            return pd.DataFrame()
        return pd.read_csv(io.StringIO(run.stdout))


class FakeDataset(object):
    """Stand-in for dataiku.Dataset on a SQL table.

    connection  test connection of the dataset (see the table above)
    schema      as in the dataset settings, None when empty
    table       None for a SQL query dataset
    location_type, database_type
                what get_location_info() says
    """

    def __init__(self, connection: str, schema: Optional[str], table: Optional[str],
                 location_type: str = "SQL", database_type: Optional[str] = None):
        self.connection = connection
        self.schema = schema
        self.table = table
        self.location_type = location_type
        if database_type is None:
            database_type = "Oracle" if connection.startswith("ORA") else "PostgreSQL"
        self.database_type = database_type
        self.name = "TESTPROJECT.%s" % (table or "query_dataset")

    def get_location_info(self, sensitive_info: bool = False) -> Dict[str, Any]:
        info: Dict[str, Any] = {"databaseType": self.database_type}
        if self.schema is not None:
            info["schema"] = self.schema
        if self.table is not None:
            info["table"] = self.table
        return {"locationInfoType": self.location_type, "info": info}

    def get_config(self) -> Dict[str, Any]:
        return {"type": self.database_type, "params": {"connection": self.connection}}


class MetricDataTypes(object):
    """Stand-in for dataiku.metric.MetricDataTypes."""
    DATE = "DATE"


def install_fake_dataiku() -> types.ModuleType:
    """Put a stand-in dataiku module (and dataiku.metric) in sys.modules."""
    module = types.ModuleType("dataiku")
    module.SQLExecutor2 = FakeExecutor  # type: ignore[attr-defined]
    metric = types.ModuleType("dataiku.metric")
    metric.MetricDataTypes = MetricDataTypes  # type: ignore[attr-defined]
    module.metric = metric  # type: ignore[attr-defined]
    sys.modules["dataiku"] = module
    sys.modules["dataiku.metric"] = metric
    # forget tableprobes modules imported with a previous stand-in
    for name in list(sys.modules):
        if name == "tableprobes" or name.startswith("tableprobes."):
            del sys.modules[name]
    return module
