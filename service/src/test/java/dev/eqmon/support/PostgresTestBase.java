package dev.eqmon.support;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.DockerClientFactory;
import org.testcontainers.postgresql.PostgreSQLContainer;

/**
 * Integration tests run against a real PostgreSQL.
 *
 * <p>Order of preference: an explicitly provided database ({@code MONITOR_TEST_DB_URL}, used on a
 * developer machine without Docker), otherwise a Testcontainers PostgreSQL 17 (used in CI). The
 * schema is cleaned and re-migrated before each test class, so reruns are deterministic.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Import(TestDbConfig.class)
public abstract class PostgresTestBase {

    private static final String ENV_URL = "MONITOR_TEST_DB_URL";
    private static final PostgreSQLContainer CONTAINER;

    static {
        if (System.getenv(ENV_URL) == null && DockerClientFactory.instance().isDockerAvailable()) {
            CONTAINER = new PostgreSQLContainer("postgres:17-alpine");
            CONTAINER.start();
        } else {
            CONTAINER = null;
        }
    }

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        if (CONTAINER != null) {
            registry.add("spring.datasource.url", CONTAINER::getJdbcUrl);
            registry.add("spring.datasource.username", CONTAINER::getUsername);
            registry.add("spring.datasource.password", CONTAINER::getPassword);
        } else {
            String url = System.getenv(ENV_URL);
            if (url == null) {
                throw new IllegalStateException(
                        "No Docker and no " + ENV_URL + ": integration tests need a PostgreSQL");
            }
            registry.add("spring.datasource.url", () -> url);
            registry.add("spring.datasource.username", () -> envOr("MONITOR_TEST_DB_USER", "postgres"));
            registry.add("spring.datasource.password", () -> envOr("MONITOR_TEST_DB_PASSWORD", "postgres"));
        }
        registry.add("spring.flyway.clean-disabled", () -> "false");
    }

    private static String envOr(String name, String fallback) {
        String v = System.getenv(name);
        return v == null ? fallback : v;
    }
}
