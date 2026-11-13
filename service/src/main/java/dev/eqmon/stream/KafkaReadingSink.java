package dev.eqmon.stream;

import dev.eqmon.ingest.Reading;
import dev.eqmon.ingest.ReadingSink;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;

/** Publishes each stored reading with the machine id as key; the HTTP request returns without waiting for the processor. */
public class KafkaReadingSink implements ReadingSink {

    private static final Logger log = LoggerFactory.getLogger(KafkaReadingSink.class);

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
        for (Reading r : readings) {
            template.send(topic, Integer.toString(r.machineId()), json.write(r)).whenComplete((result, ex) -> {
                if (ex == null) {
                    published.increment();
                } else {
                    failed.increment();
                    log.error("publish failed for machine {} cycle {}: {}", r.machineId(), r.cycle(), ex.toString());
                }
            });
        }
    }
}
