package dev.eqmon.ingest;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

class ReadingValidatorTest {

    private final ReadingValidator validator = new ReadingValidator();

    static Map<String, Double> allSensors() {
        Map<String, Double> m = new HashMap<>();
        for (int i = 1; i <= 21; i++) {
            m.put("s" + i, (double) i);
        }
        return m;
    }

    static ReadingRequest valid(int machine, int cycle) {
        return new ReadingRequest(machine, cycle, null, List.of(0.0, 0.0, 100.0), allSensors());
    }

    @Test
    void acceptsAValidReading() {
        assertThat(validator.validate(List.of(valid(1, 1)), Set.of(1)::contains)).isEmpty();
    }

    @Test
    void rejectsUnknownMachine() {
        var problems = validator.validate(List.of(valid(42, 1)), Set.of(1)::contains);
        assertThat(problems).extracting(ReadingValidator.Problem::message).containsExactly("unknown machine 42");
    }

    @Test
    void rejectsNonPositiveCycle() {
        var problems = validator.validate(List.of(valid(1, 0), valid(1, -3)), Set.of(1)::contains);
        assertThat(problems).hasSize(2);
        assertThat(problems.get(1).index()).isEqualTo(1);
        assertThat(problems.get(1).message()).contains("positive");
    }

    @Test
    void rejectsMissingSensor() {
        Map<String, Double> sensors = allSensors();
        sensors.remove("s7");
        sensors.put("s21", null);
        var r = new ReadingRequest(1, 5, null, List.of(0.0, 0.0, 100.0), sensors);
        var problems = validator.validate(List.of(r), Set.of(1)::contains);
        assertThat(problems).extracting(ReadingValidator.Problem::message).containsExactly("missing sensors [s7, s21]");
    }

    @Test
    void rejectsWrongSettingCount() {
        var r = new ReadingRequest(1, 5, null, List.of(0.0), allSensors());
        var problems = validator.validate(List.of(r), Set.of(1)::contains);
        assertThat(problems).extracting(ReadingValidator.Problem::message).containsExactly("settings must have exactly 3 values");
    }

    @Test
    void reportsEveryProblemInABatchWithItsIndex() {
        var problems = validator.validate(List.of(valid(1, 1), valid(9, 0)), Set.of(1)::contains);
        assertThat(problems).extracting(ReadingValidator.Problem::index).containsExactly(1, 1);
    }
}
