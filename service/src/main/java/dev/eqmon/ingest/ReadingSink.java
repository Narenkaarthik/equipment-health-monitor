package dev.eqmon.ingest;

import java.util.List;

/**
 * Where validated, stored readings go next. Stage 1 has a no-op sink; stage 2 wires the in-process
 * processor; stage 5 swaps in a Kafka producer so the request returns as soon as the message is sent.
 */
@FunctionalInterface
public interface ReadingSink {
    void accept(List<Reading> readings);
}
