package dev.eqmon.model;

import dev.eqmon.ingest.Reading;
import dev.eqmon.processing.FeatureConsumer;
import dev.eqmon.processing.FeatureVector;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Clock;
import java.util.List;
import java.util.concurrent.TimeUnit;

/** Scores every feature vector, stores the health score and tells the listeners. */
public class ScoringService implements FeatureConsumer {

    private final RulModel model;
    private final HealthScoreRepository scores;
    private final List<HealthScoreListener> listeners;
    private final Clock clock;
    private final Timer inference;

    public ScoringService(RulModel model, HealthScoreRepository scores, List<HealthScoreListener> listeners,
            Clock clock, MeterRegistry metrics) {
        this.model = model;
        this.scores = scores;
        this.listeners = List.copyOf(listeners);
        this.clock = clock;
        this.inference = metrics.timer("monitor.inference.time");
    }

    @Override
    public void accept(Reading reading, FeatureVector features) {
        long t0 = System.nanoTime();
        double rul = model.predict(features);
        inference.record(System.nanoTime() - t0, TimeUnit.NANOSECONDS);
        HealthScore score = new HealthScore(reading.machineId(), reading.cycle(), rul, model.version(),
                features.windowRows(), clock.instant());
        scores.insert(score);
        for (HealthScoreListener l : listeners) {
            l.onScore(score);
        }
    }

    public String modelVersion() {
        return model.version();
    }
}
