package dev.eqmon.query;

import static org.assertj.core.api.Assertions.assertThat;

import dev.eqmon.processing.Processor;
import dev.eqmon.processing.WindowStateStore;
import dev.eqmon.support.IntegrationTestBase;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.simple.JdbcClient;

/** The dashboard's read API: fleet list, paginated history, health history, alerts, acknowledge, SSE. */
class QueryApiIT extends IntegrationTestBase {

    @Autowired TestRestTemplate http;
    @Autowired JdbcClient jdbc;
    @Autowired WindowStateStore store;
    @Autowired Processor processor;
    @LocalServerPort int port;

    @BeforeEach
    void seed() {
        jdbc.sql("delete from alerts").update();
        jdbc.sql("delete from health_scores").update();
        jdbc.sql("delete from readings").update();
        jdbc.sql("update machines set status = 'HEALTHY'").update();
        store.clear();
        processor.forgetInMemoryState();
        http.put("/api/machines/3", Map.of("name", "engine-003"));
        for (int c = 1; c <= 45; c++) {
            http.postForEntity("/api/readings", reading(3, c), Map.class);
        }
    }

    static Map<String, Object> reading(int machine, int cycle) {
        Map<String, Double> sensors = new HashMap<>();
        for (int i = 1; i <= 21; i++) {
            sensors.put("s" + i, 100.0 * i + cycle);
        }
        return Map.of("machineId", machine, "cycle", cycle, "settings", List.of(0.0, 0.0, 100.0), "sensors", sensors);
    }

    @Test
    void fleetListsTheMachineWithItsLatestScore() {
        ResponseEntity<List> r = http.getForEntity("/api/machines", List.class);
        assertThat(r.getStatusCode()).isEqualTo(HttpStatus.OK);
        Map<String, Object> m = ((List<Map<String, Object>>) r.getBody()).stream()
                .filter(x -> ((Integer) x.get("id")) == 3).findFirst().orElseThrow();
        assertThat(m.get("lastCycle")).isEqualTo(45);
        assertThat(m.get("predictedRul")).isNotNull();
        assertThat(m.get("modelVersion")).asString().startsWith("gbr-");
    }

    @Test
    void readingHistoryIsPaginatedAndFiltered() {
        Map<String, Object> page1 = http.getForObject("/api/machines/3/readings?sensor=s2&from=1&limit=20", Map.class);
        assertThat((List<?>) page1.get("points")).hasSize(20);
        assertThat(page1.get("hasMore")).isEqualTo(true);
        assertThat(page1.get("nextFrom")).isEqualTo(21);
        Map<String, Object> first = (Map<String, Object>) ((List<?>) page1.get("points")).get(0);
        assertThat(first.get("cycle")).isEqualTo(1);
        assertThat((Double) first.get("value")).isEqualTo(201.0);
        Map<String, Object> page3 = http.getForObject("/api/machines/3/readings?sensor=s2&from=41&limit=20", Map.class);
        assertThat((List<?>) page3.get("points")).hasSize(5);
        assertThat(page3.get("hasMore")).isEqualTo(false);
        Map<String, Object> window = http.getForObject("/api/machines/3/readings?sensor=s2&from=10&to=12", Map.class);
        assertThat((List<?>) window.get("points")).hasSize(3);
    }

    @Test
    void unknownSensorIsABadRequestNotAnInjection() {
        ResponseEntity<String> r = http.getForEntity("/api/machines/3/readings?sensor=s1;drop table readings", String.class);
        assertThat(r.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(jdbc.sql("select count(*) from readings").query(Long.class).single()).isEqualTo(45L);
    }

    @Test
    void healthHistoryAndMachineDetail() {
        Map<String, Object> h = http.getForObject("/api/machines/3/health?from=40", Map.class);
        assertThat((List<?>) h.get("points")).hasSize(6);
        Map<String, Object> one = http.getForObject("/api/machines/3", Map.class);
        assertThat(one.get("maxCycle")).isEqualTo(45);
        assertThat(one.get("readings")).isEqualTo(45);
        assertThat(http.getForEntity("/api/machines/999", String.class).getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
    }

    @Test
    void alertsListAndAcknowledge() {
        jdbc.sql("insert into alerts (machine_id, rule, severity, detail, opened_cycle, opened_at) values (3, 'rul_threshold', 'WARNING', 'test', 45, now())").update();
        long id = jdbc.sql("select id from alerts where machine_id = 3").query(Long.class).single();
        List<Map<String, Object>> open = http.getForObject("/api/alerts?status=open", List.class);
        assertThat(open).extracting(a -> ((Number) a.get("id")).longValue()).contains(id);
        assertThat(http.postForEntity("/api/alerts/" + id + "/acknowledge", null, Map.class).getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(http.postForEntity("/api/alerts/999999/acknowledge", null, Map.class).getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
        List<Map<String, Object>> closed = http.getForObject("/api/alerts?status=closed", List.class);
        assertThat(closed).isEmpty();
    }

    @Test
    void streamSendsServerSentEvents() throws Exception {
        HttpURLConnection c = (HttpURLConnection) URI.create("http://localhost:" + port + "/api/stream").toURL().openConnection();
        c.setReadTimeout(10000);
        assertThat(c.getContentType()).startsWith("text/event-stream");
        try (BufferedReader in = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8))) {
            assertThat(in.readLine()).isEqualTo("event:hello");
            http.postForEntity("/api/readings", reading(3, 46), Map.class);
            String line;
            boolean sawScore = false;
            for (int i = 0; i < 20 && (line = in.readLine()) != null; i++) {
                if (line.equals("event:score")) {
                    sawScore = true;
                    break;
                }
            }
            assertThat(sawScore).isTrue();
        } finally {
            c.disconnect();
        }
    }
}
