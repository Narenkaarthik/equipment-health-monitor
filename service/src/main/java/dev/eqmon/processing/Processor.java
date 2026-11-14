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
    private final Timer lag;

    public Processor(int windowSize, WindowStateStore store, List<FeatureConsumer> consumers, MeterRegistry metrics) {
        this.windowSize = windowSize;
        this.store = store;
        this.consumers = List.copyOf(consumers);
        this.applied = metrics.counter("monitor.readings.processed", "outcome", "applied");
        this.gaps = metrics.counter("monitor.readings.processed", "outcome", "gap");
        this.late = metrics.counter("monitor.readings.processed", "outcome", "late");
        this.timer = metrics.timer("monitor.processing.time");
        this.lag = Timer.builder("monitor.processing.lag")
                .description("time from ingest (recordedAt) to the end of processing")
                .publishPercentiles(0.5, 0.95, 0.99)
                .register(metrics);
    }

    @Override
    public void accept(List<Reading> readings) {
        for (Reading r : readings) {
            process(r);
        }
    }

    /** @return the outcome for this reading (features are delivered to the consumers as a side effect) */
    /**
     * Order matters for crash safety: the window is saved to the store only AFTER the consumers (score
     * insert, alerts) succeeded. A crash before the save means the reading is redelivered against the
     * old window, scored again, and the score insert is a no-op (primary key). Saving first would make the
     * redelivered reading look LATE and its score would be lost. If a consumer throws, the in-memory window
     * is dropped so the retry reloads the last saved state instead of seeing its own half-applied reading.
     */
    public MachineWindow.Result process(Reading r) {
        long start = System.nanoTime();
        MachineWindow window = windows.computeIfAbsent(r.machineId(), this::loadOrCreate);
        MachineWindow.Result result;
        synchronized (window) {
            result = window.apply(r);
            if (result.outcome() != MachineWindow.Outcome.LATE) {
                try {
                    FeatureVector f = result.features().orElseThrow();
                    for (FeatureConsumer c : consumers) {
                        c.accept(r, f);
                    }
                    store.save(window.snapshot());
                } catch (RuntimeException e) {
                    windows.remove(r.machineId(), window);
                    throw e;
                }
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
        if (r.recordedAt() != null) {
            lag.record(java.time.Duration.between(r.recordedAt(), java.time.Instant.now()));
        }
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
