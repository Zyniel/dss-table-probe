"""The "Table storage" probe: the space the dataset's table takes in its database, by
family of objects, and its structure.

Families of objects:
  TABLE  table data: the table or its partitions; Oracle: also the IOT top index and
         overflow, nested table storage
  INDEX  indexes of the table, also those owned by another schema
  LOB    Oracle LOB segments and their indexes; PostgreSQL TOAST tables and their indexes
  OTHER  Oracle: the cluster of a clustered table and its index; PostgreSQL: sequences
         owned by the table's columns (serial, identity)

The metrics are listed in catalog.py; only the ticked ones are returned, and only the
queries they need are run:
  sizes, storage units, indexes, tablespaces  the table's objects: on PostgreSQL storage.sql;
                                              on Oracle data_tables.sql, dependents.sql, then
                                              segments.sql, each naming the objects as
                                              literals so the dictionary is read by its indexes
  LOB columns, partitioning, compression      table.sql
"""
from typing import Any, Dict, List

import pandas as pd

from tableprobes import catalog
from tableprobes.database import sql_literal
from tableprobes.location import LocatedTable, locate, table_placeholders
from tableprobes.metrics import as_int, as_text, is_missing, keep_ticked, without_missing
from tableprobes.settings import read_settings

FAMILIES = ("TABLE", "INDEX", "LOB", "OTHER")

# Kinds of table that have storage of their own
STORAGE_KINDS = ("TABLE", "PARTITIONED TABLE", "MATERIALIZED VIEW")

BYTES_PER_MB = 1048576

# Oracle: segment_type of DBA_SEGMENTS -> kind of segment holding an object (storage_class)
SEGMENT_CLASSES = {
    "TABLE": "TABLE",
    "TABLE PARTITION": "TABLE",
    "TABLE SUBPARTITION": "TABLE",
    "NESTED TABLE": "TABLE",
    "INDEX": "INDEX",
    "INDEX PARTITION": "INDEX",
    "INDEX SUBPARTITION": "INDEX",
    "LOBSEGMENT": "LOBSEGMENT",
    "LOB PARTITION": "LOBSEGMENT",
    "LOB SUBPARTITION": "LOBSEGMENT",
    "LOBINDEX": "LOBINDEX",
    "CLUSTER": "CLUSTER",
}

# Oracle accepts at most 1000 values in an IN list
MAX_IN_LIST = 1000

# Oracle: an object of the table, before its segments are read
PART_COLUMNS = ["object_owner", "object_name", "family", "storage_class"]

OBJECT_COLUMNS = ["family", "storage_class", "object_owner", "object_name", "tablespace_name",
                  "n_segments", "size_bytes"]


def compute(dataset: Any, config: Dict[str, Any]) -> Dict[str, Any]:
    """The ticked storage metrics of the dataset's table. config: the probe settings given
    by DSS."""
    settings = read_settings(config)
    ticked = catalog.ticked_metrics(config, catalog.STORAGE_GROUPS)
    located = locate(dataset, settings)

    table = located.table
    if table.kind not in STORAGE_KINDS:
        raise ValueError("%s is a %s: it has no storage of its own" % (table.full_name(), table.kind))

    needs_objects = False
    needs_attributes = False
    for name in ticked:
        if name in catalog.TABLE_QUERY_METRICS:
            needs_attributes = True
        else:
            needs_objects = True

    metrics: Dict[str, Any] = {}
    if needs_objects:
        check_sizes_readable(located)
        objects = read_objects(located)
        metrics.update(object_metrics(objects))
    if needs_attributes:
        attributes = located.database.query("table", table_placeholders(table))
        if len(attributes) == 0:
            raise LookupError("Table %s disappeared while the probe was reading it" % table.full_name())
        metrics.update(attribute_metrics(attributes.iloc[0].to_dict()))

    return without_missing(keep_ticked(metrics, ticked))


def check_sizes_readable(located: LocatedTable) -> None:
    """Raises an error when the connection cannot read the sizes of the table."""
    # Without the DBA_ views, Oracle only shows the segments of the login user
    database = located.database
    table = located.table
    if database.engine == "oracle" and database.oracle_views == "user" and table.schema != located.login_user:
        raise PermissionError("The sizes of %s cannot be read: connection %s logs in as %s, which may only read "
                              "the sizes of its own tables. Grant SELECT_CATALOG_ROLE (or SELECT ANY DICTIONARY) "
                              "to %s, or choose a connection with this grant in the probe settings"
                              % (table.full_name(), database.label, located.login_user, located.login_user))


def read_objects(located: LocatedTable) -> pd.DataFrame:
    """One row per object of the table and tablespace (OBJECT_COLUMNS)."""
    database = located.database
    placeholders = table_placeholders(located.table)

    if database.engine == "postgresql":
        return database.query("storage", placeholders)

    # Oracle, each step naming as literals what the previous one found
    data_tables = database.query("data_tables", placeholders)
    if len(data_tables) == 0:
        raise LookupError("Table %s disappeared while the probe was reading it" % located.table.full_name())
    parts = oracle_table_parts(data_tables)

    dependents = database.query("dependents", {
        "owner": placeholders["owner"],
        "table_names": literal_list(data_tables["table_name"].tolist()),
        "cluster_filter": oracle_cluster_filter(data_tables),
    })
    if len(dependents) > 0:
        parts = pd.concat([parts, dependents[PART_COLUMNS]], ignore_index=True)

    segments = database.query("segments", {"segment_filter": oracle_segment_filter(parts)})
    return oracle_objects(parts, segments)


def oracle_table_parts(data_tables: pd.DataFrame) -> pd.DataFrame:
    """The data tables of data_tables.sql, and the clusters holding them, as objects of the
    table: family TABLE, or OTHER for a cluster (counted whole)."""
    rows = []
    clusters = []
    for data_table in data_tables.itertuples():
        rows.append([data_table.owner, data_table.table_name, "TABLE", "TABLE"])
        if not is_missing(data_table.cluster_name):
            cluster = [data_table.cluster_owner, data_table.cluster_name, "OTHER", "CLUSTER"]
            if cluster not in clusters:
                clusters.append(cluster)
    return pd.DataFrame(rows + clusters, columns=PART_COLUMNS)


def oracle_cluster_filter(data_tables: pd.DataFrame) -> str:
    """The condition of dependents.sql naming the clusters of the data tables as literals,
    1 = 0 when there is none."""
    conditions = []
    for data_table in data_tables.itertuples():
        if is_missing(data_table.cluster_name):
            continue
        condition = "(i.table_owner = %s AND i.table_name = %s)" % (
            sql_literal(str(data_table.cluster_owner)), sql_literal(str(data_table.cluster_name)))
        if condition not in conditions:
            conditions.append(condition)
    if not conditions:
        return "1 = 0"
    return " OR ".join(conditions)


def literal_list(values: List[Any]) -> str:
    """values as a parenthesized list of SQL literals: ('A', 'B')."""
    literals = []
    for value in values:
        literals.append(sql_literal(str(value)))
    return "(" + ", ".join(literals) + ")"


def oracle_segment_filter(parts: pd.DataFrame) -> str:
    """The condition of segments.sql naming the table's objects as literals, one condition
    per owner (and per 1000 names)."""
    names_by_owner: Dict[str, List[str]] = {}
    for part in parts.itertuples():
        owner = str(part.object_owner)
        name = str(part.object_name)
        if owner not in names_by_owner:
            names_by_owner[owner] = []
        if name not in names_by_owner[owner]:
            names_by_owner[owner].append(name)

    conditions = []
    for owner in sorted(names_by_owner):
        names = names_by_owner[owner]
        for start in range(0, len(names), MAX_IN_LIST):
            conditions.append("(s.owner = %s AND s.segment_name IN %s)"
                              % (sql_literal(owner), literal_list(names[start:start + MAX_IN_LIST])))

    if not conditions:
        return "1 = 0"
    return "\n   OR ".join(conditions)


def oracle_objects(parts: pd.DataFrame, segments: pd.DataFrame) -> pd.DataFrame:
    """The table's objects (PART_COLUMNS) with their segments of segments.sql summed per
    object and tablespace. An object without any segment (deferred segment creation, temporary or
    external table) keeps one row, at 0 bytes and 0 segments."""
    # segments by object: (owner, name) -> list of (kind of segment, tablespace, bytes)
    segments_by_object: Dict[Any, List[Any]] = {}
    for segment in segments.itertuples():
        key = (segment.owner, segment.segment_name)
        segment_class = SEGMENT_CLASSES.get(str(segment.segment_type), str(segment.segment_type))
        if key not in segments_by_object:
            segments_by_object[key] = []
        segments_by_object[key].append((segment_class, segment.tablespace_name, float(segment.bytes)))

    rows = []
    for part in parts.itertuples():
        # sums per tablespace of the segments of this object
        bytes_by_tablespace: Dict[Any, float] = {}
        count_by_tablespace: Dict[Any, int] = {}
        for segment_class, tablespace, size in segments_by_object.get((part.object_owner, part.object_name), []):
            # the partitions of a LOB index are INDEX PARTITION segments
            same_kind = segment_class == part.storage_class or (
                part.storage_class == "LOBINDEX" and segment_class == "INDEX")
            if not same_kind:
                continue
            bytes_by_tablespace[tablespace] = bytes_by_tablespace.get(tablespace, 0.0) + size
            count_by_tablespace[tablespace] = count_by_tablespace.get(tablespace, 0) + 1

        if not bytes_by_tablespace:
            rows.append([part.family, part.storage_class, part.object_owner, part.object_name, None, 0, 0.0])
        for tablespace in bytes_by_tablespace:
            rows.append([part.family, part.storage_class, part.object_owner, part.object_name, tablespace,
                         count_by_tablespace[tablespace], bytes_by_tablespace[tablespace]])

    return pd.DataFrame(rows, columns=OBJECT_COLUMNS)


def object_metrics(objects: pd.DataFrame) -> Dict[str, Any]:
    """Sizes, storage units, indexes and tablespaces, from one row per object and
    tablespace."""
    sizes_mb = {}
    segments = {}
    total_bytes = 0.0
    total_segments = 0
    for family in FAMILIES:
        family_rows = objects[objects["family"] == family]
        family_bytes = float(family_rows["size_bytes"].sum())
        family_segments = int(family_rows["n_segments"].sum())

        sizes_mb[family] = round(family_bytes / BYTES_PER_MB, 3)
        segments[family] = family_segments
        total_bytes = total_bytes + family_bytes
        total_segments = total_segments + family_segments

    metrics: Dict[str, Any] = {}
    metrics["total_mb"] = round(total_bytes / BYTES_PER_MB, 3)
    for family in FAMILIES:
        metrics[family.lower() + "_mb"] = sizes_mb[family]

    metrics["total_segments"] = total_segments
    for family in FAMILIES:
        metrics[family.lower() + "_segments"] = segments[family]

    metrics["n_indexes"] = count_indexes(objects)

    tablespaces = distinct_values(objects["tablespace_name"].tolist())
    metrics["n_tablespaces"] = len(tablespaces)
    metrics["tablespaces"] = join_or_none(tablespaces)
    return metrics


def attribute_metrics(attributes: Dict[str, Any]) -> Dict[str, Any]:
    """LOB columns, partitioning and compression, from the row of table.sql."""
    return {
        "n_lob_columns": as_int(attributes["n_lob_columns"]),
        "partitioned": as_text(attributes["partitioned"]),
        "n_partitions": as_int(attributes["n_partitions"]),
        "n_subpartitions": as_int(attributes["n_subpartitions"]),
        "compression": join_or_none(distinct_values([attributes["compression"]])),
    }


def count_indexes(objects: pd.DataFrame) -> int:
    """Indexes of the table: the objects of family INDEX (an index whose partitions sit in
    several tablespaces has several rows, it counts once)."""
    index_rows = objects[objects["family"] == "INDEX"]
    index_names = set()
    for index_row in index_rows.itertuples():
        index_names.add((index_row.object_owner, index_row.object_name))
    return len(index_names)


def distinct_values(values: List[Any]) -> List[str]:
    """The distinct non-empty values, sorted. A value can itself be a list separated by
    commas (Oracle compression of several partitions)."""
    distinct = set()
    for value in values:
        if is_missing(value):
            continue
        for part in str(value).split(","):
            part = part.strip()
            if part != "":
                distinct.add(part)
    return sorted(distinct)


def join_or_none(values: List[str]) -> Any:
    """values separated by commas, None when there is none."""
    if not values:
        return None
    return ",".join(values)
