package dev.eqmon.model;

import static org.assertj.core.api.Assertions.assertThat;

import dev.eqmon.processing.Processor;
import dev.eqmon.processing.WindowStateStore;
import dev.eqmon.support.IntegrationTestBase;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Stage 3 "done when": every ingested reading produces a stored predicted RUL. */
class ScoringIT extends IntegrationTestBase {

    @Autowired TestRestTemplate http;
    @Autowired HealthScoreRepository scores;
    @Autowired ScoringService scoring;
    @Autowired WindowStateStore store;
    @Autowired Processor processor;
    @Autowired JdbcClient jdbc;

    @BeforeEach
    void clean() {
        jdbc.sql("delete from health_scores").update();
        jdbc.sql("delete from readings").update();
        store.clear();
        processor.forgetInMemoryState();
        http.put("/api/machines/5", null);
    }

    static Map<String, Object> reading(int machine, int cycle) {
        Map<String, Double> sensors = new HashMap<>();
        double[] base = {518.67, 642.0, 1588.0, 1400.0, 14.62, 21.61, 554.0, 2388.0, 9050.0, 1.3, 47.4, 522.0, 2388.0,
                8135.0, 8.42, 0.03, 392, 2388, 100, 39.0, 23.4};
        for (int i = 1; i <= 21; i++) {
            sensors.put("s" + i, base[i - 1] + cycle * 0.01);
        }
        return Map.of("machineId", machine, "cycle", cycle, "settings", List.of(0.0, 0.0, 100.0), "sensors", sensors);
    }

    @Test
    void everyIngestedReadingGetsAScore() {
        for (int c = 1; c <= 35; c++) {
            assertThat(http.postForEntity("/api/readings", reading(5, c), Map.class).getStatusCode()).isEqualTo(HttpStatus.ACCEPTED);
        }
        assertThat(scores.count()).isEqualTo(35);
        HealthScore latest = scores.latest(5).orElseThrow();
        assertThat(latest.cycle()).isEqualTo(35);
        assertThat(latest.windowRows()).isEqualTo(30);
        assertThat(latest.modelVersion()).isEqualTo(scoring.modelVersion());
        assertThat(latest.predictedRul()).isBetween(0.0, 125.0);
    }

    @Test
    void duplicateReadingDoesNotProduceASecondScore() {
        http.postForEntity("/api/readings", reading(5, 1), Map.class);
        http.postForEntity("/api/readings", reading(5, 1), Map.class);
        assertThat(scores.count()).isEqualTo(1);
    }
}
