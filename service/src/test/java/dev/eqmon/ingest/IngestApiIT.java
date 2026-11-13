package dev.eqmon.ingest;

import static org.assertj.core.api.Assertions.assertThat;

import dev.eqmon.machines.MachineRepository;
import dev.eqmon.support.IntegrationTestBase;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Stage 1: POST /api/readings against a real PostgreSQL. */
class IngestApiIT extends IntegrationTestBase {

    @Autowired TestRestTemplate http;
    @Autowired MachineRepository machines;
    @Autowired ReadingRepository readings;

    @Autowired JdbcClient jdbc;

    @BeforeEach
    void fleet() {
        jdbc.sql("delete from readings").update();
        http.put("/api/machines/1", Map.of("name", "engine-001"));
        http.put("/api/machines/2", null);
    }

    static Map<String, Object> reading(int machine, int cycle) {
        Map<String, Double> sensors = new HashMap<>();
        for (int i = 1; i <= 21; i++) {
            sensors.put("s" + i, 100.0 + i + cycle * 0.01);
        }
        return Map.of("machineId", machine, "cycle", cycle, "settings", List.of(-0.0007, -0.0004, 100.0), "sensors", sensors);
    }

    @Test
    void storesASingleReadingAndIgnoresTheDuplicate() {
        ResponseEntity<Map> first = http.postForEntity("/api/readings", reading(1, 1), Map.class);
        assertThat(first.getStatusCode()).isEqualTo(HttpStatus.ACCEPTED);
        assertThat(first.getBody()).containsEntry("received", 1).containsEntry("inserted", 1).containsEntry("duplicates", 0);

        ResponseEntity<Map> again = http.postForEntity("/api/readings", reading(1, 1), Map.class);
        assertThat(again.getStatusCode()).isEqualTo(HttpStatus.ACCEPTED);
        assertThat(again.getBody()).containsEntry("inserted", 0).containsEntry("duplicates", 1);
        assertThat(readings.countForMachine(1)).isEqualTo(1);
    }

    @Test
    void storesABatchInOneCall() {
        List<Map<String, Object>> batch = List.of(reading(1, 10), reading(1, 11), reading(2, 1));
        ResponseEntity<Map> r = http.postForEntity("/api/readings", batch, Map.class);
        assertThat(r.getStatusCode()).isEqualTo(HttpStatus.ACCEPTED);
        assertThat(r.getBody()).containsEntry("inserted", 3);
        assertThat(readings.countForMachine(1)).isEqualTo(2);
        assertThat(readings.countForMachine(2)).isEqualTo(1);
    }

    @Test
    void rejectsUnknownMachineWithAllProblemsListed() {
        List<Map<String, Object>> batch = List.of(reading(1, 1), reading(77, 1));
        ResponseEntity<Map> r = http.postForEntity("/api/readings", batch, Map.class);
        assertThat(r.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(r.getBody().toString()).contains("unknown machine 77");
        assertThat(readings.count()).isZero();
    }

    @Test
    void rejectsNonPositiveCycleAndMissingSensor() {
        Map<String, Object> bad = new HashMap<>(reading(1, 0));
        Map<String, Double> sensors = new HashMap<>((Map<String, Double>) bad.get("sensors"));
        sensors.remove("s4");
        bad.put("sensors", sensors);
        ResponseEntity<Map> r = http.postForEntity("/api/readings", bad, Map.class);
        assertThat(r.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(r.getBody().toString()).contains("positive").contains("missing sensors [s4]");
    }

    @Test
    void rejectsAnEmptyBatch() {
        ResponseEntity<Map> r = http.postForEntity("/api/readings", List.of(), Map.class);
        assertThat(r.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
    }
}
