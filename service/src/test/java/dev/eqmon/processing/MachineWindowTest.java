package dev.eqmon.processing;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.eqmon.ingest.Reading;
import java.io.IOException;
import java.nio.file.Path;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class MachineWindowTest {

    static Reading reading(int machine, int cycle, double level) {
        double[] sensors = new double[21];
        for (int i = 0; i < 21; i++) {
            sensors[i] = level + i;
        }
        return new Reading(machine, cycle, Instant.EPOCH, new double[] {0, 0, 100}, sensors);
    }

    @Test
    void consecutiveCyclesAreApplied() {
        MachineWindow w = new MachineWindow(1, 30);
        assertThat(w.apply(reading(1, 1, 10)).outcome()).isEqualTo(MachineWindow.Outcome.APPLIED);
        assertThat(w.apply(reading(1, 2, 11)).outcome()).isEqualTo(MachineWindow.Outcome.APPLIED);
        assertThat(w.size()).isEqualTo(2);
        assertThat(w.lastCycle()).isEqualTo(2);
    }

    @Test
    void lateOrDuplicateCycleIsIgnoredAndWindowUnchanged() {
        MachineWindow w = new MachineWindow(1, 30);
        w.apply(reading(1, 5, 10));
        w.apply(reading(1, 6, 12));
        MachineWindow.Result dup = w.apply(reading(1, 6, 99));
        MachineWindow.Result late = w.apply(reading(1, 3, 99));
        assertThat(dup.outcome()).isEqualTo(MachineWindow.Outcome.LATE);
        assertThat(late.outcome()).isEqualTo(MachineWindow.Outcome.LATE);
        assertThat(dup.features()).isEmpty();
        assertThat(w.size()).isEqualTo(2);
        assertThat(w.lastCycle()).isEqualTo(6);
        // the mean of s1 is still (10 + 12) / 2
        assertThat(w.apply(reading(1, 7, 14)).features().orElseThrow().get("s1_mean")).isEqualTo(12.0);
    }

    @Test
    void gapIsAcceptedAndReported() {
        MachineWindow w = new MachineWindow(1, 30);
        w.apply(reading(1, 1, 10));
        MachineWindow.Result r = w.apply(reading(1, 4, 10));
        assertThat(r.outcome()).isEqualTo(MachineWindow.Outcome.GAP);
        assertThat(r.gapCycles()).isEqualTo(2);
        assertThat(w.size()).isEqualTo(2);
        assertThat(w.lastCycle()).isEqualTo(4);
    }

    @Test
    void firstCycleNeedNotBeOne() {
        MachineWindow w = new MachineWindow(1, 30);
        assertThat(w.apply(reading(1, 120, 10)).outcome()).isEqualTo(MachineWindow.Outcome.APPLIED);
    }

    @Test
    void windowKeepsOnlyTheLastWReadings() {
        MachineWindow w = new MachineWindow(1, 3);
        for (int c = 1; c <= 10; c++) {
            w.apply(reading(1, c, c));
        }
        assertThat(w.size()).isEqualTo(3);
        // last three s1 values: 8, 9, 10
        FeatureVector f = w.apply(reading(1, 11, 11)).features().orElseThrow();
        assertThat(f.get("s1_mean")).isEqualTo(10.0);
        assertThat(f.get("s1_slope")).isCloseTo(1.0, within(1e-12));
        assertThat(f.windowRows()).isEqualTo(3);
    }

    @Test
    void snapshotRoundTripsThroughJsonAndKeepsTheStatistics() throws IOException {
        MachineWindow w = new MachineWindow(7, 5);
        for (int c = 1; c <= 8; c++) {
            w.apply(reading(7, c, 100 + c * c));
        }
        ObjectMapper json = new ObjectMapper();
        String text = json.writeValueAsString(w.snapshot());
        MachineWindow back = MachineWindow.restore(json.readValue(text, MachineWindow.WindowSnapshot.class));
        assertThat(back.lastCycle()).isEqualTo(8);
        assertThat(back.size()).isEqualTo(5);
        FeatureVector a = w.apply(reading(7, 9, 181)).features().orElseThrow();
        FeatureVector b = back.apply(reading(7, 9, 181)).features().orElseThrow();
        for (int i = 0; i < a.features().length; i++) {
            assertThat(b.features()[i]).as("feature %d", i).isCloseTo(a.features()[i], within(1e-9));
        }
    }

    /** Parity with the Python pipeline: engine 1, first 40 cycles, every sensor, tolerance 1e-6. */
    @Test
    void matchesThePythonFeatureFixture() throws IOException {
        Path fixture = Path.of("..", "tests", "fixtures", "window_features_engine1.json");
        JsonNode fx = new ObjectMapper().readTree(fixture.toFile());
        int window = fx.get("window").asInt();
        MachineWindow w = new MachineWindow(1, window);
        JsonNode raw = fx.get("raw");
        JsonNode expected = fx.get("expected");
        JsonNode cycles = fx.get("cycles");
        int checked = 0;
        for (int k = 0; k < raw.size(); k++) {
            double[] sensors = new double[21];
            for (int s = 0; s < 21; s++) {
                sensors[s] = raw.get(k).get(s).asDouble();
            }
            Reading r = new Reading(1, cycles.get(k).asInt(), Instant.EPOCH, new double[] {0, 0, 100}, sensors);
            FeatureVector f = w.apply(r).features().orElseThrow();
            for (int s = 1; s <= 21; s++) {
                JsonNode row = expected.get("s" + s).get(k);
                assertThat(f.get("s" + s + "_mean")).as("s%d mean row %d", s, k).isCloseTo(row.get(0).asDouble(), within(1e-6));
                assertThat(f.get("s" + s + "_std")).as("s%d std row %d", s, k).isCloseTo(row.get(1).asDouble(), within(1e-6));
                assertThat(f.get("s" + s + "_slope")).as("s%d slope row %d", s, k).isCloseTo(row.get(2).asDouble(), within(1e-6));
                checked++;
            }
        }
        assertThat(checked).isEqualTo(40 * 21);
    }
}
