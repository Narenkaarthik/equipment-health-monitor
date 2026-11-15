package dev.eqmon.machines;

import java.util.Map;
import java.util.regex.Pattern;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Registers a machine so its readings are accepted. {@code PUT /api/machines/{id}} with {"name": "..."}.
 * Names are plain identifiers (letters, digits, space, dot, dash, underscore; at most 64): the dashboard shows them,
 * so markup is refused here as well as escaped there.
 */
@RestController
@RequestMapping("/api/machines")
public class MachineRegistrationController {

    static final Pattern NAME = Pattern.compile("[A-Za-z0-9 ._-]{1,64}");

    private final MachineRepository machines;
    private final KnownMachines known;

    public MachineRegistrationController(MachineRepository machines, KnownMachines known) {
        this.machines = machines;
        this.known = known;
    }

    @PutMapping("/{id}")
    public ResponseEntity<Map<String, Object>> register(@PathVariable int id, @RequestBody(required = false) Map<String, String> body) {
        if (id <= 0) {
            return ResponseEntity.badRequest().body(Map.of("error", "machine id must be positive"));
        }
        String name = body == null || body.get("name") == null || body.get("name").isBlank()
                ? String.format("engine-%03d", id)
                : body.get("name");
        if (!NAME.matcher(name).matches()) {
            return ResponseEntity.badRequest().body(Map.of("error",
                    "name must be 1-64 letters, digits, spaces, dots, dashes or underscores"));
        }
        machines.upsert(id, name);
        known.add(id);
        return ResponseEntity.ok(Map.of("id", id, "name", name));
    }
}
