package dev.eqmon.stream;

import dev.eqmon.ingest.Reading;
import dev.eqmon.ingest.ReadingSink;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;

/**
 * Publishes each stored reading with the machine id as key. The batch is sent in one go and the call
 * returns once the broker has acknowledged every message ({@code acks=all}), so a 202 means "durably
 * queued". If the broker does not acknowledge, the exception rolls back the ingest transaction and the
 * client sees an error and can retry; the readings table never holds a row that was not queued.
 * The request does not wait for the processor.
 */
public class KafkaReadingSink implements ReadingSink {

    private final KafkaTemplate<String, String> template;
    private final ReadingJson json;
    private final String topic;
    private final Counter published;
    private final Counter failed;

    public KafkaReadingSink(KafkaTemplate<String, String> template, ReadingJson json, String topic, MeterRegistry metrics) {
        this.template = template;
        this.json = json;
        this.topic = topic;
        this.published = metrics.counter("monitor.kafka.published");
        this.failed = metrics.counter("monitor.kafka.publish_failed");
    }

    @Override
    public void accept(List<Reading> readings) {
        List<CompletableFuture<SendResult<String, String>>> sends = new ArrayList<>(readings.size());
        for (Reading r : readings) {
            sends.add(template.send(topic, Integer.toString(r.machineId()), json.write(r)));
        }
        try {
            CompletableFuture.allOf(sends.toArray(CompletableFuture[]::new)).get(10, TimeUnit.SECONDS);
            published.increment(readings.size());
        } catch (Exception e) {
            failed.increment(readings.size());
            if (e instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            throw new IllegalStateException("Kafka did not acknowledge the batch", e);
        }
    }
}
