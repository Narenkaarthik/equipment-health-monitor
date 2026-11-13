package dev.eqmon.processing;

import java.util.Optional;

/** Durable home of the per-machine window so a restart does not lose it (Redis in production). */
public interface WindowStateStore {

    void save(MachineWindow.WindowSnapshot snapshot);

    Optional<MachineWindow.WindowSnapshot> load(int machineId);

    /** Removes every stored window (tests and operator reset). */
    void clear();
}
