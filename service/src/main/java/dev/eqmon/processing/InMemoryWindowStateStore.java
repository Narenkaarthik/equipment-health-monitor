package dev.eqmon.processing;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

/** Window store without Redis: state survives nothing. Used by unit tests and the {@code no-redis} profile. */
public class InMemoryWindowStateStore implements WindowStateStore {

    private final Map<Integer, MachineWindow.WindowSnapshot> map = new ConcurrentHashMap<>();

    @Override
    public void save(MachineWindow.WindowSnapshot snapshot) {
        map.put(snapshot.machineId(), snapshot);
    }

    @Override
    public Optional<MachineWindow.WindowSnapshot> load(int machineId) {
        return Optional.ofNullable(map.get(machineId));
    }

    @Override
    public void clear() {
        map.clear();
    }
}
