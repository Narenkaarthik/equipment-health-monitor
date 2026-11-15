package dev.eqmon.machines;

import static org.assertj.core.api.Assertions.assertThat;

import dev.eqmon.support.IntegrationTestBase;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Registration refuses markup and nonsense ids; the ingest cache sees machines registered elsewhere. */
class MachineRegistrationIT extends IntegrationTestBase {

    @Autowired TestRestTemplate http;
    @Autowired KnownMachines known;
    @Autowired JdbcClient jdbc;

    ResponseEntity<Map> put(int id, String name) {
        return http.exchange("/api/machines/" + id, HttpMethod.PUT, new HttpEntity<>(Map.of("name", name)), Map.class);
    }

    @Test
    void refusesMarkupInNames() {
        assertThat(put(201, "<img src=x onerror=alert(1)>").getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(put(201, "x".repeat(65)).getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(jdbc.sql("select count(*) from machines where id = 201").query(Long.class).single()).isZero();
    }

    @Test
    void acceptsPlainNamesAndRefusesNonPositiveIds() {
        assertThat(put(202, "Engine 202.b_x-1").getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(put(0, "zero").getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
    }

    @Test
    void cacheFindsAMachineRegisteredBehindItsBack() {
        known.clear();
        // as if another ingest instance had registered it
        jdbc.sql("insert into machines (id, name) values (203, 'elsewhere') on conflict do nothing").update();
        assertThat(known.contains(203)).isTrue();
        assertThat(known.contains(999_999)).isFalse();
    }
}
