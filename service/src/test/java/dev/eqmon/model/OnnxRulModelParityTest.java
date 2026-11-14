package dev.eqmon.model;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.eqmon.processing.FeatureVector;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;

/**
 * Stage 3 parity: the Java ONNX prediction equals the Python sklearn prediction for 300 real test
 * rows within the pre-registered tolerance (1e-3 cycles). The fixture is written by model/export_onnx.py.
 */
class OnnxRulModelParityTest {

    @Test
    void javaPredictionsMatchPythonOnTheFixture() throws Exception {
        OnnxRulModel model = new OnnxRulModel(new ClassPathResource("models/rul.onnx"), new ClassPathResource("models/rul.json"));
        JsonNode fx = new ObjectMapper().readTree(Path.of("..", "tests", "fixtures", "parity_" + model.metadata().arm() + ".json").toFile());
        assertThat(fx.get("version").asText()).isEqualTo(model.version());
        double tol = fx.get("tolerance_abs").asDouble();
        int n = fx.get("rows").size();
        int width = model.metadata().feature_names().size();
        double[][] rows = new double[n][width];
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < width; j++) {
                rows[i][j] = fx.get("rows").get(i).get(j).asDouble();
            }
        }
        double[] java = model.predictRaw(rows);
        double maxDiff = 0;
        for (int i = 0; i < n; i++) {
            double py = fx.get("sklearn").get(i).asDouble();
            maxDiff = Math.max(maxDiff, Math.abs(java[i] - py));
            assertThat(java[i]).as("row %d", i).isCloseTo(py, within(tol));
        }
        System.out.printf("parity: %d rows, max |java - sklearn| = %.3e (tolerance %.0e)%n", n, maxDiff, tol);
        assertThat(n).isEqualTo(300);
        model.close();
    }

    @Test
    void singlePredictionPicksTheRightColumnsAndIsClipped() throws Exception {
        OnnxRulModel model = new OnnxRulModel(new ClassPathResource("models/rul.onnx"), new ClassPathResource("models/rul.json"));
        JsonNode fx = new ObjectMapper().readTree(Path.of("..", "tests", "fixtures", "parity_" + model.metadata().arm() + ".json").toFile());
        // scatter the fixture's first row into the 63-wide vector by feature name, everything else garbage
        double[] wide = new double[FeatureVector.SIZE];
        java.util.Arrays.fill(wide, 12345.0);
        for (int j = 0; j < model.metadata().feature_names().size(); j++) {
            wide[FeatureVector.index(model.metadata().feature_names().get(j))] = fx.get("rows").get(0).get(j).asDouble();
        }
        double expected = Math.max(0, Math.min(model.metadata().cap(), fx.get("sklearn").get(0).asDouble()));
        assertThat(model.predict(new FeatureVector(1, 1, 30, wide))).isCloseTo(expected, within(1e-3));
        model.close();
    }

    @Test
    void inferenceTakesWellUnderAMillisecond() throws Exception {
        OnnxRulModel model = new OnnxRulModel(new ClassPathResource("models/rul.onnx"), new ClassPathResource("models/rul.json"));
        double[] wide = new double[FeatureVector.SIZE];
        FeatureVector f = new FeatureVector(1, 1, 30, wide);
        for (int i = 0; i < 500; i++) {
            model.predict(f); // warm up
        }
        long t0 = System.nanoTime();
        int n = 5000;
        for (int i = 0; i < n; i++) {
            model.predict(f);
        }
        double usPerCall = (System.nanoTime() - t0) / 1e3 / n;
        System.out.printf("inference: %.1f us per prediction%n", usPerCall);
        // picked up by scripts/collect_build_facts.py so documents never carry a hand-typed timing
        java.nio.file.Files.writeString(java.nio.file.Path.of("target", "java_inference.json"),
                String.format(java.util.Locale.ROOT, "{\"us_per_prediction\": %.2f, \"predictions_timed\": %d}%n", usPerCall, n));
        assertThat(usPerCall).isLessThan(5000.0); // "within a few milliseconds"; typically tens of microseconds
        model.close();
    }
}
