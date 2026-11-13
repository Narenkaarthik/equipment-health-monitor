-- Stage 0: the fleet. One row per monitored machine (a C-MAPSS engine unit when replaying FD001).
CREATE TABLE machines (
    id          INTEGER      PRIMARY KEY,
    name        VARCHAR(64)  NOT NULL UNIQUE,
    status      VARCHAR(16)  NOT NULL DEFAULT 'HEALTHY'
                             CHECK (status IN ('HEALTHY', 'WARNING', 'CRITICAL')),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

COMMENT ON TABLE machines IS 'Monitored machines; status follows the most severe open alert.';
