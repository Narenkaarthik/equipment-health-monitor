package dev.eqmon.support;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.DockerClientFactory;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.postgresql.PostgreSQLContainer;

/**
 * Integration tests run against a real PostgreSQL and a real Redis.
 *
 * <p>Order of preference: explicitly provided services ({@code MONITOR_TEST_DB_URL},
 * {@code MONITOR_TEST_REDIS_HOST}; a developer machine without Docker), otherwise Testcontainers
 * (CI). The schema is cleaned and re-migrated per test class, so reruns are deterministic.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Import(TestDbConfig.class)
public abstract class IntegrationTestBase {

    private static final String ENV_URL = "MONITOR_TEST_DB_URL";
    private static final String ENV_REDIS = "MONITOR_TEST_REDIS_HOST";
    private static final PostgreSQLContainer PG;
    private static final GenericContainer<?> REDIS;

    static {
        boolean docker = DockerClientFactory.instance().isDockerAvailable();
        if (System.getenv(ENV_URL) == null && docker) {
            PG = new PostgreSQLContainer("postgres:17-alpine");
            PG.start();
        } else {
            PG = null;
        }
        if (System.getenv(ENV_REDIS) == null && docker) {
            REDIS = new GenericContainer<>("redis:7-alpine").withExposedPorts(6379);
            REDIS.start();
        } else {
            REDIS = null;
        }
    }

    @DynamicPropertySource
    static void services(DynamicPropertyRegistry registry) {
        if (PG != null) {
            registry.add("spring.datasource.url", PG::getJdbcUrl);
            registry.add("spring.datasource.username", PG::getUsername);
            registry.add("spring.datasource.password", PG::getPassword);
        } else {
            String url = System.getenv(ENV_URL);
            if (url == null) {
                throw new IllegalStateException("No Docker and no " + ENV_URL + ": integration tests need a PostgreSQL");
            }
            registry.add("spring.datasource.url", () -> url);
            registry.add("spring.datasource.username", () -> envOr("MONITOR_TEST_DB_USER", "postgres"));
            registry.add("spring.datasource.password", () -> envOr("MONITOR_TEST_DB_PASSWORD", "postgres"));
        }
        if (REDIS != null) {
            registry.add("spring.data.redis.host", REDIS::getHost);
            registry.add("spring.data.redis.port", () -> REDIS.getMappedPort(6379));
        } else {
            registry.add("spring.data.redis.host", () -> envOr(ENV_REDIS, "localhost"));
            registry.add("spring.data.redis.port", () -> envOr("MONITOR_TEST_REDIS_PORT", "6379"));
        }
        registry.add("spring.flyway.clean-disabled", () -> "false");
    }

    private static String envOr(String name, String fallback) {
        String v = System.getenv(name);
        return v == null ? fallback : v;
    }
}
