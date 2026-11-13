package dev.eqmon.replayer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.io.StringReader;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class CmapssReaderTest {

    static final String SAMPLE = """
            1 2 0.0019 -0.0003 100.0 518.67 642.15 1591.82 1403.14 14.62 21.61 553.75 2388.04 9044.07 1.30 47.49 522.28 2388.07 8131.49 8.4318 0.03 392 2388 100.00 39.00 23.4236
            1 1 -0.0007 -0.0004 100.0 518.67 641.82 1589.70 1400.60 14.62 21.61 554.36 2388.06 9046.19 1.30 47.47 521.66 2388.02 8138.62 8.4195 0.03 392 2388 100.00 39.06 23.4190
            2 1 -0.0018 0.0006 100.0 518.67 641.89 1583.84 1391.28 14.62 21.61 554.53 2388.01 9050.17 1.30 47.44 521.79 2388.06 8145.32 8.4047 0.03 391 2388 100.00 38.86 23.3735
            """;

    @Test
    void groupsByUnitAndSortsByCycle() throws IOException {
        Map<Integer, List<CmapssReader.Row>> rows = CmapssReader.read(new StringReader(SAMPLE));
        assertEquals(2, rows.size());
        assertEquals(List.of(1, 2), rows.get(1).stream().map(CmapssReader.Row::cycle).toList());
        assertEquals(518.67, rows.get(1).get(0).sensors()[0]);
        assertEquals(23.4190, rows.get(1).get(0).sensors()[20]);
        assertEquals(-0.0007, rows.get(1).get(0).settings()[0]);
    }

    @Test
    void rowSerialisesToTheIngestJson() throws IOException {
        CmapssReader.Row row = CmapssReader.read(new StringReader(SAMPLE)).get(2).get(0);
        String json = row.toJson();
        assertTrue(json.startsWith("{\"machineId\":2,\"cycle\":1,\"settings\":[-0.0018,6.0E-4,100.0],\"sensors\":{\"s1\":518.67,"));
        assertTrue(json.endsWith("\"s21\":23.3735}}"));
    }

    @Test
    void rejectsShortLines() {
        try {
            CmapssReader.read(new StringReader("1 2 3\n"));
        } catch (IOException e) {
            assertTrue(e.getMessage().contains("expected 26 columns"));
            return;
        }
        throw new AssertionError("expected IOException");
    }
}
