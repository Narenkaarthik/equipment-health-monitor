# BUILD: Real-Time Equipment Monitoring Service

**One-line pitch:** A Java backend that ingests live sensor readings from industrial equipment, scores each machine's health with an ML model, raises alerts, and shows it on a live dashboard.

**Stack:** Java 21, Spring Boot, PostgreSQL, Redis, Apache Kafka (added in stage 5), ONNX Runtime, Docker Compose, JUnit 5, Testcontainers, k6. Dashboard in plain HTML with Chart.js.

**Time budget:** 8 weeks at about 6 hours a week.

**Ground rule:** You write the code. Use AI to explain an error or a concept, never to produce a file you then commit. This project is your main talking point in software interviews, so every line must be yours to defend.

---

## 1. Why this version stands out

Most student projects are either a notebook or a CRUD app. This is neither. It is a small production-style system with a data stream, a model in the loop, storage choices you can justify, tests, and a measured throughput number.

It also ties your work together: the model it serves is the one from your sensor-reduction project. If that project shows 8 sensors work as well as 21, this service runs on 8.

It runs on **real data replayed as a stream**, not on numbers you invented. That is the difference from the digital twin idea.

## 2. The data

Use the same dataset as your sensor-reduction project. If you have not fixed one, use **NASA C-MAPSS, subset FD001** (paper 1).

| Fact | Value |
| --- | --- |
| What it is | Run-to-failure records of simulated turbofan engines |
| Training engines in FD001 | 100 |
| Columns per row | Engine ID, cycle number, 3 operating settings, 21 sensor readings |
| What you predict | Remaining useful life (RUL) in cycles |

Each engine starts healthy and degrades until failure. That gives you a natural stream: replay each engine's rows in cycle order, one row at a time.

Be accurate when you describe it: C-MAPSS is a physics-based simulation published by NASA, not field data. Say "a NASA benchmark dataset", not "real engine data".

## 3. Architecture

```
replayer ──HTTP──▶ ingest API ──▶ [Kafka topic: readings] ──▶ processor
 (CSV → stream)     (validate)        (added in stage 5)         │
                                                                 ├─▶ PostgreSQL (readings, health scores, alerts)
                                                                 ├─▶ Redis (latest state per machine)
                                                                 ├─▶ model (ONNX Runtime, in-process)
                                                                 └─▶ alert engine
dashboard ◀──REST + Server-Sent Events── query API
```

| Component | Job |
| --- | --- |
| Replayer | Reads the dataset file and posts readings at a configurable rate, for many machines at once |
| Ingest API | Validates each reading and accepts it quickly |
| Processor | Keeps a sliding window per machine, computes features, calls the model, writes results |
| Model | Predicts remaining useful life from the window's features |
| Alert engine | Applies rules, opens and closes alerts, avoids duplicates |
| Query API | Serves machine lists, history and alerts to the dashboard |
| Dashboard | Shows fleet status, one machine's sensor charts, and live alerts |

## 4. Repository layout

```
equipment-monitor/
  README.md
  docker-compose.yml
  docs/
    architecture.md
    decisions/            # one short file per design decision
    load-test-report.md
  model/                  # Python: train and export to ONNX
    train.py
    export_onnx.py
  replayer/               # small Java command-line app
  service/                # Spring Boot application
    src/main/java/.../
      ingest/
      processing/
      model/
      alerts/
      query/
      config/
    src/main/resources/db/migration/   # Flyway SQL files
    src/test/java/...
  dashboard/
    index.html
  loadtest/
    ingest.js             # k6 script
```

## 5. Data model

Design these tables yourself; this is the minimum.

| Table | Key columns | Notes |
| --- | --- | --- |
| `machines` | id, name, status | status is HEALTHY, WARNING or CRITICAL |
| `readings` | machine_id, cycle, recorded_at, sensor values | Primary key (machine_id, cycle), which makes duplicate posts harmless |
| `health_scores` | machine_id, cycle, predicted_rul, model_version | One row per scored reading |
| `alerts` | id, machine_id, rule, severity, opened_at, closed_at | An open alert has no closed_at |

Decide and document: sensor values as separate columns or one JSON column? Which indexes, and why? When would you partition `readings` by time?

## 6. API

| Method and path | Purpose |
| --- | --- |
| `POST /api/readings` | Ingest one reading or a batch |
| `GET /api/machines` | Fleet list with status and latest predicted RUL |
| `GET /api/machines/{id}/readings?from=&to=&sensor=` | History for charts, paginated |
| `GET /api/machines/{id}/health` | Health score history |
| `GET /api/alerts?status=open` | Alert list |
| `POST /api/alerts/{id}/acknowledge` | Mark an alert as seen |
| `GET /api/stream` | Server-Sent Events: live status and alert updates |

## 7. Build stages

### Stage 0: Skeleton (week 1)

- [ ] Spring Boot project with one health-check endpoint.
- [ ] Docker Compose file that starts the service and PostgreSQL.
- [ ] Flyway migration that creates the `machines` table.
- [ ] GitHub Actions workflow that runs tests on every push.

**Done when:** `docker compose up` starts everything and the health check returns 200.

### Stage 1: Ingest and store (week 1–2)

- [ ] `POST /api/readings` with validation: known machine, cycle is positive, no missing sensors.
- [ ] Write to PostgreSQL. A repeated (machine, cycle) must not create a duplicate or an error.
- [ ] Batch inserts for batch posts.
- [ ] Replayer: read the CSV, post readings for N machines in parallel at R readings per second.
- [ ] Integration tests with Testcontainers against a real PostgreSQL.

**Done when:** the replayer streams all 100 engines and the row count in the database matches the file.

### Stage 2: Sliding window and features (week 3)

- [ ] Per machine, keep the last W readings in memory (start with W = 30). Use a ring buffer or `ArrayDeque`.
- [ ] Compute per-sensor features over the window: mean, standard deviation, slope.
- [ ] Compute the rolling mean in O(1) per new reading, not by re-summing the window. This is the sliding-window pattern from your DSA practice.
- [ ] Handle out-of-order and missing cycles: decide the rule, write it down, test it.
- [ ] Store the latest state per machine in Redis, so a restart does not lose the window.

**Done when:** unit tests check the features against values you computed by hand for a small window.

### Stage 3: Model in the loop (week 4)

- [ ] In Python, train a simple RUL regressor (gradient boosting or random forest) on the same window features. Cap RUL at about 125 cycles, a common convention for this dataset.
- [ ] Export it to ONNX. Load it in Java with ONNX Runtime and score each new window.
- [ ] Write a parity test: the same input gives the same prediction in Python and in Java, within a small tolerance.
- [ ] Store predictions with a model version.
- [ ] If ONNX blocks you for more than a week, fall back to a small Python scoring service called over HTTP. Record the trade-off in `docs/decisions/`.

**Done when:** every ingested reading produces a predicted RUL within a few milliseconds.

### Stage 4: Alerts (week 5)

- [ ] Two rule types: threshold (predicted RUL below 30 cycles is CRITICAL, below 60 is WARNING) and trend (RUL fell more than X over the last N cycles).
- [ ] An alert opens once and stays open; it must not fire again on every reading. It closes only after the condition clears for K consecutive readings.
- [ ] Machine status follows its most severe open alert.
- [ ] Acknowledge endpoint.
- [ ] Unit tests for the open, stay-open and close transitions.

**Done when:** replaying one engine to failure produces exactly one WARNING and one CRITICAL alert, in that order.

### Stage 5: Decouple with Kafka (week 6)

- [ ] Add Kafka to Docker Compose. Ingest now publishes to a `readings` topic and returns immediately; the processor consumes from it.
- [ ] Use the machine ID as the message key so one machine's readings stay in order.
- [ ] Make processing idempotent, so a message delivered twice changes nothing.
- [ ] Send messages that fail repeatedly to a dead-letter topic.
- [ ] Kill the processor mid-stream, restart it, and show that no reading is lost or double-counted.

**Done when:** the kill-and-restart test passes. Write up what you observed.

If you run short of time, this is the stage to skip. Stages 0–4 plus 6–7 still make a complete project.

### Stage 6: Dashboard (week 7)

Keep this small. It exists to make the system visible, not to show front-end skill.

- [ ] Fleet view: a table of machines with status colour and predicted RUL.
- [ ] Machine view: line charts of a few sensors and of predicted RUL over time.
- [ ] Alert panel that updates live through Server-Sent Events.

**Done when:** you can start the replayer and watch a machine go from green to red.

### Stage 7: Prove it works (week 8)

- [ ] Load test ingest with k6. Record throughput and p50, p95 and p99 latency.
- [ ] Find the first bottleneck, fix it, and measure again. Keep both sets of numbers.
- [ ] Add metrics with Micrometer: readings ingested, processing lag, inference time.
- [ ] Deploy to a free cloud tier and put the link in the README.
- [ ] Write `docs/architecture.md` and at least four decision records.
- [ ] Record a 2-minute demo video.

**Done when:** the README has a diagram, a live link, a demo video and a before-and-after performance table.

## 8. Design decisions to write up

One short file each: the options, what you chose, and why.

1. Why Kafka between ingest and processing, instead of processing inside the request?
2. Sensor values as columns or JSON?
3. In-process ONNX or a separate Python model service?
4. Where does window state live, and what happens on restart?
5. PostgreSQL or a time-series database? Read paper 2 before answering.
6. Server-Sent Events or WebSockets for the dashboard?

## 9. What "finished" means

- `docker compose up` runs the whole system on a fresh machine.
- A measured number: "handles X readings per second at p95 latency of Y ms on a laptop".
- A failure test you can describe: what happens when the processor crashes.
- More than 60% test coverage on the processing and alert code.
- A live link and a demo video.

## 10. Mistakes that will sink it

- Generating random sensor data instead of replaying the dataset.
- Calling it a digital twin. It is a monitoring service.
- Spending three weeks on the dashboard.
- Adding Kafka first. Build it without, then add it, so you can explain what it bought you.
- No tests, or no load numbers.
- Alerts that fire on every reading.
- Claiming scale you did not measure.

## 11. Questions an interviewer will ask

1. Walk me through what happens to one reading, end to end.
2. What happens if the same reading arrives twice? Out of order?
3. The processor crashes. What is lost?
4. How would this handle 10,000 machines? Where does it break first?
5. Why PostgreSQL? When would you switch?
6. How do you deploy a new model version without downtime?
7. How do you know the Java prediction matches the Python one?
8. Which index did you add, and how did you know it helped?
9. What is your p99 latency, and what causes the tail?

## 12. Resume bullets (fill in your real numbers)

- Built a real-time equipment monitoring service in Java and Spring Boot that ingests sensor streams through Kafka, scores machine health with an ONNX model and raises de-duplicated alerts; sustained X readings per second at Y ms p95 latency.
- Verified no data loss across processor restarts through idempotent consumers; Z% test coverage using JUnit and Testcontainers.

## 13. Papers to read

All four are free to read.

1. **Saxena, Goebel, Simon, Eklund (2008).** "Damage Propagation Modeling for Aircraft Engine Run-to-Failure Simulation." International Conference on Prognostics and Health Management. https://data.nasa.gov/dataset/damage-propagation-modeling-for-aircraft-engine-run-to-failure-simulation. *The dataset paper. Read first.*
2. **Pelkonen et al. (2015).** "Gorilla: A Fast, Scalable, In-Memory Time Series Database." Proceedings of the VLDB Endowment, 8(12). *How Facebook stores monitoring data. Read for the storage decision; the compression idea is a good stretch feature.*
3. **Kreps, Narkhede, Rao (2011).** "Kafka: a Distributed Messaging System for Log Processing." NetDB workshop. *Read before stage 5. It explains partitions, offsets and why ordering is per key.*
4. **Sculley et al. (2015).** "Hidden Technical Debt in Machine Learning Systems." NeurIPS. *Why the model is the small part of an ML system. Gives you vocabulary for interviews.*

Search papers 2–4 by title; each has a free PDF from the publisher or the authors.
