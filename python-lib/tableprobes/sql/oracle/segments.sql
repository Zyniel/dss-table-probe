-- =============================================================================
-- segments.sql (Oracle)
-- Storage probe, step 3 of 3: the segments of the table's objects (data tables, clusters,
-- indexes, LOBs): one row per segment (each partition and subpartition has its own).
-- The probe sums them per object and tablespace.
-- {{segment_filter}} names the objects as literals, one condition per owner:
--   (s.owner = 'SALES' AND s.segment_name IN ('ORDERS', 'ORDERS_PK', 'SYS_LOB0000073399C00002$$'))
-- so the dictionary is read by its indexes. Live segments only: a table dropped to the
-- recycle bin has another name.
-- -----------------------------------------------------------------------------
-- segment_type    TABLE, TABLE PARTITION, INDEX SUBPARTITION, LOBSEGMENT, CLUSTER...
-- bytes           allocated space (Exadata HCC: compressed)
-- Placeholders: {{segment_filter}}; dictionary view {{segments}}
-- =============================================================================
SELECT s.owner,
       s.segment_name,
       s.segment_type,
       s.tablespace_name,
       s.bytes
FROM   {{segments}} s
WHERE  {{segment_filter}};
