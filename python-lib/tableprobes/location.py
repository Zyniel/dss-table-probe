"""Where the table of a dataset is.

1. The dataset settings give the engine, the schema and the table (variables resolved).
2. The dataset's connection tells its default schema, when the dataset has none, and which
   database it reaches.
3. The connection that reads the dictionary (the dataset's, or the one chosen in the probe
   settings) must reach the same database.
4. The database gives the table as it knows it: names as written, or as the database
   stores unquoted names (upper case on Oracle, lower case on PostgreSQL); ignoring case
   only when neither exists. Oracle synonyms are followed to their table.
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dataiku import SQLExecutor2

from tableprobes.database import Database, sql_literal
from tableprobes.metrics import as_int, as_text
from tableprobes.settings import ProbeSettings

# databaseType of the dataset location -> engine
DATABASE_TYPES = {"PostgreSQL": "postgresql", "Oracle": "oracle"}

# When one name matches several objects (an Oracle materialized view is also a table),
# the first kind of this list is kept
KIND_ORDER = ("TABLE", "PARTITIONED TABLE", "MATERIALIZED VIEW", "FOREIGN TABLE", "VIEW", "SYNONYM")

# Synonyms followed at most, a synonym pointing to a synonym...
MAX_SYNONYMS = 5

logger = logging.getLogger(__name__)


@dataclass
class DatasetTable:
    """The table a SQL dataset points to, as written in its settings.

    engine  "oracle" or "postgresql"
    schema  None when the dataset has no schema: the connection's default applies
    """

    engine: str
    schema: Optional[str]
    table: str


@dataclass
class Table:
    """A table as the database knows it.

    kind  TABLE, PARTITIONED TABLE, MATERIALIZED VIEW, FOREIGN TABLE or VIEW
    oid   PostgreSQL only: the oid of the relation, the other queries read it by oid
    """

    schema: str
    name: str
    kind: str
    oid: Optional[int]

    def full_name(self) -> str:
        return "%s.%s" % (self.schema, self.name)


@dataclass
class LocatedTable:
    """The database to read and the dataset's table in it.

    login_user  account of the connection that reads the database
    """

    database: Database
    table: Table
    login_user: str


def locate(dataset: Any, settings: ProbeSettings) -> LocatedTable:
    """The database to read and the dataset's table in it (steps 1 to 4 above)."""
    written = dataset_table(dataset)

    dataset_database = Database(written.engine, SQLExecutor2(dataset=dataset),
                                "of dataset %s" % dataset.name, settings.oracle_dictionary)
    dataset_session = session_info(dataset_database, written.table)

    schema = written.schema
    if schema is None:
        schema = dataset_session["table_schema"] or dataset_session["current_schema"]
    if schema is None:
        raise ValueError("Dataset %s has no schema, and its connection has no default schema (search_path): "
                         "write the schema in the dataset settings" % dataset.name)

    if settings.read_connection is None:
        database = dataset_database
        reading_session = dataset_session
    else:
        database = Database(written.engine, SQLExecutor2(connection=settings.read_connection),
                            settings.read_connection, settings.oracle_dictionary)
        reading_session = session_info(database, written.table)
        if reading_session["database_id"] != dataset_session["database_id"]:
            raise ValueError("Connection %s reaches database %s, but the connection of dataset %s reaches "
                             "database %s: choose a connection to the dataset's database in the probe settings"
                             % (settings.read_connection, reading_session["database_id"], dataset.name,
                                dataset_session["database_id"]))

    table = find_table(database, schema, written.table, look_in_public=written.schema is None)
    logger.info("Dataset %s: %s %s, read through connection %s",
                dataset.name, table.kind, table.full_name(), database.label)
    login_user = reading_session["login_user"] or ""
    return LocatedTable(database=database, table=table, login_user=login_user)


def dataset_table(dataset: Any) -> DatasetTable:
    """The table of a dataset, from its settings. Raises an error for anything that is not
    a table of an Oracle or PostgreSQL connection."""
    location = dataset.get_location_info()
    location_type = location.get("locationInfoType")
    info = location.get("info") or {}

    if location_type != "SQL":
        raise ValueError("Dataset %s is not a SQL dataset (location %s): this probe reads Oracle and PostgreSQL "
                         "tables only" % (dataset.name, location_type))

    database_type = info.get("databaseType")
    if not database_type:
        database_type = dataset.get_config().get("type")
    engine = DATABASE_TYPES.get(database_type)
    if engine is None:
        raise ValueError("Dataset %s is on %s: this probe reads Oracle and PostgreSQL tables only"
                         % (dataset.name, database_type))

    table = info.get("table")
    if not table:
        raise ValueError("Dataset %s has no table (a SQL query dataset?): there is no table to measure"
                         % dataset.name)

    schema = info.get("schema") or None

    for value in (schema, table):
        if value is not None and "${" in value:
            raise ValueError("Dataset %s: variable not resolved in %r" % (dataset.name, value))

    return DatasetTable(engine=engine, schema=schema, table=table)


def session_info(database: Database, table: str) -> Dict[str, Optional[str]]:
    """login_user, current_schema, table_schema and database_id of a connection
    (sql/<engine>/session.sql)."""
    quoted_table = '"' + table.replace('"', '""') + '"'
    rows = database.query("session", {"quoted_table": sql_literal(quoted_table)})
    row = rows.iloc[0]

    info = {}
    for column in ("login_user", "current_schema", "table_schema", "database_id"):
        info[column] = as_text(row[column])
    return info


def find_table(database: Database, schema: str, table: str, look_in_public: bool) -> Table:
    """The table as the database knows it (sql/<engine>/find.sql).

    look_in_public  Oracle: also look at the public synonyms, as Oracle does for a name
                    without schema
    """
    for _synonyms_followed in range(MAX_SYNONYMS + 1):
        public_owner = "NULL"
        if look_in_public:
            public_owner = sql_literal("PUBLIC")
        values = {"schema": sql_literal(schema), "table": sql_literal(table), "public_owner": public_owner}

        # Names as written or as the database stores unquoted names: indexed lookups.
        # Ignoring case reads every object of the schema: only when nothing matched.
        candidates = database.query("find", values)
        if len(candidates) == 0:
            candidates = database.query("find_ignore_case", values)

        matches = best_matches(candidates.to_dict("records"), schema, table)
        if not matches:
            raise LookupError("Table %s.%s not found in the database: was the dataset ever built?"
                              % (schema, table))

        names = set()
        for match in matches:
            names.add("%s.%s" % (match["schema_name"], match["table_name"]))
        if len(names) > 1:
            raise LookupError("%s.%s matches several objects when case is ignored (%s): write the exact name "
                              "in the dataset settings" % (schema, table, ", ".join(sorted(names))))

        match = first_by_kind(matches)
        if match["kind"] != "SYNONYM":
            return Table(schema=match["schema_name"], name=match["table_name"], kind=match["kind"],
                         oid=as_int(match["table_oid"]))

        db_link = as_text(match["target_db_link"])
        if db_link is not None:
            raise ValueError("%s.%s is a synonym of a table of database link %s: this probe reads local "
                             "tables only" % (match["schema_name"], match["table_name"], db_link))
        logger.info("%s.%s is a synonym of %s.%s", match["schema_name"], match["table_name"],
                    match["target_schema"], match["target_table"])
        schema = match["target_schema"]
        table = match["target_table"]
        look_in_public = False

    raise LookupError("More than %d synonyms in a row from %s.%s" % (MAX_SYNONYMS, schema, table))


def best_matches(candidates: List[Dict[str, Any]], schema: str, table: str) -> List[Dict[str, Any]]:
    """The candidates that match best: objects of the schema before public synonyms; within
    each, schema and table names written exactly, then the table name exactly, then both
    ignoring case (the candidates all match ignoring case)."""
    for public in (False, True):
        for exact_names in ("schema and table", "table", "none"):
            matches = []
            for candidate in candidates:
                is_public = candidate["schema_name"] == "PUBLIC" and schema.upper() != "PUBLIC"
                if is_public != public:
                    continue
                if exact_names in ("schema and table", "table") and candidate["table_name"] != table:
                    continue
                if exact_names == "schema and table" and candidate["schema_name"] != schema:
                    continue
                matches.append(candidate)
            if matches:
                return matches
    return []


def first_by_kind(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The match whose kind comes first in KIND_ORDER."""
    best = matches[0]
    for match in matches:
        if KIND_ORDER.index(match["kind"]) < KIND_ORDER.index(best["kind"]):
            best = match
    return best


def table_placeholders(table: Table) -> Dict[str, str]:
    """Values of the placeholders that name the table in the SQL files."""
    table_oid = "NULL"
    if table.oid is not None:
        table_oid = str(int(table.oid))
    return {
        "owner": sql_literal(table.schema),
        "table": sql_literal(table.name),
        "table_oid": table_oid,
    }
