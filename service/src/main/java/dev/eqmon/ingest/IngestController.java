package dev.eqmon.ingest;

import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/**
 * {@code POST /api/readings}: one reading (a JSON object) or a batch (a JSON array).
 * Returns 202 with counts, or 400 listing every invalid reading by its index in the batch.
 */
@RestController
public class IngestController {

    private final IngestService ingest;

    public IngestController(IngestService ingest) {
        this.ingest = ingest;
    }

    @PostMapping("/api/readings")
    public ResponseEntity<IngestService.Result> post(@RequestBody List<ReadingRequest> batch) {
        if (batch == null || batch.isEmpty()) {
            throw new InvalidBatchException(List.of(new ReadingValidator.Problem(0, "empty batch")));
        }
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(ingest.ingest(batch));
    }

    @ExceptionHandler(InvalidBatchException.class)
    public ResponseEntity<Map<String, Object>> invalid(InvalidBatchException e) {
        return ResponseEntity.badRequest().body(Map.of(
                "error", "invalid batch",
                "problems", e.problems()));
    }
}
