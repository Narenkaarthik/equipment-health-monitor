-- Stage 4: alerts. One row per alert episode; an open alert has no closed_at.
CREATE TABLE alerts (
    id               BIGSERIAL     PRIMARY KEY,
    machine_id       INTEGER       NOT NULL REFERENCES machines(id),
    rule             VARCHAR(32)   NOT NULL,          -- rule that opened it: rul_threshold | rul_trend
    severity         VARCHAR(16)   NOT NULL CHECK (severity IN ('WARNING', 'CRITICAL')),
    detail           VARCHAR(256)  NOT NULL,
    opened_cycle     INTEGER       NOT NULL,
    opened_at        TIMESTAMPTZ   NOT NULL,
    closed_cycle     INTEGER,
    closed_at        TIMESTAMPTZ,
    acknowledged_at  TIMESTAMPTZ
);

-- "open alerts of machine X" and "all open alerts" are the hot queries; a partial index keeps it tiny.
CREATE INDEX alerts_open_idx ON alerts (machine_id, severity) WHERE closed_at IS NULL;
CREATE INDEX alerts_opened_at_idx ON alerts (opened_at DESC);

COMMENT ON TABLE alerts IS 'Alert episodes. At most one open alert per (machine, severity); closed_at IS NULL means open.';
