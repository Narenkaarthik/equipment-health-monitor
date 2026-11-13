package dev.eqmon.ingest;

import dev.eqmon.machines.MachineRepository;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Accepts a batch of readings: validates all of them, stores them in one batch insert, then hands
 * each one to the {@link ReadingSink} (the processor in stages 2-4, a Kafka producer in stage 5).
 * A batch is all-or-nothing: one invalid reading rejects the whole batch with every problem listed.
 */
@Service
public class IngestService {

    public record Result(int received, int inserted, int duplicates) {}

    private final ReadingValidator validator;
    private final MachineRepository machines;
    private final ReadingRepository readings;
    private final ReadingSink sink;
    private final Clock clock;

    public IngestService(ReadingValidator validator, MachineRepository machines, ReadingRepository readings,
            ReadingSink sink, Clock clock) {
        this.validator = validator;
        this.machines = machines;
        this.readings = readings;
        this.sink = sink;
        this.clock = clock;
    }

    @Transactional
    public Result ingest(List<ReadingRequest> batch) {
        Set<Integer> known = machines.ids();
        List<ReadingValidator.Problem> problems = validator.validate(batch, known);
        if (!problems.isEmpty()) {
            throw new InvalidBatchException(problems);
        }
        Instant now = clock.instant();
        List<Reading> valid = batch.stream().map(r -> Reading.from(r, now)).toList();
        int inserted = readings.insertAll(valid);
        sink.accept(valid);
        return new Result(batch.size(), inserted, batch.size() - inserted);
    }
}
