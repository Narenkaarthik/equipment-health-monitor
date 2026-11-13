# 0001: Kafka between ingest and processing, instead of processing inside the request

**Status:** accepted (stage 5). Stages 1 to 4 ran without it, on purpose, so the difference can be measured.

## The two designs

**Direct** (`monitor.pipeline=direct`, stages 1 to 4): `POST /api/readings` validates, inserts, then
runs the window update, the model and the alert rules in the request thread. The client gets 202
when everything is done.

**Decoupled** (`monitor.pipeline=kafka`, stage 5): the request validates, inserts and publishes
one message per reading to the `readings` topic, keyed by machine id, then returns. A consumer
group (the processor) reads the topic and does the rest.

## Why decouple

1. **Latency and throughput of ingest stop depending on the model and Redis.** In the direct
   design the request pays for one Redis write, one ONNX call and one or two PostgreSQL writes
   on top of the insert (about 2 ms of processing per reading, measured in stage 2). With Kafka
   the request pays for the insert and an asynchronous publish. The load-test report shows both.
2. **A crash in the processor loses nothing.** The topic keeps the message until the consumer
   commits its offset, and the offset is committed only after the processor applied the reading
   (`AckMode.RECORD`). Restart the consumer and it resumes where it stopped. In the direct design a
   crash mid-request loses that reading's processing (the row is stored, the score is not).
3. **Ordering per machine, parallelism across machines.** Kafka orders messages within a
   partition; keying by machine id puts all of one machine's readings on one partition. Six
   partitions give six consumer threads without any locking of our own (Kreps, Narkhede, Rao 2011:
   partitions are the unit of parallelism, offsets the unit of progress).
4. **Back-pressure instead of overload.** A burst of readings queues in the topic; the processor
   drains it at its own pace. In the direct design a burst means more request threads doing
   model inference at once.
5. **More consumers later.** A second consumer group (an archiver, a retraining exporter) can
   read the same stream without touching ingest.

## What it costs

- One more system to run (a broker, its storage, its monitoring).
- At-least-once delivery, so the processor must be idempotent. It is: the ordering rule
  rejects a cycle that is not newer than the last applied one, and every table has a primary key
  on (machine, cycle). The kill-and-restart experiment in `docs/architecture.md` demonstrates it.
- A reading is "accepted" before it is scored; a client that wants the score must ask for it
  (`GET /api/machines/{id}/health`) or listen on `/api/stream`.
- Messages that fail three times go to `readings.DLT` for a human to look at, instead of
  blocking the partition.

## Why not do this first

The plan's rule: build without it, then add it, so you can explain what it bought you. The
direct design is simpler and is still the right one for a single-process demo or for the tests;
it stays available behind the `monitor.pipeline` switch.
