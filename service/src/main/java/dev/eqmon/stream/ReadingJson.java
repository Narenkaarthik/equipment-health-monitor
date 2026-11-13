package dev.eqmon.stream;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.eqmon.ingest.Reading;

/** The wire format of a reading on the {@code readings} topic (plain JSON of {@link Reading}). */
public final class ReadingJson {

    private final ObjectMapper mapper;

    public ReadingJson(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public String write(Reading r) {
        try {
            return mapper.writeValueAsString(r);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException(e);
        }
    }

    public Reading read(String json) {
        try {
            return mapper.readValue(json, Reading.class);
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("malformed reading message", e);
        }
    }
}
