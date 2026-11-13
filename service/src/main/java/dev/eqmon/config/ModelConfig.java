package dev.eqmon.config;

import ai.onnxruntime.OrtException;
import dev.eqmon.model.HealthScoreListener;
import dev.eqmon.model.HealthScoreRepository;
import dev.eqmon.model.OnnxRulModel;
import dev.eqmon.model.RulModel;
import dev.eqmon.model.ScoringService;
import io.micrometer.core.instrument.MeterRegistry;
import java.io.IOException;
import java.time.Clock;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;

/** Loads the ONNX model from the classpath (or a path given by {@code monitor.model.path}) and wires scoring. */
@Configuration
public class ModelConfig {

    @Bean(destroyMethod = "close")
    OnnxRulModel rulModel(@Value("${monitor.model.onnx:classpath:models/rul.onnx}") Resource onnx,
            @Value("${monitor.model.metadata:classpath:models/rul.json}") Resource metadata) throws IOException, OrtException {
        return new OnnxRulModel(onnx, metadata);
    }

    @Bean
    ScoringService scoringService(RulModel model, HealthScoreRepository scores, List<HealthScoreListener> listeners,
            Clock clock, MeterRegistry metrics) {
        return new ScoringService(model, scores, listeners, clock, metrics);
    }
}
