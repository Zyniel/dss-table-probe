"""Shared code of the dss-table-probe plugin: metrics on the table behind an Oracle or
PostgreSQL dataset.

location.py    where the dataset's table is, as the database knows it
database.py    runs the SQL files of sql/<engine>/ through a DSS connection
storage.py     the "Table storage" probe: space by family of objects
statistics.py  the "Table statistics" probe: optimizer statistics and activity
metrics.py     values as DSS stores metrics
settings.py    the settings of a probe
"""
