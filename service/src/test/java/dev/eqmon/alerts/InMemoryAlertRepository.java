package dev.eqmon.alerts;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/** Test double: alerts in a list, ids assigned in order. */
public class InMemoryAlertRepository implements AlertRepository {

    public final List<Alert> all = new ArrayList<>();

    @Override
    public Alert open(Alert a) {
        Alert stored = new Alert(all.size() + 1, a.machineId(), a.rule(), a.severity(), a.detail(), a.openedCycle(),
                a.openedAt(), null, null, null);
        all.add(stored);
        return stored;
    }

    @Override
    public void close(long id, int cycle, Instant at) {
        replace(id, find(id).orElseThrow().closed(cycle, at));
    }

    @Override
    public boolean acknowledge(long id, Instant at) {
        Optional<Alert> a = find(id);
        a.ifPresent(x -> replace(id, x.acknowledgedAt() == null ? x.acknowledged(at) : x));
        return a.isPresent();
    }

    @Override
    public Optional<Alert> find(long id) {
        return all.stream().filter(a -> a.id() == id).findFirst();
    }

    @Override
    public List<Alert> openFor(int machineId) {
        return all.stream().filter(a -> a.machineId() == machineId && a.open()).toList();
    }

    @Override
    public List<Alert> list(String status, int limit) {
        return all.stream().filter(a -> switch (status) {
            case "open" -> a.open();
            case "closed" -> !a.open();
            default -> true;
        }).limit(limit).toList();
    }

    private void replace(long id, Alert updated) {
        for (int i = 0; i < all.size(); i++) {
            if (all.get(i).id() == id) {
                all.set(i, updated);
            }
        }
    }
}
