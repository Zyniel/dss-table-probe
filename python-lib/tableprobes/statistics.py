"""The "Table statistics" probe: optimizer statistics, lifecycle and activity of the
dataset's table.

Metrics of both engines:
  table_kind, row_estimate, avg_row_bytes, last_analyzed (date), days_since_analyzed,
  dml_since_analyzed, dml_pct_since_analyzed, stale_stats
Oracle only:
  inserts_since_analyzed, updates_since_analyzed, deletes_since_analyzed,
  truncated_since_analyzed, last_dml (date), created (date), last_ddl (date),
  days_since_ddl, logging, parallel_degree
PostgreSQL only:
  logging (NO for an unlogged table), live_rows, dead_rows, dead_rows_pct,
  last_vacuum (date), days_since_vacuum, seq_scans, index_scans

stale_stats is YES when the statistics were never gathered, when the table was truncated
since (Oracle), or when the rows changed since reach the threshold of the probe settings
(10 % by default, Oracle's default STALE_PERCENT). A metric the database cannot give is
left out rather than stored empty.
"""
from typing import Any, Dict, Optional

from tableprobes.location import locate, table_placeholders
from tableprobes.metrics import as_date, as_float, as_int, as_text, without_missing
from tableprobes.settings import read_settings

# Kinds of table with statistics
STATISTICS_KINDS = ("TABLE", "PARTITIONED TABLE", "MATERIALIZED VIEW", "FOREIGN TABLE")

# How each column of sql/<engine>/statistics.sql becomes a metric, in the order of the file
TEXT_COLUMNS = ("table_kind", "truncated_since_analyzed", "logging", "parallel_degree")
INTEGER_COLUMNS = ("row_estimate", "avg_row_bytes", "dml_since_analyzed", "inserts_since_analyzed",
                   "updates_since_analyzed", "deletes_since_analyzed", "live_rows", "dead_rows",
                   "seq_scans", "index_scans")
DECIMAL_COLUMNS = ("days_since_analyzed", "days_since_ddl", "days_since_vacuum")
DATE_COLUMNS = ("last_analyzed", "last_dml", "created", "last_ddl", "last_vacuum")


def compute(dataset: Any, config: Dict[str, Any]) -> Dict[str, Any]:
    """Statistics metrics of the dataset's table. config: the probe settings given by DSS."""
    settings = read_settings(config)
    located = locate(dataset, settings)

    table = located.table
    if table.kind not in STATISTICS_KINDS:
        raise ValueError("%s is a %s: it has no statistics of its own" % (table.full_name(), table.kind))

    rows = located.database.query("statistics", table_placeholders(table))
    if len(rows) == 0:
        raise LookupError("Table %s disappeared while the probe was reading it" % table.full_name())

    metrics = statistics_metrics(rows.iloc[0].to_dict(), settings.stale_pct)
    return without_missing(metrics)


def statistics_metrics(row: Dict[str, Any], stale_pct: float) -> Dict[str, Any]:
    """The metrics from the row of statistics.sql."""
    metrics: Dict[str, Any] = {}
    for column in row:
        if column in TEXT_COLUMNS:
            metrics[column] = as_text(row[column])
        elif column in INTEGER_COLUMNS:
            metrics[column] = as_int(row[column])
        elif column in DECIMAL_COLUMNS:
            metrics[column] = as_float(row[column])
        elif column in DATE_COLUMNS:
            metrics[column] = as_date(row[column])
        else:
            raise ValueError("statistics.sql returned column %r, unknown to statistics.py" % column)

    dml_pct = dml_percent(metrics["row_estimate"], metrics["dml_since_analyzed"])
    metrics["dml_pct_since_analyzed"] = dml_pct
    metrics["stale_stats"] = stale_flag(metrics["last_analyzed"], dml_pct,
                                        metrics["truncated_since_analyzed"], stale_pct)
    metrics["dead_rows_pct"] = dead_rows_percent(metrics["live_rows"], metrics["dead_rows"])
    return metrics


def dml_percent(row_estimate: Optional[int], dml: Optional[int]) -> Optional[float]:
    """Rows changed since the last analysis, in % of the rows then. A table analyzed empty
    and written since counts as 100 %."""
    if dml is None:
        return None
    if row_estimate is None or row_estimate == 0:
        if dml > 0:
            return 100.0
        return 0.0
    return round(100.0 * dml / row_estimate, 2)


def stale_flag(last_analyzed: Any, dml_pct: Optional[float], truncated: Optional[str],
               stale_pct: float) -> Optional[str]:
    """YES when the statistics are missing or stale, NO when they are fresh, None when the
    database does not tell the changes since the last analysis."""
    if last_analyzed is None:
        return "YES"
    if truncated == "YES":
        return "YES"
    if dml_pct is None:
        return None
    if dml_pct >= stale_pct:
        return "YES"
    return "NO"


def dead_rows_percent(live_rows: Optional[int], dead_rows: Optional[int]) -> Optional[float]:
    """PostgreSQL: dead rows in % of all row versions (live and dead)."""
    if live_rows is None or dead_rows is None:
        return None
    all_rows = live_rows + dead_rows
    if all_rows == 0:
        return 0.0
    return round(100.0 * dead_rows / all_rows, 2)
