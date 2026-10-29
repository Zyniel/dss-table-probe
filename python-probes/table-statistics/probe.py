"""Custom probe "Table statistics" of the dss-table-probe plugin.

Optimizer statistics, lifecycle and activity of the table of an Oracle or PostgreSQL
dataset. The metrics are described in python-lib/tableprobes/statistics.py and in the
plugin README.
"""
from tableprobes import statistics


def process(dataset, partition_id):
    """Statistics metrics of the dataset's table.

    dataset       the dataiku.Dataset the probe runs on
    partition_id  "ALL", or the partition the metrics are computed for. Every partition of
                  a SQL dataset lives in the same table: the metrics always describe the
                  whole table
    config        (global, filled by DSS) the probe settings of probe.json
    """
    return statistics.compute(dataset, config)  # noqa: F821
