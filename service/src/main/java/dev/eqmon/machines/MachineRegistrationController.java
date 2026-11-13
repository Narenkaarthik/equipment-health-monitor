package dev.eqmon.machines;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Registers a machine so its readings are accepted. {@code PUT /api/machines/{id}} with {"name": "..."}. */
@RestController
@RequestMapping("/api/machines")
public class MachineRegistrationController {

    private final MachineRepository machines;

    public MachineRegistrationController(MachineRepository machines) {
        this.machines = machines;
    }

    @PutMapping("/{id}")
    public ResponseEntity<Map<String, Object>> register(@PathVariable int id, @RequestBody(required = false) Map<String, String> body) {
        String name = body == null || body.get("name") == null || body.get("name").isBlank()
                ? String.format("engine-%03d", id)
                : body.get("name");
        machines.upsert(id, name);
        return ResponseEntity.ok(Map.of("id", id, "name", name));
    }
}
