package dev.eqmon.processing;

import dev.eqmon.ingest.Reading;

/** Receives the features of every applied reading: the model scorer (stage 3), which feeds the alert engine (stage 4). */
@FunctionalInterface
public interface FeatureConsumer {
    void accept(Reading reading, FeatureVector features);
}
