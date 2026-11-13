package dev.eqmon;

import static org.assertj.core.api.Assertions.assertThat;

import dev.eqmon.support.IntegrationTestBase;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Stage 0 "done when": the health check answers 200 and the first migration has run. */
class HealthEndpointIT extends IntegrationTestBase {

    @Autowired TestRestTemplate http;
    @Autowired JdbcClient jdbc;

    @Test
    void healthIsUp() {
        ResponseEntity<String> r = http.getForEntity("/actuator/health", String.class);
        assertThat(r.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(r.getBody()).contains("\"status\":\"UP\"");
    }

    @Test
    void machinesTableExists() {
        Integer n = jdbc.sql("select count(*) from information_schema.tables where table_name = 'machines'")
                .query(Integer.class).single();
        assertThat(n).isEqualTo(1);
    }
}
