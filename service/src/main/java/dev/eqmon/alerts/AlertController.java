package dev.eqmon.alerts;

import java.time.Clock;
import java.util.List;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** {@code GET /api/alerts?status=open|closed|all} and {@code POST /api/alerts/{id}/acknowledge}. */
@RestController
@RequestMapping("/api/alerts")
public class AlertController {

    private final AlertRepository alerts;
    private final AlertEngine engine;
    private final Clock clock;

    public AlertController(AlertRepository alerts, AlertEngine engine, Clock clock) {
        this.alerts = alerts;
        this.engine = engine;
        this.clock = clock;
    }

    @GetMapping
    public List<Alert> list(@RequestParam(defaultValue = "open") String status, @RequestParam(defaultValue = "200") int limit) {
        return alerts.list(status, Math.min(Math.max(limit, 1), 1000));
    }

    @PostMapping("/{id}/acknowledge")
    public ResponseEntity<Map<String, Object>> acknowledge(@PathVariable long id) {
        if (!engine.acknowledge(id, clock.instant())) {
            return ResponseEntity.notFound().build();
        }
        Alert a = alerts.find(id).orElseThrow();
        return ResponseEntity.ok(Map.of("id", id, "acknowledgedAt", a.acknowledgedAt().toString()));
    }
}
