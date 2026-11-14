package dev.eqmon.processing;

import static org.assertj.core.api.Assertions.assertThat;

import dev.eqmon.ingest.Reading;
import dev.eqmon.support.IntegrationTestBase;
import java.time.Instant;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

/** Stage 2 "restart does not lose the window": state round-trips through a real Redis. */
class ProcessorRestartIT extends IntegrationTestBase {

    @Autowired Processor processor;
    @Autowired WindowStateStore store;
    @Autowired dev.eqmon.machines.MachineRepository machines;
    @Autowired org.springframework.jdbc.core.simple.JdbcClient jdbc;

    @BeforeEach
    void clean() {
        jdbc.sql("delete from alerts").update();
        jdbc.sql("delete from health_scores").update();
        machines.upsert(42, "engine-042");
        machines.upsert(43, "engine-043");
        store.clear();
        processor.forgetInMemoryState();
    }

    static Reading reading(int machine, int cycle, double level) {
        double[] sensors = new double[21];
        for (int i = 0; i < 21; i++) {
            sensors[i] = level + i * 0.5;
        }
        return new Reading(machine, cycle, Instant.EPOCH, new double[] {0, 0, 100}, sensors);
    }

    @Test
    void windowSurvivesARestart() {
        for (int c = 1; c <= 40; c++) {
            processor.process(reading(42, c, 600 + c));
        }
        FeatureVector before = processor.process(reading(42, 41, 641)).features().orElseThrow();

        // "restart": the in-memory map is gone, Redis is not
        processor.forgetInMemoryState();
        assertThat(store.load(42)).isPresent();
        assertThat(store.load(42).get().lastCycle()).isEqualTo(41);

        MachineWindow.Result after = processor.process(reading(42, 42, 642));
        assertThat(after.outcome()).isEqualTo(MachineWindow.Outcome.APPLIED);
        FeatureVector f = after.features().orElseThrow();
        assertThat(f.windowRows()).isEqualTo(processor.windowSize());
        // s1 window after restart is cycles 13..42 -> mean of 613..642 = 627.5
        assertThat(f.get("s1_mean")).isCloseTo(627.5, org.assertj.core.api.Assertions.within(1e-9));
        assertThat(before.get("s1_mean")).isCloseTo(626.5, org.assertj.core.api.Assertions.within(1e-9));
    }

    @Test
    void lateReadingAfterRestartIsStillRejected() {
        processor.process(reading(43, 10, 1));
        processor.forgetInMemoryState();
        assertThat(processor.process(reading(43, 9, 1)).outcome()).isEqualTo(MachineWindow.Outcome.LATE);
        assertThat(processor.process(reading(43, 11, 1)).outcome()).isEqualTo(MachineWindow.Outcome.APPLIED);
    }
}
