package dev.eqmon.model;

import dev.eqmon.processing.FeatureVector;

/** Predicts remaining useful life (cycles) from a window's features. */
public interface RulModel {

    String version();

    /** @return predicted RUL, clipped to [0, cap] */
    double predict(FeatureVector features);
}
