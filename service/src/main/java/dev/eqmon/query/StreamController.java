package dev.eqmon.query;

import dev.eqmon.alerts.AlertEvent;
import dev.eqmon.model.HealthScore;
import dev.eqmon.model.HealthScoreListener;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.context.event.EventListener;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * {@code GET /api/stream}: Server-Sent Events. Event types: {@code status} (machine status changed),
 * {@code alert} (opened, closed, acknowledged) and {@code score} (a new predicted RUL).
 * One-way, text, auto-reconnecting in every browser: enough for a dashboard (docs/decisions/0006).
 */
@RestController
public class StreamController implements HealthScoreListener {

    private final List<SseEmitter> clients = new CopyOnWriteArrayList<>();

    @GetMapping(path = "/api/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream() {
        SseEmitter emitter = new SseEmitter(0L);
        clients.add(emitter);
        emitter.onCompletion(() -> clients.remove(emitter));
        emitter.onTimeout(() -> clients.remove(emitter));
        emitter.onError(e -> clients.remove(emitter));
        send(emitter, "hello", Map.of("clients", clients.size()));
        return emitter;
    }

    @EventListener
    public void onAlert(AlertEvent e) {
        if (e.type() == AlertEvent.Type.STATUS) {
            broadcast("status", Map.of("machineId", e.machineId(), "status", e.status()));
        } else {
            broadcast("alert", Map.of("type", e.type().name(), "machineId", e.machineId(), "alert", e.alert()));
        }
    }

    @Override
    public void onScore(HealthScore s) {
        if (!clients.isEmpty()) {
            broadcast("score", Map.of("machineId", s.machineId(), "cycle", s.cycle(), "predictedRul", s.predictedRul()));
        }
    }

    public int clientCount() {
        return clients.size();
    }

    private void broadcast(String name, Object data) {
        for (SseEmitter c : clients) {
            send(c, name, data);
        }
    }

    private void send(SseEmitter c, String name, Object data) {
        try {
            c.send(SseEmitter.event().name(name).data(data, MediaType.APPLICATION_JSON));
        } catch (IOException | IllegalStateException ex) {
            clients.remove(c);
        }
    }
}
