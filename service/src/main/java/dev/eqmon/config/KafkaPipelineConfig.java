package dev.eqmon.config;

import dev.eqmon.ingest.ReadingSink;
import dev.eqmon.processing.Processor;
import dev.eqmon.stream.KafkaReadingSink;
import dev.eqmon.stream.ReadingConsumer;
import dev.eqmon.stream.ReadingJson;
import io.micrometer.core.instrument.MeterRegistry;
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.config.TopicBuilder;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

/**
 * Stage 5: {@code monitor.pipeline=kafka} makes ingest publish to the {@code readings} topic and return,
 * and a consumer (when {@code monitor.consumer.enabled=true}) drive the processor.
 * Message key = machine id, so one machine's readings stay on one partition, in order.
 * A message that fails {@value #ATTEMPTS} times goes to {@code readings.DLT}.
 */
@Configuration
@ConditionalOnProperty(name = "monitor.pipeline", havingValue = "kafka")
public class KafkaPipelineConfig {

    public static final String TOPIC = "readings";
    public static final String DLT = "readings.DLT";
    static final int ATTEMPTS = 3;

    @Bean
    NewTopic readingsTopic(@Value("${monitor.kafka.partitions:6}") int partitions) {
        return TopicBuilder.name(TOPIC).partitions(partitions).replicas(1).build();
    }

    @Bean
    NewTopic readingsDlt() {
        return TopicBuilder.name(DLT).partitions(1).replicas(1).build();
    }

    @Bean
    ReadingJson readingJson(com.fasterxml.jackson.databind.ObjectMapper mapper) {
        return new ReadingJson(mapper);
    }

    @Bean(name = "kafkaReadingSink")
    @Primary
    ReadingSink kafkaReadingSink(KafkaTemplate<String, String> template, ReadingJson json, MeterRegistry metrics) {
        return new KafkaReadingSink(template, json, TOPIC, metrics);
    }

    @Bean
    @ConditionalOnProperty(name = "monitor.consumer.enabled", havingValue = "true", matchIfMissing = true)
    ReadingConsumer readingConsumer(Processor processor, ReadingJson json, MeterRegistry metrics) {
        return new ReadingConsumer(processor, json, metrics);
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String> kafkaListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory, KafkaTemplate<String, String> template,
            @Value("${monitor.kafka.partitions:6}") int partitions) {
        var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(partitions);
        // the offset is committed only after the processor has applied the record: at-least-once,
        // and the processor's ordering rule plus the primary keys make a redelivery a no-op
        factory.getContainerProperties().setAckMode(ContainerProperties.AckMode.RECORD);
        var recoverer = new DeadLetterPublishingRecoverer(template, (record, ex) -> new org.apache.kafka.common.TopicPartition(DLT, 0));
        var handler = new DefaultErrorHandler(recoverer, new FixedBackOff(200L, ATTEMPTS - 1L));
        factory.setCommonErrorHandler(handler);
        return factory;
    }
}
