package dev.eqmon.model;

import ai.onnxruntime.OnnxTensor;
import ai.onnxruntime.OrtEnvironment;
import ai.onnxruntime.OrtException;
import ai.onnxruntime.OrtSession;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.eqmon.processing.FeatureVector;
import java.io.IOException;
import java.io.InputStream;
import java.util.Map;
import org.springframework.core.io.Resource;

/**
 * In-process scoring with ONNX Runtime. The model's input columns are looked up by name in the
 * 63-wide feature vector, so the same processor serves a model trained on any sensor subset.
 * {@link OrtSession#run} is thread-safe; one session serves every machine.
 */
public final class OnnxRulModel implements RulModel, AutoCloseable {

    private final ModelMetadata meta;
    private final OrtEnvironment env;
    private final OrtSession session;
    private final int[] columns;

    public OnnxRulModel(Resource onnx, Resource metadata) throws IOException, OrtException {
        try (InputStream in = metadata.getInputStream()) {
            this.meta = new ObjectMapper().readValue(in, ModelMetadata.class);
        }
        this.env = OrtEnvironment.getEnvironment();
        OrtSession.SessionOptions opts = new OrtSession.SessionOptions();
        opts.setIntraOpNumThreads(1); // one small tree ensemble per call; parallelism comes from many machines
        try (InputStream in = onnx.getInputStream()) {
            this.session = env.createSession(in.readAllBytes(), opts);
        }
        this.columns = meta.feature_names().stream().mapToInt(FeatureVector::index).toArray();
    }

    @Override
    public String version() {
        return meta.version();
    }

    public ModelMetadata metadata() {
        return meta;
    }

    @Override
    public double predict(FeatureVector features) {
        double[][] input = new double[1][columns.length];
        for (int i = 0; i < columns.length; i++) {
            input[0][i] = features.features()[columns[i]];
        }
        return clip(predictRaw(input)[0]);
    }

    /** Batch prediction without clipping; used by the parity test. */
    public double[] predictRaw(double[][] rows) {
        try (OnnxTensor tensor = "float".equals(meta.input_type()) ? OnnxTensor.createTensor(env, toFloat(rows))
                : OnnxTensor.createTensor(env, rows);
                OrtSession.Result result = session.run(Map.of(meta.input_name(), tensor))) {
            Object value = result.get(0).getValue();
            double[] out = new double[rows.length];
            if (value instanceof double[][] d) {
                for (int i = 0; i < out.length; i++) {
                    out[i] = d[i][0];
                }
            } else if (value instanceof float[][] f) {
                for (int i = 0; i < out.length; i++) {
                    out[i] = f[i][0];
                }
            } else {
                throw new IllegalStateException("unexpected model output " + value.getClass());
            }
            return out;
        } catch (OrtException e) {
            throw new IllegalStateException("inference failed", e);
        }
    }

    private static float[][] toFloat(double[][] rows) {
        float[][] out = new float[rows.length][];
        for (int i = 0; i < rows.length; i++) {
            out[i] = new float[rows[i].length];
            for (int j = 0; j < rows[i].length; j++) {
                out[i][j] = (float) rows[i][j];
            }
        }
        return out;
    }

    private double clip(double rul) {
        return Math.max(0.0, Math.min(meta.cap(), rul));
    }

    @Override
    public void close() throws OrtException {
        session.close();
    }
}
