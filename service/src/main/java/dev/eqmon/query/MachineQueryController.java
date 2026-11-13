package dev.eqmon.query;

import dev.eqmon.machines.MachineRepository;
import dev.eqmon.model.HealthScore;
import dev.eqmon.model.HealthScoreRepository;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * Read API for the dashboard:
 * {@code GET /api/machines}, {@code GET /api/machines/{id}/readings?from=&to=&sensor=&limit=},
 * {@code GET /api/machines/{id}/health?from=&to=&limit=}.
 */
@RestController
@RequestMapping("/api/machines")
public class MachineQueryController {

    private static final int MAX_PAGE = 2000;

    private final ReadingQueryRepository readings;
    private final HealthScoreRepository scores;
    private final MachineRepository machines;

    public MachineQueryController(ReadingQueryRepository readings, HealthScoreRepository scores, MachineRepository machines) {
        this.readings = readings;
        this.scores = scores;
        this.machines = machines;
    }

    @GetMapping
    public List<ReadingQueryRepository.FleetRow> fleet() {
        return readings.fleet();
    }

    @GetMapping("/{id}")
    public Map<String, Object> one(@PathVariable int id) {
        MachineRepository.Machine m = machines.find(id).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        Map<String, Object> range = readings.cycleRange(id);
        return Map.of("id", m.id(), "name", m.name(), "status", m.status(), "minCycle", range.get("min_cycle"),
                "maxCycle", range.get("max_cycle"), "readings", range.get("rows_"),
                "latest", scores.latest(id).map(h -> Map.of("cycle", h.cycle(), "predictedRul", h.predictedRul(),
                        "modelVersion", h.modelVersion())).orElse(Map.of()));
    }

    @GetMapping("/{id}/readings")
    public Map<String, Object> readingHistory(@PathVariable int id, @RequestParam(defaultValue = "s11") String sensor,
            @RequestParam(defaultValue = "1") int from, @RequestParam(defaultValue = "2147483647") int to,
            @RequestParam(defaultValue = "500") int limit) {
        if (!ReadingQueryRepository.validSensor(sensor)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "unknown sensor " + sensor);
        }
        int page = Math.min(Math.max(limit, 1), MAX_PAGE);
        List<ReadingQueryRepository.Point> points = readings.sensorHistory(id, sensor, from, to, page + 1);
        boolean more = points.size() > page;
        List<ReadingQueryRepository.Point> body = more ? points.subList(0, page) : points;
        return Map.of("machineId", id, "sensor", sensor, "from", from, "to", to, "points", body,
                "nextFrom", more ? body.get(body.size() - 1).cycle() + 1 : -1, "hasMore", more);
    }

    @GetMapping("/{id}/health")
    public Map<String, Object> healthHistory(@PathVariable int id, @RequestParam(defaultValue = "1") int from,
            @RequestParam(defaultValue = "2147483647") int to, @RequestParam(defaultValue = "500") int limit) {
        int page = Math.min(Math.max(limit, 1), MAX_PAGE);
        List<HealthScore> rows = scores.history(id, from, to, page + 1);
        boolean more = rows.size() > page;
        List<HealthScore> body = more ? rows.subList(0, page) : rows;
        return Map.of("machineId", id, "from", from, "to", to, "hasMore", more,
                "points", body.stream().map(h -> Map.of("cycle", h.cycle(), "predictedRul", h.predictedRul(),
                        "modelVersion", h.modelVersion())).toList());
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> badRequest(IllegalArgumentException e) {
        return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
    }
}
