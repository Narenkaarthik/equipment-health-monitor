package dev.eqmon.config;

import com.fasterxml.jackson.databind.DeserializationFeature;
import dev.eqmon.ingest.ReadingSink;
import java.time.Clock;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Small cross-cutting beans. */
@Configuration
public class AppConfig {

    /** A single posted reading ({@code {...}}) is accepted as a batch of one ({@code [{...}]}). */
    @Bean
    Jackson2ObjectMapperBuilderCustomizer singleValueAsArray() {
        return builder -> builder.featuresToEnable(DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY);
    }

    @Bean
    @ConditionalOnMissingBean
    Clock clock() {
        return Clock.systemUTC();
    }

    /** Stage 1 default: readings are stored and go nowhere else. Replaced by the processor in stage 2. */
    @Bean
    @ConditionalOnMissingBean(ReadingSink.class)
    ReadingSink noopSink() {
        return readings -> { };
    }
}
