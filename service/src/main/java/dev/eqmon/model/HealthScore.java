package dev.eqmon.model;

import java.time.Instant;

/** A scored reading. */
public record HealthScore(int machineId, int cycle, double predictedRul, String modelVersion, int windowRows, Instant scoredAt) {}
