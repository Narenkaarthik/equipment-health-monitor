package dev.eqmon.alerts;

/** Ordered from least to most severe; a machine's status is the most severe open alert, or HEALTHY. */
public enum Severity {
    WARNING, CRITICAL;

    public static final String HEALTHY = "HEALTHY";
}
