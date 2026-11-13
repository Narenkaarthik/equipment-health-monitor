package dev.eqmon.config;

import dev.eqmon.alerts.AlertEngine;
import dev.eqmon.alerts.AlertEvent;
import dev.eqmon.alerts.AlertRepository;
import dev.eqmon.alerts.AlertRules;
import dev.eqmon.machines.MachineRepository;
import dev.eqmon.model.HealthScore;
import dev.eqmon.model.HealthScoreRepository;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Wires the alert engine as a listener of health scores; events go to Spring's event bus. */
@Configuration
@EnableConfigurationProperties(AlertRules.class)
public class AlertConfig {

    @Bean
    AlertEngine alertEngine(AlertRules rules, AlertRepository alerts, MachineRepository machines,
            HealthScoreRepository scores, ApplicationEventPublisher publisher) {
        return new AlertEngine(rules, alerts, machines::updateStatus, (AlertEvent e) -> publisher.publishEvent(e),
                (machineId, n) -> scores.history(machineId, 0, Integer.MAX_VALUE, Integer.MAX_VALUE).stream()
                        .skip(Math.max(0, scores.history(machineId, 0, Integer.MAX_VALUE, Integer.MAX_VALUE).size() - n))
                        .map(HealthScore::predictedRul).toList());
    }
}
