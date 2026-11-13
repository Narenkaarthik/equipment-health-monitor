package dev.eqmon.model;

/** Receives every new health score: the alert engine (stage 4) and the live stream (stage 6). */
@FunctionalInterface
public interface HealthScoreListener {
    void onScore(HealthScore score);
}
