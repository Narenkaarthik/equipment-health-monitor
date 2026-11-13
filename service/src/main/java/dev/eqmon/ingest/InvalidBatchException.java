package dev.eqmon.ingest;

import java.util.List;

/** Thrown when any reading in a batch fails validation; carries every problem found. */
public class InvalidBatchException extends RuntimeException {

    private final List<ReadingValidator.Problem> problems;

    public InvalidBatchException(List<ReadingValidator.Problem> problems) {
        super(problems.size() + " invalid reading(s): " + problems.get(0).message());
        this.problems = List.copyOf(problems);
    }

    public List<ReadingValidator.Problem> problems() {
        return problems;
    }
}
