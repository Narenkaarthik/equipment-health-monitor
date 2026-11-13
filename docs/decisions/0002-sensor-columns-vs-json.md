# 0002: Sensor values as columns, not JSON

**Status:** accepted (stage 1)

## Options

1. **One typed column per sensor** (`s1 .. s21 DOUBLE PRECISION`).
2. **One `JSONB` column** holding `{"s1": ..., "s21": ...}`.
3. **Long format**: one row per (machine, cycle, sensor, value).

## Decision

Option 1. The fleet has a fixed, known sensor set (C-MAPSS has exactly 21), so the schema does not
need to be flexible; it needs to be compact, typed and fast to insert and scan.

## Why

- A row is about 200 bytes with typed columns; the same reading as JSONB is 400 to 500 bytes
  because every key is stored in every row. At 20 631 readings this is irrelevant; at 10 000
  machines it is the difference between the table fitting in cache or not.
- Typed columns let PostgreSQL validate `NOT NULL` and numeric type at insert; JSON would push
  that validation into application code only.
- Any sensor can be selected, filtered and aggregated with plain SQL and a planner that knows the
  column statistics. `jsonb_path` queries work, but they cannot use per-key statistics.
- Batch inserts are one prepared statement with 27 parameters; no serialisation step.
- Long format (option 3) multiplies rows by 21 and makes "all sensors of one cycle" a pivot.

## What we gave up

Adding a sensor is a migration, not a config change. If the fleet were heterogeneous (different
machines with different sensors) option 2 would win, possibly with the frequently queried sensors
promoted to columns.

## Indexes

The primary key `(machine_id, cycle)` is the only index on `readings` so far. It serves the two
queries the system makes: "latest W cycles of machine X" and "machine X between cycles a and b".
`health_scores` and `alerts` get `(machine_id, cycle)` and a partial index on open alerts
(`WHERE closed_at IS NULL`). Each index is added only once a query that needs it exists, and the
load-test report records what each one changed.

## When to partition `readings` by time

Not yet. Partitioning pays off when (a) old data is dropped by range (dropping a partition is
instant, deleting rows is not), or (b) the table no longer fits in memory and most queries touch a
recent range. Rule of thumb for this service: partition monthly once the table passes about
100 million rows or once a retention policy exists, whichever comes first.
