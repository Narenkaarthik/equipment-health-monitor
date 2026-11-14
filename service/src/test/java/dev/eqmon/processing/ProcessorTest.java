package dev.eqmon.processing;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import dev.eqmon.ingest.Reading;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;

/** Crash safety of the processor's ordering: the window is saved only after the consumers succeeded. */
class ProcessorTest {

    static Reading reading(int cycle) {
        double[] sensors = new double[21];
        java.util.Arrays.fill(sensors, 100 + cycle);
        return new Reading(1, cycle, Instant.now(), new double[] {0, 0, 100}, sensors);
    }

    @Test
    void aFailedConsumerLeavesTheStoredWindowUntouchedAndTheRetryIsApplied() {
        InMemoryWindowStateStore store = new InMemoryWindowStateStore();
        List<Integer> scored = new ArrayList<>();
        AtomicBoolean fail = new AtomicBoolean(false);
        FeatureConsumer scorer = (r, f) -> {
            if (fail.get()) {
                throw new IllegalStateException("database down");
            }
            scored.add(r.cycle());
        };
        Processor p = new Processor(30, store, List.of(scorer), new SimpleMeterRegistry());
        p.process(reading(1));
        p.process(reading(2));
        assertThat(store.load(1).orElseThrow().lastCycle()).isEqualTo(2);

        fail.set(true);
        assertThatThrownBy(() -> p.process(reading(3))).hasMessageContaining("database down");
        assertThat(store.load(1).orElseThrow().lastCycle()).as("window not saved after a failed consumer").isEqualTo(2);

        fail.set(false);
        MachineWindow.Result retry = p.process(reading(3)); // Kafka redelivers the same record
        assertThat(retry.outcome()).isEqualTo(MachineWindow.Outcome.APPLIED);
        assertThat(scored).containsExactly(1, 2, 3);
        assertThat(store.load(1).orElseThrow().lastCycle()).isEqualTo(3);
    }

    @Test
    void aRedeliveryAfterACrashBeforeTheSaveIsScoredAgainNotLost() {
        InMemoryWindowStateStore store = new InMemoryWindowStateStore();
        List<Integer> scored = new ArrayList<>();
        Processor first = new Processor(30, store, List.of((r, f) -> scored.add(r.cycle())), new SimpleMeterRegistry());
        for (int c = 1; c <= 5; c++) {
            first.process(reading(c));
        }
        // simulate "crashed after scoring cycle 5 but before saving": the store still says 4
        MachineWindow w = new MachineWindow(1, 30);
        for (int c = 1; c <= 4; c++) {
            w.apply(reading(c));
        }
        store.save(w.snapshot());

        Processor restarted = new Processor(30, store, List.of((r, f) -> scored.add(r.cycle())), new SimpleMeterRegistry());
        assertThat(restarted.process(reading(5)).outcome()).isEqualTo(MachineWindow.Outcome.APPLIED);
        assertThat(restarted.process(reading(5)).outcome()).isEqualTo(MachineWindow.Outcome.LATE);
        // cycle 5 reached the scorer twice; the health_scores primary key makes the second insert a no-op
        assertThat(scored).containsExactly(1, 2, 3, 4, 5, 5);
    }
}
