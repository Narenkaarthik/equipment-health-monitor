-- Stage 3: one predicted RUL per scored reading, tagged with the model that produced it.
CREATE TABLE health_scores (
    machine_id     INTEGER       NOT NULL REFERENCES machines(id),
    cycle          INTEGER       NOT NULL,
    predicted_rul  REAL          NOT NULL,
    model_version  VARCHAR(96)   NOT NULL,
    window_rows    SMALLINT      NOT NULL,
    scored_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (machine_id, cycle)
);

COMMENT ON TABLE health_scores IS 'Predicted remaining useful life per (machine, cycle); PK makes re-scoring idempotent.';
