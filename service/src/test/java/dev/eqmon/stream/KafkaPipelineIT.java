package dev.eqmon.stream;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import dev.eqmon.model.HealthScoreRepository;
import dev.eqmon.processing.Processor;
import dev.eqmon.processing.WindowStateStore;
import dev.eqmon.support.IntegrationTestBase;
import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.test.context.TestPropertySource;

/** Stage 5: ingest publishes, the consumer processes, duplicates change nothing, poison goes to the DLT. */
@TestPropertySource(properties = {"monitor.pipeline=kafka", "monitor.kafka.partitions=3", "monitor.kafka.group=it-processor", "monitor.kafka.topic=readings-it"})
class KafkaPipelineIT extends IntegrationTestBase {

    @Autowired TestRestTemplate http;
    @Autowired HealthScoreRepository scores;
    @Autowired WindowStateStore store;
    @Autowired Processor processor;
    @Autowired JdbcClient jdbc;
    @Autowired KafkaTemplate<String, String> kafka;
    @Autowired ReadingJson readingJson;
    @Value("${spring.kafka.bootstrap-servers}") String bootstrap;

    @BeforeEach
    void clean() {
        jdbc.sql("delete from alerts").update();
        jdbc.sql("delete from health_scores").update();
        jdbc.sql("delete from readings").update();
        store.clear();
        processor.forgetInMemoryState();
        http.put("/api/machines/9", null);
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
    void readingsFlowThroughKafkaInOrderAndDuplicatesChangeNothing() {
        for (int c = 1; c <= 40; c++) {
            assertThat(http.postForEntity("/api/readings", reading(9, c), Map.class).getStatusCode()).isEqualTo(HttpStatus.ACCEPTED);
        }
        await().atMost(Duration.ofSeconds(60)).untilAsserted(() -> assertThat(scores.count()).isEqualTo(40));
        assertThat(scores.latest(9).orElseThrow().cycle()).isEqualTo(40);

        // the same 40 readings again: HTTP accepts them (duplicates), Kafka delivers them, the processor ignores them
        for (int c = 1; c <= 40; c++) {
            http.postForEntity("/api/readings", reading(9, c), Map.class);
        }
        // and a raw redelivery straight onto the topic
        kafka.send("readings-it", "9", readingJson
                .write(dev.eqmon.ingest.Reading.from(new dev.eqmon.ingest.ReadingRequest(9, 40, null, List.of(0.0, 0.0, 100.0),
                        (Map<String, Double>) reading(9, 40).get("sensors")), java.time.Instant.EPOCH)));
        await().pollDelay(Duration.ofSeconds(3)).atMost(Duration.ofSeconds(30)).untilAsserted(() -> {
            assertThat(scores.count()).isEqualTo(40);
            assertThat(jdbc.sql("select count(*) from readings").query(Long.class).single()).isEqualTo(40L);
        });
    }

    @Test
    void malformedMessageLandsOnTheDeadLetterTopic() {
        kafka.send("readings-it", "9", "{not json");
        Properties p = new Properties();
        p.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrap);
        p.put(ConsumerConfig.GROUP_ID_CONFIG, "dlt-check-" + System.nanoTime());
        p.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        p.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
        p.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
        try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(p)) {
            consumer.subscribe(List.of("readings-it.DLT"));
            await().atMost(Duration.ofSeconds(60)).untilAsserted(() -> {
                ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(500));
                assertThat(records.count()).isGreaterThan(0);
                assertThat(records.iterator().next().value()).isEqualTo("{not json");
            });
        }
        assertThat(scores.count()).isZero();
    }
}
