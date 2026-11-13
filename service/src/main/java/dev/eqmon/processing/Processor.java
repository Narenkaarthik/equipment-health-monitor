package dev.eqmon.processing;

import dev.eqmon.ingest.Reading;
import dev.eqmon.ingest.ReadingSink;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Keeps one {@link MachineWindow} per machine, applies each reading in order, persists the window to
 * the state store and hands the features on. Calls for the same machine are serialised on the window;
 * different machines proceed in parallel.
 */
public class Processor implements ReadingSink {

    private static final Logger log = LoggerFactory.getLogger(Processor.class);

    private final int windowSize;
    private final WindowStateStore store;
    private final List<FeatureConsumer> consumers;
    private final Map<Integer, MachineWindow> windows = new ConcurrentHashMap<>();
    private final Counter applied;
    private final Counter gaps;
    private final Counter late;
    private final Timer timer;

    public Processor(int windowSize, WindowStateStore store, List<FeatureConsumer> consumers, MeterRegistry metrics) {
        this.windowSize = windowSize;
        this.store = store;
        this.consumers = List.copyOf(consumers);
        this.applied = metrics.counter("monitor.readings.processed", "outcome", "applied");
        this.gaps = metrics.counter("monitor.readings.processed", "outcome", "gap");
        this.late = metrics.counter("monitor.readings.processed", "outcome", "late");
        this.timer = metrics.timer("monitor.processing.time");
    }

    @Override
    public void accept(List<Reading> readings) {
        for (Reading r : readings) {
            process(r);
        }
    }

    /** @return the outcome for this reading (features are delivered to the consumers as a side effect) */
    public MachineWindow.Result process(Reading r) {
        long start = System.nanoTime();
        MachineWindow window = windows.computeIfAbsent(r.machineId(), this::loadOrCreate);
        MachineWindow.Result result;
        synchronized (window) {
            result = window.apply(r);
            if (result.outcome() != MachineWindow.Outcome.LATE) {
                store.save(window.snapshot());
            }
        }
        switch (result.outcome()) {
            case APPLIED -> applied.increment();
            case GAP -> {
                gaps.increment();
                log.debug("machine {} cycle {}: gap of {} cycles", r.machineId(), r.cycle(), result.gapCycles());
            }
            case LATE -> late.increment();
        }
        result.features().ifPresent(f -> {
            for (FeatureConsumer c : consumers) {
                c.accept(r, f);
            }
        });
        timer.record(System.nanoTime() - start, java.util.concurrent.TimeUnit.NANOSECONDS);
        return result;
    }

    private MachineWindow loadOrCreate(int machineId) {
        return store.load(machineId)
                .map(snap -> {
                    log.info("machine {}: restored window of {} rows (last cycle {})", machineId, snap.cycles().size(), snap.lastCycle());
                    return MachineWindow.restore(snap);
                })
                .orElseGet(() -> new MachineWindow(machineId, windowSize));
    }

    /** Drops in-memory windows (the store keeps them); the next reading reloads from the store. */
    public void forgetInMemoryState() {
        windows.clear();
    }

    public int windowSize() {
        return windowSize;
    }
}
