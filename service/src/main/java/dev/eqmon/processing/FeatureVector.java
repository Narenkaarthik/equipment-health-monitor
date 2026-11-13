package dev.eqmon.processing;

import java.util.ArrayList;
import java.util.List;

/**
 * The features of one machine at one cycle: for each sensor s1..s21 in order, [mean, std, slope]
 * over the window. {@code features.length == 63}. A model picks the columns it was trained on.
 */
public record FeatureVector(int machineId, int cycle, int windowRows, double[] features) {

    public static final String[] STATS = {"mean", "std", "slope"};
    public static final int SENSORS = 21;
    public static final int SIZE = SENSORS * STATS.length;

    public FeatureVector {
        features = features.clone();
        if (features.length != SIZE) {
            throw new IllegalArgumentException("expected " + SIZE + " features");
        }
    }

    /** Column names in the same order as the Python pipeline: s1_mean, s1_std, s1_slope, s2_mean, ... */
    public static List<String> names() {
        List<String> names = new ArrayList<>(SIZE);
        for (int s = 1; s <= SENSORS; s++) {
            for (String st : STATS) {
                names.add("s" + s + "_" + st);
            }
        }
        return names;
    }

    public static int index(String name) {
        int i = names().indexOf(name);
        if (i < 0) {
            throw new IllegalArgumentException("unknown feature " + name);
        }
        return i;
    }

    public double get(String name) {
        return features[index(name)];
    }
}
