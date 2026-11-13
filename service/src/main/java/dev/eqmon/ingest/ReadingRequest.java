package dev.eqmon.ingest;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * One sensor reading as posted to {@code POST /api/readings}.
 *
 * <pre>{"machineId": 1, "cycle": 17, "recordedAt": "2026-01-01T00:00:00Z",
 *       "settings": [-0.0007, -0.0004, 100.0], "sensors": {"s1": 518.67, ..., "s21": 23.419}}</pre>
 *
 * Validation lives in {@link ReadingValidator} so every problem in a batch is reported at once.
 */
public record ReadingRequest(
        Integer machineId,
        Integer cycle,
        Instant recordedAt,
        List<Double> settings,
        Map<String, Double> sensors) {

    public static final int SENSOR_COUNT = 21;
    public static final int SETTING_COUNT = 3;

    public static String sensorKey(int i) {
        return "s" + i;
    }
}
