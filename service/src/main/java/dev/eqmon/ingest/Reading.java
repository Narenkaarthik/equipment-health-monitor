package dev.eqmon.ingest;

import java.time.Instant;

/**
 * A validated reading as stored and processed. Sensors are indexed 0..20 for s1..s21.
 * Immutable; arrays are defensively copied on construction.
 */
public record Reading(int machineId, int cycle, Instant recordedAt, double[] settings, double[] sensors) {

    public Reading {
        settings = settings.clone();
        sensors = sensors.clone();
        if (settings.length != ReadingRequest.SETTING_COUNT) {
            throw new IllegalArgumentException("expected 3 settings");
        }
        if (sensors.length != ReadingRequest.SENSOR_COUNT) {
            throw new IllegalArgumentException("expected 21 sensors");
        }
    }

    /** Sensor value by 1-based sensor number (s1..s21). */
    public double sensor(int number) {
        return sensors[number - 1];
    }

    public static Reading from(ReadingRequest r, Instant fallbackTime) {
        double[] settings = new double[ReadingRequest.SETTING_COUNT];
        for (int i = 0; i < settings.length; i++) {
            settings[i] = r.settings().get(i);
        }
        double[] sensors = new double[ReadingRequest.SENSOR_COUNT];
        for (int i = 0; i < sensors.length; i++) {
            sensors[i] = r.sensors().get(ReadingRequest.sensorKey(i + 1));
        }
        return new Reading(r.machineId(), r.cycle(), r.recordedAt() == null ? fallbackTime : r.recordedAt(), settings, sensors);
    }
}
