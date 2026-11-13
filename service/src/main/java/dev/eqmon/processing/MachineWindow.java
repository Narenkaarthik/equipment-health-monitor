package dev.eqmon.processing;

import dev.eqmon.ingest.Reading;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * The last W readings of one machine and the running statistics of every sensor.
 *
 * <p>Ordering rule (docs/decisions/0004): cycles are the machine's clock.
 * <ul>
 *   <li>{@code cycle == last + 1}: the normal case.</li>
 *   <li>{@code cycle > last + 1}: a gap. The reading is accepted and appended; the window then spans
 *       more cycles than rows, which is recorded as a gap and otherwise tolerated (the features are
 *       still "the last W observations").</li>
 *   <li>{@code cycle <= last}: late or duplicate. The reading is NOT applied; the window is unchanged
 *       and no features are produced, because a decision for a later cycle has already been made.</li>
 * </ul>
 * Not thread-safe; the {@link Processor} serialises calls per machine.
 */
public final class MachineWindow {

    public enum Outcome { APPLIED, GAP, LATE }

    public record Result(Outcome outcome, Optional<FeatureVector> features, int gapCycles) {}

    private final int machineId;
    private final int capacity;
    private final ArrayDeque<double[]> rows = new ArrayDeque<>();
    private final ArrayDeque<Integer> cycles = new ArrayDeque<>();
    private final RollingStats[] stats = new RollingStats[FeatureVector.SENSORS];
    private int lastCycle = 0;

    public MachineWindow(int machineId, int capacity) {
        this.machineId = machineId;
        this.capacity = capacity;
        for (int i = 0; i < stats.length; i++) {
            stats[i] = new RollingStats(capacity);
        }
    }

    public int machineId() {
        return machineId;
    }

    public int lastCycle() {
        return lastCycle;
    }

    public int size() {
        return rows.size();
    }

    public Result apply(Reading r) {
        if (r.machineId() != machineId) {
            throw new IllegalArgumentException("reading for machine " + r.machineId() + " given to window of " + machineId);
        }
        if (rows.isEmpty() && lastCycle == 0) {
            push(r);
            return new Result(Outcome.APPLIED, Optional.of(features(r.cycle())), 0);
        }
        if (r.cycle() <= lastCycle) {
            return new Result(Outcome.LATE, Optional.empty(), 0);
        }
        int gap = r.cycle() - lastCycle - 1;
        push(r);
        return new Result(gap > 0 ? Outcome.GAP : Outcome.APPLIED, Optional.of(features(r.cycle())), gap);
    }

    private void push(Reading r) {
        if (rows.size() == capacity) {
            rows.removeFirst();
            cycles.removeFirst();
        }
        rows.addLast(r.sensors());
        cycles.addLast(r.cycle());
        for (int s = 0; s < stats.length; s++) {
            stats[s].add(r.sensors()[s]);
        }
        lastCycle = r.cycle();
    }

    private FeatureVector features(int cycle) {
        double[] f = new double[FeatureVector.SIZE];
        for (int s = 0; s < stats.length; s++) {
            f[s * 3] = stats[s].mean();
            f[s * 3 + 1] = stats[s].std();
            f[s * 3 + 2] = stats[s].slope();
        }
        return new FeatureVector(machineId, cycle, rows.size(), f);
    }

    /** Everything needed to rebuild this window after a restart. */
    public WindowSnapshot snapshot() {
        List<Integer> c = new ArrayList<>(cycles);
        List<double[]> v = new ArrayList<>(rows);
        return new WindowSnapshot(machineId, capacity, lastCycle, c, v);
    }

    public static MachineWindow restore(WindowSnapshot snap) {
        MachineWindow w = new MachineWindow(snap.machineId(), snap.capacity());
        for (int i = 0; i < snap.cycles().size(); i++) {
            double[] sensors = snap.sensors().get(i);
            w.rows.addLast(sensors.clone());
            w.cycles.addLast(snap.cycles().get(i));
            for (int s = 0; s < w.stats.length; s++) {
                w.stats[s].add(sensors[s]);
            }
        }
        w.lastCycle = snap.lastCycle();
        return w;
    }

    /** Serialisable state of a window. */
    public record WindowSnapshot(int machineId, int capacity, int lastCycle, List<Integer> cycles, List<double[]> sensors) {}
}
