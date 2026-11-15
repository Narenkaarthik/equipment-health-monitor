package dev.eqmon.ingest;

import java.util.ArrayList;
import java.util.List;
import java.util.function.IntPredicate;
import org.springframework.stereotype.Component;

/** Validates a batch of readings: known machine, positive cycle, three settings, all 21 sensors present. */
@Component
public class ReadingValidator {

    public record Problem(int index, String message) {}

    /**
     * @param batch the readings as posted
     * @param knownMachines true for ids that exist in the fleet
     * @return every problem found; empty means the whole batch is acceptable
     */
    public List<Problem> validate(List<ReadingRequest> batch, IntPredicate knownMachines) {
        List<Problem> problems = new ArrayList<>();
        for (int i = 0; i < batch.size(); i++) {
            ReadingRequest r = batch.get(i);
            if (r == null) {
                problems.add(new Problem(i, "reading is null"));
                continue;
            }
            if (r.machineId() == null) {
                problems.add(new Problem(i, "machineId is required"));
            } else if (!knownMachines.test(r.machineId())) {
                problems.add(new Problem(i, "unknown machine " + r.machineId()));
            }
            if (r.cycle() == null) {
                problems.add(new Problem(i, "cycle is required"));
            } else if (r.cycle() <= 0) {
                problems.add(new Problem(i, "cycle must be positive, got " + r.cycle()));
            }
            if (r.settings() == null || r.settings().size() != ReadingRequest.SETTING_COUNT) {
                problems.add(new Problem(i, "settings must have exactly " + ReadingRequest.SETTING_COUNT + " values"));
            } else if (r.settings().stream().anyMatch(v -> v == null || v.isNaN())) {
                problems.add(new Problem(i, "settings contain a missing value"));
            }
            if (r.sensors() == null) {
                problems.add(new Problem(i, "sensors are required"));
            } else {
                List<String> missing = new ArrayList<>();
                for (int s = 1; s <= ReadingRequest.SENSOR_COUNT; s++) {
                    Double v = r.sensors().get(ReadingRequest.sensorKey(s));
                    if (v == null || v.isNaN()) {
                        missing.add(ReadingRequest.sensorKey(s));
                    }
                }
                if (!missing.isEmpty()) {
                    problems.add(new Problem(i, "missing sensors " + missing));
                }
            }
        }
        return problems;
    }
}
