package dev.eqmon.processing;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Optional;
import java.util.Set;
import org.springframework.data.redis.core.StringRedisTemplate;

/** Window snapshots as JSON strings under {@code window:{machineId}}. About 6 KB per machine at W = 30. */
public class RedisWindowStateStore implements WindowStateStore {

    static final String PREFIX = "window:";

    private final StringRedisTemplate redis;
    private final ObjectMapper json;

    public RedisWindowStateStore(StringRedisTemplate redis, ObjectMapper json) {
        this.redis = redis;
        this.json = json;
    }

    @Override
    public void save(MachineWindow.WindowSnapshot snapshot) {
        try {
            redis.opsForValue().set(PREFIX + snapshot.machineId(), json.writeValueAsString(snapshot));
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("cannot serialise window of machine " + snapshot.machineId(), e);
        }
    }

    @Override
    public Optional<MachineWindow.WindowSnapshot> load(int machineId) {
        String value = redis.opsForValue().get(PREFIX + machineId);
        if (value == null) {
            return Optional.empty();
        }
        try {
            return Optional.of(json.readValue(value, MachineWindow.WindowSnapshot.class));
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("corrupt window state for machine " + machineId, e);
        }
    }

    @Override
    public void clear() {
        Set<String> keys = redis.keys(PREFIX + "*");
        if (keys != null && !keys.isEmpty()) {
            redis.delete(keys);
        }
    }
}
