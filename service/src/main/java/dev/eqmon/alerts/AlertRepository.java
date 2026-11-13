package dev.eqmon.alerts;

import java.util.List;
import java.util.Optional;

/** Persistence of alert episodes. */
public interface AlertRepository {

    /** @return the stored alert with its id */
    Alert open(Alert alert);

    void close(long id, int cycle, java.time.Instant at);

    boolean acknowledge(long id, java.time.Instant at);

    Optional<Alert> find(long id);

    List<Alert> openFor(int machineId);

    /** @param status "open", "closed" or "all" */
    List<Alert> list(String status, int limit);
}
