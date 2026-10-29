"""Custom probe "Table storage" of the dss-table-probe plugin.

Space taken by the table of an Oracle or PostgreSQL dataset, by family of objects: table
data, indexes, LOB (TOAST on PostgreSQL) and other. The metrics are described in
python-lib/tableprobes/storage.py and in the plugin README.
"""
from tableprobes import storage


def process(dataset, partition_id):
    """Storage metrics of the dataset's table.

    dataset       the dataiku.Dataset the probe runs on
    partition_id  "ALL", or the partition the metrics are computed for. Every partition of
                  a SQL dataset lives in the same table: the metrics always describe the
                  whole table
    config        (global, filled by DSS) the probe settings of probe.json
    """
    return storage.compute(dataset, config)  # noqa: F821
