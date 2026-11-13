-- Stage 1: raw readings. One row per (machine, cycle); the primary key makes a repeated post a no-op.
-- Sensor values are typed columns, not JSON: the schema is fixed (21 sensors), rows stay compact
-- (~200 bytes), and any sensor can be filtered or aggregated in SQL (see docs/decisions/0002).
CREATE TABLE readings (
    machine_id   INTEGER      NOT NULL REFERENCES machines(id),
    cycle        INTEGER      NOT NULL CHECK (cycle > 0),
    recorded_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    setting_1    DOUBLE PRECISION NOT NULL,
    setting_2    DOUBLE PRECISION NOT NULL,
    setting_3    DOUBLE PRECISION NOT NULL,
    s1  DOUBLE PRECISION NOT NULL,  s2  DOUBLE PRECISION NOT NULL,  s3  DOUBLE PRECISION NOT NULL,
    s4  DOUBLE PRECISION NOT NULL,  s5  DOUBLE PRECISION NOT NULL,  s6  DOUBLE PRECISION NOT NULL,
    s7  DOUBLE PRECISION NOT NULL,  s8  DOUBLE PRECISION NOT NULL,  s9  DOUBLE PRECISION NOT NULL,
    s10 DOUBLE PRECISION NOT NULL,  s11 DOUBLE PRECISION NOT NULL,  s12 DOUBLE PRECISION NOT NULL,
    s13 DOUBLE PRECISION NOT NULL,  s14 DOUBLE PRECISION NOT NULL,  s15 DOUBLE PRECISION NOT NULL,
    s16 DOUBLE PRECISION NOT NULL,  s17 DOUBLE PRECISION NOT NULL,  s18 DOUBLE PRECISION NOT NULL,
    s19 DOUBLE PRECISION NOT NULL,  s20 DOUBLE PRECISION NOT NULL,  s21 DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (machine_id, cycle)
);

-- The primary key index already serves "readings of machine X in cycle order", which is the query the
-- charts make. A time-range index is added only when a time-based query exists (see 0002).
COMMENT ON TABLE readings IS 'Raw sensor readings, one per machine cycle. PK (machine_id, cycle) deduplicates.';
