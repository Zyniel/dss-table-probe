"""The metrics of each probe, as the user ticks them in the probe settings.

Each metric is a checkbox of probe.json named "metric_<name>". Only the total size is
ticked by default. tests/test_units.py checks that both probe.json files list exactly
these metrics, with these defaults.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class Metric:
    """One metric of a probe.

    name         name of the metric in DSS
    label        label of its checkbox
    description  help text of its checkbox
    default      ticked by default
    """

    name: str
    label: str
    description: str
    default: bool = False


# --- Table storage -----------------------------------------------------------------------
STORAGE_SIZES = (
    Metric("total_mb", "Total size (MB)", "total_mb: all the table's objects: data, indexes, LOB, other",
           default=True),
    Metric("table_mb", "Table data size (MB)", "table_mb: the table or its partitions"),
    Metric("index_mb", "Index size (MB)", "index_mb: the table's indexes"),
    Metric("lob_mb", "LOB size (MB)", "lob_mb: Oracle LOB segments and their indexes, PostgreSQL TOAST"),
    Metric("other_mb", "Other size (MB)", "other_mb: Oracle cluster, PostgreSQL sequences of the table's columns"),
)
STORAGE_SEGMENTS = (
    Metric("total_segments", "Storage units", "total_segments: Oracle segments, PostgreSQL relations"),
    Metric("table_segments", "Table data storage units", "table_segments: one per partition holding data"),
    Metric("index_segments", "Index storage units", "index_segments"),
    Metric("lob_segments", "LOB storage units", "lob_segments"),
    Metric("other_segments", "Other storage units", "other_segments"),
)
STORAGE_STRUCTURE = (
    Metric("n_indexes", "Indexes", "n_indexes: indexes of the table"),
    Metric("n_lob_columns", "LOB columns",
           "n_lob_columns: Oracle LOB columns, PostgreSQL columns that can go out of line (text, bytea, jsonb...)"),
    Metric("partitioned", "Partitioned", "partitioned: YES or NO"),
    Metric("n_partitions", "Partitions", "n_partitions"),
    Metric("n_subpartitions", "Subpartitions", "n_subpartitions"),
    Metric("n_tablespaces", "Tablespaces", "n_tablespaces: tablespaces holding the table's objects"),
    Metric("tablespaces", "Tablespace names", "tablespaces: comma separated"),
    Metric("compression", "Compression (Oracle)",
           "compression: NONE, BASIC, ADVANCED, QUERY LOW/HIGH, ARCHIVE LOW/HIGH (Exadata HCC)..."),
)
STORAGE_GROUPS: Tuple[Tuple[str, Tuple[Metric, ...]], ...] = (
    ("Sizes", STORAGE_SIZES),
    ("Storage units", STORAGE_SEGMENTS),
    ("Structure", STORAGE_STRUCTURE),
)

# Metrics read from table.sql; the others come from the table's objects and their storage
TABLE_QUERY_METRICS = ("n_lob_columns", "partitioned", "n_partitions", "n_subpartitions", "compression")

# --- Table statistics --------------------------------------------------------------------
STATISTICS_COMMON = (
    Metric("table_kind", "Table kind", "table_kind: HEAP, PARTITIONED, INDEX ORGANIZED, TEMPORARY..."),
    Metric("row_estimate", "Rows at the last analysis", "row_estimate: from the optimizer statistics"),
    Metric("avg_row_bytes", "Average row length (bytes)", "avg_row_bytes"),
    Metric("last_analyzed", "Last analysis", "last_analyzed: date of the last statistics gathering"),
    Metric("days_since_analyzed", "Days since the last analysis", "days_since_analyzed"),
    Metric("dml_since_analyzed", "Rows changed since the analysis", "dml_since_analyzed: inserted, updated, deleted"),
    Metric("dml_pct_since_analyzed", "% of rows changed since the analysis", "dml_pct_since_analyzed"),
    Metric("stale_stats", "Stale statistics", "stale_stats: YES or NO, from the threshold below"),
    Metric("logging", "Logging", "logging: YES or NO (PostgreSQL: NO for an unlogged table)"),
)
STATISTICS_ORACLE = (
    Metric("inserts_since_analyzed", "Rows inserted since the analysis", "inserts_since_analyzed"),
    Metric("updates_since_analyzed", "Rows updated since the analysis", "updates_since_analyzed"),
    Metric("deletes_since_analyzed", "Rows deleted since the analysis", "deletes_since_analyzed"),
    Metric("truncated_since_analyzed", "Truncated since the analysis", "truncated_since_analyzed: YES or NO"),
    Metric("created", "Created", "created: creation date of the table"),
    Metric("last_ddl", "Last DDL", "last_ddl: date of the last DDL on the table"),
    Metric("days_since_ddl", "Days since the last DDL", "days_since_ddl"),
    Metric("parallel_degree", "Parallel degree", "parallel_degree"),
)
STATISTICS_POSTGRESQL = (
    Metric("live_rows", "Live rows", "live_rows"),
    Metric("dead_rows", "Dead rows", "dead_rows"),
    Metric("dead_rows_pct", "% of dead rows", "dead_rows_pct"),
    Metric("last_vacuum", "Last vacuum", "last_vacuum: date of the latest vacuum"),
    Metric("days_since_vacuum", "Days since the last vacuum", "days_since_vacuum"),
    Metric("seq_scans", "Sequential scans", "seq_scans: since the statistics counters were reset"),
    Metric("index_scans", "Index scans", "index_scans: since the statistics counters were reset"),
)
STATISTICS_GROUPS: Tuple[Tuple[str, Tuple[Metric, ...]], ...] = (
    ("Statistics", STATISTICS_COMMON),
    ("Oracle only", STATISTICS_ORACLE),
    ("PostgreSQL only", STATISTICS_POSTGRESQL),
)


def all_metrics(groups: Tuple[Tuple[str, Tuple[Metric, ...]], ...]) -> List[Metric]:
    """The metrics of a probe, in the order of its form."""
    metrics = []
    for _group_label, group_metrics in groups:
        for metric in group_metrics:
            metrics.append(metric)
    return metrics


def ticked_metrics(config: Dict[str, Any], groups: Tuple[Tuple[str, Tuple[Metric, ...]], ...]) -> List[str]:
    """Names of the metrics ticked in the probe settings. A checkbox missing from config (a
    probe set up before the metric existed) takes its default. Raises an error when none is
    ticked."""
    ticked = []
    for metric in all_metrics(groups):
        value = config.get("metric_" + metric.name)
        if value is None:
            value = metric.default
        if value:
            ticked.append(metric.name)

    if not ticked:
        raise ValueError("No metric is ticked in the probe settings: tick at least one")
    return ticked
