package dev.eqmon.alerts;

/** Published on every alert transition and every machine status change (consumed by the SSE stream). */
public record AlertEvent(Type type, int machineId, Alert alert, String status) {

    public enum Type { OPENED, CLOSED, ACKNOWLEDGED, STATUS }
}
