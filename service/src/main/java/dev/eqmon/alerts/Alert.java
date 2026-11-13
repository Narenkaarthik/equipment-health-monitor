package dev.eqmon.alerts;

import java.time.Instant;

/** One alert episode. {@code closedAt == null} means open. */
public record Alert(long id, int machineId, String rule, Severity severity, String detail, int openedCycle,
        Instant openedAt, Integer closedCycle, Instant closedAt, Instant acknowledgedAt) {

    public boolean open() {
        return closedAt == null;
    }

    public Alert closed(int cycle, Instant at) {
        return new Alert(id, machineId, rule, severity, detail, openedCycle, openedAt, cycle, at, acknowledgedAt);
    }

    public Alert acknowledged(Instant at) {
        return new Alert(id, machineId, rule, severity, detail, openedCycle, openedAt, closedCycle, closedAt, at);
    }
}
