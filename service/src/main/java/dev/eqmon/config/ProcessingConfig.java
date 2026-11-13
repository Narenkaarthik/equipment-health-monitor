package dev.eqmon.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.eqmon.ingest.ReadingSink;
import dev.eqmon.processing.FeatureConsumer;
import dev.eqmon.processing.InMemoryWindowStateStore;
import dev.eqmon.processing.Processor;
import dev.eqmon.processing.RedisWindowStateStore;
import dev.eqmon.processing.WindowStateStore;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.data.redis.core.StringRedisTemplate;

/** Wires the processor. Window state lives in Redis unless {@code monitor.window.store=memory}. */
@Configuration
public class ProcessingConfig {

    @Bean
    @ConditionalOnProperty(name = "monitor.window.store", havingValue = "redis", matchIfMissing = true)
    WindowStateStore redisWindowStateStore(StringRedisTemplate redis, ObjectMapper json) {
        return new RedisWindowStateStore(redis, json);
    }

    @Bean
    @ConditionalOnProperty(name = "monitor.window.store", havingValue = "memory")
    WindowStateStore inMemoryWindowStateStore() {
        return new InMemoryWindowStateStore();
    }

    @Bean
    Processor processor(@Value("${monitor.window.size:30}") int windowSize, WindowStateStore store,
            List<FeatureConsumer> consumers, MeterRegistry metrics) {
        return new Processor(windowSize, store, consumers, metrics);
    }

    /** Direct pipeline (stages 1-4): the ingest request hands readings straight to the processor. */
    @Bean
    @Primary
    @ConditionalOnMissingBean(name = "kafkaReadingSink")
    ReadingSink directSink(Processor processor) {
        return processor;
    }
}
