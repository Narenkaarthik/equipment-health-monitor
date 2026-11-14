package dev.eqmon.stream;

import dev.eqmon.processing.Processor;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;

/**
 * Consumes the {@code readings} topic and drives the processor. Idempotent by construction: a
 * redelivered record has {@code cycle <= last} for its machine and is classified LATE (no window change,
 * no score, no alert), and every table it would touch has a primary key on (machine, cycle).
 */
public class ReadingConsumer {

    private final Processor processor;
    private final ReadingJson json;
    private final Counter consumed;

    public ReadingConsumer(Processor processor, ReadingJson json, MeterRegistry metrics) {
        this.processor = processor;
        this.json = json;
        this.consumed = metrics.counter("monitor.kafka.consumed");
    }

    @KafkaListener(topics = "${monitor.kafka.topic:readings}", groupId = "${monitor.kafka.group:processor}")
    public void onRecord(ConsumerRecord<String, String> record) {
        consumed.increment();
        processor.process(json.read(record.value()));
    }
}
