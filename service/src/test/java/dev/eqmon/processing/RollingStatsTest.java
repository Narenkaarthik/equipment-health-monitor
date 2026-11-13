package dev.eqmon.processing;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

import java.util.Random;
import org.junit.jupiter.api.Test;

class RollingStatsTest {

    /** Same hand-computed case as tests/test_features.py: x = [1, 2, 4, 8], W = 3. */
    @Test
    void matchesHandComputedValues() {
        RollingStats s = new RollingStats(3);
        s.add(1);
        assertThat(s.mean()).isEqualTo(1.0);
        assertThat(s.std()).isEqualTo(0.0);
        assertThat(s.slope()).isEqualTo(0.0);
        s.add(2);
        assertThat(s.mean()).isEqualTo(1.5);
        assertThat(s.std()).isEqualTo(0.5);
        assertThat(s.slope()).isEqualTo(1.0);
        s.add(4);
        assertThat(s.mean()).isCloseTo(7.0 / 3, within(1e-12));
        assertThat(s.std()).isCloseTo(Math.sqrt(14.0 / 9), within(1e-12));
        assertThat(s.slope()).isCloseTo(1.5, within(1e-12));
        s.add(8); // window is now [2, 4, 8]
        assertThat(s.size()).isEqualTo(3);
        assertThat(s.mean()).isCloseTo(14.0 / 3, within(1e-12));
        assertThat(s.std()).isCloseTo(Math.sqrt(56.0 / 9), within(1e-12));
        assertThat(s.slope()).isCloseTo(3.0, within(1e-12));
    }

    @Test
    void incrementalEqualsBruteForceOverALongNoisyStream() {
        Random rnd = new Random(7);
        int w = 30;
        RollingStats s = new RollingStats(w);
        double[] all = new double[5000];
        double level = 9046.0;
        for (int k = 0; k < all.length; k++) {
            level += rnd.nextGaussian() * 0.05;
            all[k] = level + rnd.nextGaussian() * 3;
            s.add(all[k]);
            int start = Math.max(0, k + 1 - w);
            double[] expected = bruteForce(all, start, k + 1);
            assertThat(s.mean()).as("mean at %d", k).isCloseTo(expected[0], within(1e-9));
            assertThat(s.std()).as("std at %d", k).isCloseTo(expected[1], within(1e-9));
            assertThat(s.slope()).as("slope at %d", k).isCloseTo(expected[2], within(1e-9));
        }
    }

    @Test
    void constantSensorHasExactlyZeroStdAndSlope() {
        RollingStats s = new RollingStats(30);
        for (int i = 0; i < 400; i++) {
            s.add(518.67);
            assertThat(s.std()).isEqualTo(0.0);
            assertThat(s.slope()).isEqualTo(0.0);
            assertThat(s.mean()).isEqualTo(518.67);
        }
    }

    static double[] bruteForce(double[] x, int from, int to) {
        int n = to - from;
        double mean = 0;
        for (int i = from; i < to; i++) {
            mean += x[i];
        }
        mean /= n;
        double var = 0;
        for (int i = from; i < to; i++) {
            var += (x[i] - mean) * (x[i] - mean);
        }
        double std = Math.sqrt(var / n);
        double slope = 0;
        if (n >= 2) {
            double pm = (n - 1) / 2.0, sxy = 0, sxx = 0;
            for (int i = 0; i < n; i++) {
                sxy += (i - pm) * (x[from + i] - mean);
                sxx += (i - pm) * (i - pm);
            }
            slope = sxy / sxx;
        }
        return new double[] {mean, std, slope};
    }
}
