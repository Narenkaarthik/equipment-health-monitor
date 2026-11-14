// k6 load test for POST /api/readings.
//   k6 run loadtest/ingest.js                       # 60 s, 20 virtual users, batches of 10
//   k6 run -e VUS=50 -e DURATION=120s -e BATCH=1 loadtest/ingest.js
// Each virtual user owns a set of machines (ids are spread so two users never post the same machine)
// and posts strictly increasing cycles, so the service sees fresh, in-order readings the whole time.
import http from "k6/http";
import { check } from "k6";
import { Counter, Trend } from "k6/metrics";

const VUS = Number(__ENV.VUS || 20);
const DURATION = __ENV.DURATION || "60s";
const BATCH = Number(__ENV.BATCH || 10);
const BASE = __ENV.BASE || "http://localhost:8080";
const MACHINES = Number(__ENV.MACHINES || 100);

export const options = {
  summaryTrendStats: ["avg", "min", "med", "max", "p(50)", "p(95)", "p(99)"],
  scenarios: {
    ingest: { executor: "constant-vus", vus: VUS, duration: DURATION },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500"],
  },
};

const readingsSent = new Counter("readings_sent");
const readingsPerSecond = new Trend("readings_per_request");

const BASELINE = [518.67, 642.0, 1588.0, 1400.0, 14.62, 21.61, 554.0, 2388.0, 9050.0, 1.3, 47.4, 522.0, 2388.0,
  8135.0, 8.42, 0.03, 392, 2388, 100, 39.0, 23.4];

export function setup() {
  for (let id = 1; id <= MACHINES; id++) {
    http.put(`${BASE}/api/machines/${id}`, JSON.stringify({ name: `load-${id}` }), { headers: { "Content-Type": "application/json" } });
  }
  // start above any cycle the replayer may have used so every reading is new and in order
  return { startCycle: 100000 };
}

export default function (data) {
  // VU v owns machines v, v+VUS, v+2*VUS, ... ; iteration i advances its cycles
  const vu = __VU; // 1-based
  const iter = __ITER;
  const machine = ((vu - 1) + iter * VUS) % MACHINES + 1;
  const cycle0 = data.startCycle + Math.floor((iter * VUS) / MACHINES) * BATCH;
  const batch = [];
  for (let b = 0; b < BATCH; b++) {
    const cycle = cycle0 + b;
    const sensors = {};
    for (let s = 1; s <= 21; s++) {
      sensors[`s${s}`] = BASELINE[s - 1] + Math.sin((cycle + s) / 7) * 0.5;
    }
    batch.push({ machineId: machine, cycle: cycle, settings: [0, 0, 100], sensors: sensors });
  }
  const res = http.post(`${BASE}/api/readings`, JSON.stringify(batch), { headers: { "Content-Type": "application/json" } });
  check(res, { "202 accepted": (r) => r.status === 202 });
  if (res.status === 202) {
    readingsSent.add(BATCH);
    readingsPerSecond.add(BATCH);
  }
}

export function handleSummary(data) {
  const m = data.metrics;
  const dur = m.http_req_duration.values;
  const seconds = Number(DURATION.replace("s", ""));
  const sent = m.readings_sent ? m.readings_sent.values.count : 0;
  const summary = {
    vus: VUS, duration_s: seconds, batch: BATCH,
    requests: m.http_reqs.values.count,
    readings: sent,
    readings_per_second: sent / seconds,
    p50_ms: dur["p(50)"] !== undefined ? dur["p(50)"] : dur.med,
    p95_ms: dur["p(95)"],
    p99_ms: dur["p(99)"],
    failed_rate: m.http_req_failed.values.rate,
  };
  return {
    stdout: JSON.stringify(summary, null, 2) + "\n",
    [__ENV.OUT || "loadtest/last-run.json"]: JSON.stringify(summary, null, 2),
  };
}
