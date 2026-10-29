"""The "Table storage" probe: the space the dataset's table takes in its database, by
family of objects.

Families (column "family" of sql/<engine>/storage.sql):
  TABLE  table data: the table or its partitions; Oracle: also the IOT top index and
         overflow, nested table storage
  INDEX  indexes of the table, also those owned by another schema
  LOB    Oracle LOB segments and their indexes; PostgreSQL TOAST tables and their indexes
  OTHER  Oracle: the cluster of a clustered table and its index; PostgreSQL: sequences
         owned by the table's columns (serial, identity)

Metrics, in this order:
  total_mb, table_mb, index_mb, lob_mb, other_mb
      allocated space in MB (1 MB = 1,048,576 bytes); the four families add up to total_mb
  total_segments, table_segments, index_segments, lob_segments, other_segments
      storage units: Oracle segments (one per partition), PostgreSQL relations
  n_indexes, n_lob_columns, partitioned, n_partitions, n_subpartitions
  n_tablespaces, tablespaces (comma separated)
  compression  Oracle only: compression of the data, comma separated when partitions differ
"""
from typing import Any, Dict, List

import pandas as pd

from tableprobes.location import LocatedTable, locate, table_placeholders
from tableprobes.metrics import as_int, as_text, is_missing, without_missing
from tableprobes.settings import read_settings

FAMILIES = ("TABLE", "INDEX", "LOB", "OTHER")

# Kinds of table that have storage of their own
STORAGE_KINDS = ("TABLE", "PARTITIONED TABLE", "MATERIALIZED VIEW")

BYTES_PER_MB = 1048576


def compute(dataset: Any, config: Dict[str, Any]) -> Dict[str, Any]:
    """Storage metrics of the dataset's table. config: the probe settings given by DSS."""
    settings = read_settings(config)
    located = locate(dataset, settings)
    check_readable(located)

    placeholders = table_placeholders(located.table)
    objects = located.database.query("storage", placeholders)
    attributes = located.database.query("table", placeholders)
    if len(attributes) == 0:
        raise LookupError("Table %s disappeared while the probe was reading it" % located.table.full_name())

    metrics = storage_metrics(objects, attributes.iloc[0].to_dict())
    return without_missing(metrics)


def check_readable(located: LocatedTable) -> None:
    """Raises an error when the table has no storage of its own, or when the connection
    cannot read its sizes."""
    table = located.table
    if table.kind not in STORAGE_KINDS:
        raise ValueError("%s is a %s: it has no storage of its own" % (table.full_name(), table.kind))

    # Without the DBA_ views, Oracle only shows the segments of the login user
    database = located.database
    if database.engine == "oracle" and database.oracle_views == "user" and table.schema != located.login_user:
        raise PermissionError("The sizes of %s cannot be read: connection %s logs in as %s, which may only read "
                              "the sizes of its own tables. Grant SELECT_CATALOG_ROLE (or SELECT ANY DICTIONARY) "
                              "to %s, or choose a connection with this grant in the probe settings"
                              % (table.full_name(), database.label, located.login_user, located.login_user))


def storage_metrics(objects: pd.DataFrame, attributes: Dict[str, Any]) -> Dict[str, Any]:
    """The metrics from the rows of storage.sql (one per object and tablespace) and the
    row of table.sql."""
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
    metrics["n_lob_columns"] = as_int(attributes["n_lob_columns"])
    metrics["partitioned"] = as_text(attributes["partitioned"])
    metrics["n_partitions"] = as_int(attributes["n_partitions"])
    metrics["n_subpartitions"] = as_int(attributes["n_subpartitions"])

    tablespaces = distinct_values(objects["tablespace_name"].tolist())
    metrics["n_tablespaces"] = len(tablespaces)
    metrics["tablespaces"] = join_or_none(tablespaces)

    data_rows = objects[objects["family"] == "TABLE"]
    compressions = distinct_values(data_rows["compression"].tolist())
    metrics["compression"] = join_or_none(compressions)

    return metrics


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
