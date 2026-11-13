# 0005: PostgreSQL, not a time-series database (yet)

**Status:** accepted (stage 1, revisited in stage 7)

## Options

1. **PostgreSQL** with a `(machine_id, cycle)` primary key and typed columns.
2. **TimescaleDB** (PostgreSQL extension: hypertables, automatic time partitioning, compression).
3. **A purpose-built TSDB** (InfluxDB, or a Gorilla-style in-memory store in front of cold storage).

## What Gorilla teaches (Pelkonen et al., VLDB 2015)

Facebook's monitoring store keeps the last 26 hours in memory because almost every query is
"recent data for one series", and compresses timestamps (delta-of-delta) and values (XOR of
consecutive floats) to about 1.37 bytes per point, so 2 billion series fit in RAM. The lesson is
not "use a TSDB"; it is: know the access pattern, keep the hot window close, and compress along
the time axis where consecutive values are nearly equal.

## Decision

Option 1 now, with the data model laid out so option 2 is a one-line change
(`SELECT create_hypertable('readings', 'recorded_at')`) when it is needed.

## Why

- The hot window is tiny and already in memory: the last 30 readings per machine live in Redis,
  and the live dashboard reads from there and from the SSE stream, not from the readings table.
- The relational parts (machines, alerts with open/closed/acknowledged state, joins between
  scores and alerts) are a poor fit for a pure TSDB and a natural fit for PostgreSQL.
- The volume does not justify it. FD001 is 20 631 rows. Even 10 000 machines at one reading per
  minute is 14 million rows a day, which PostgreSQL handles on one node with partitioning.
- One database means one backup, one migration tool (Flyway), one set of tests.

## When to switch

- Retention by time (drop everything older than N days) becomes a requirement: partition by
  `recorded_at` (native or Timescale) so old data is dropped, not deleted.
- The readings table stops fitting in memory and most queries are time-range scans over many
  machines: Timescale compression (which uses Gorilla-style per-column compression) gives 10 to
  20x and keeps SQL.
- Query shapes become "aggregate one sensor across thousands of machines per minute": that is a
  columnar workload; Timescale's compressed chunks or a columnar store beat row storage.

## Stretch feature noted, not built

Gorilla's XOR float compression would apply well to C-MAPSS sensors: consecutive readings of the
same sensor share most of their bits.
