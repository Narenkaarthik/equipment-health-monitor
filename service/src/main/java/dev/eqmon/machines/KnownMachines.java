package dev.eqmon.machines;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * "Is this machine registered?" for the ingest validator, without a database round trip per request.
 *
 * <p>Ids seen once are cached; an id not in the cache is looked up in the database (so a machine registered
 * through another instance is still accepted) and cached if it exists. Machines are never deleted by the
 * service, so a cached id cannot go stale. {@code monitor.ingest.cache-machines=false} turns the cache off,
 * which is how the load test measures what it is worth.
 */
@Component
public class KnownMachines {

    private final MachineRepository machines;
    private final boolean enabled;
    private final Set<Integer> cache = ConcurrentHashMap.newKeySet();

    public KnownMachines(MachineRepository machines, @Value("${monitor.ingest.cache-machines:true}") boolean enabled) {
        this.machines = machines;
        this.enabled = enabled;
    }

    public boolean contains(int id) {
        if (enabled && cache.contains(id)) {
            return true;
        }
        boolean exists = machines.find(id).isPresent();
        if (exists && enabled) {
            cache.add(id);
        }
        return exists;
    }

    public void add(int id) {
        if (enabled) {
            cache.add(id);
        }
    }

    /** Test hook: forget everything (a test that deletes machines must call it). */
    public void clear() {
        cache.clear();
    }
}
