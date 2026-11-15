package dev.eqmon.query;

import dev.eqmon.alerts.AlertEvent;
import dev.eqmon.model.HealthScore;
import dev.eqmon.model.HealthScoreListener;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import jakarta.annotation.PreDestroy;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import org.springframework.context.event.EventListener;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * {@code GET /api/stream}: Server-Sent Events. Event types: {@code status} (machine status changed),
 * {@code alert} (opened, closed, acknowledged) and {@code score} (a new predicted RUL).
 *
 * <p>Writing to a browser can block, so events are handed to one sender thread and the processing thread never
 * waits for a client. One thread keeps the events in order. If the sender falls behind (a slow client, a burst
 * of scores), {@code score} events are dropped and counted ({@code monitor.stream.dropped}): the next score
 * supersedes them. {@code status} and {@code alert} events are never dropped; when the queue is full the
 * caller sends them itself.
 */
@RestController
public class StreamController implements HealthScoreListener {

    static final int QUEUE = 10_000;

    private final List<SseEmitter> clients = new CopyOnWriteArrayList<>();
    private final ThreadPoolExecutor sender = new ThreadPoolExecutor(1, 1, 0, TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(QUEUE), r -> {
                Thread t = new Thread(r, "sse-sender");
                t.setDaemon(true);
                return t;
            }, new ThreadPoolExecutor.CallerRunsPolicy());
    private final Counter dropped;

    public StreamController(MeterRegistry metrics) {
        this.dropped = metrics.counter("monitor.stream.dropped");
    }

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
            sender.execute(() -> broadcast("status", Map.of("machineId", e.machineId(), "status", e.status())));
        } else {
            sender.execute(() -> broadcast("alert", Map.of("type", e.type().name(), "machineId", e.machineId(), "alert", e.alert())));
        }
    }

    @Override
    public void onScore(HealthScore s) {
        if (clients.isEmpty()) {
            return;
        }
        if (sender.getQueue().remainingCapacity() == 0) {
            dropped.increment();
            return;
        }
        Map<String, Object> data = Map.of("machineId", s.machineId(), "cycle", s.cycle(), "predictedRul", s.predictedRul());
        sender.execute(() -> broadcast("score", data));
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

    @PreDestroy
    void shutdown() {
        sender.shutdownNow();
    }
}
