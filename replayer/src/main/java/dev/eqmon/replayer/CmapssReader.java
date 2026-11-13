package dev.eqmon.replayer;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.Reader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Parses a C-MAPSS text file (26 space-separated columns) into per-engine lists of rows in cycle order. */
public final class CmapssReader {

    public static final int SETTINGS = 3;
    public static final int SENSORS = 21;

    /** One row of the file. */
    public record Row(int unit, int cycle, double[] settings, double[] sensors) {

        public String toJson() {
            StringBuilder sb = new StringBuilder(512);
            sb.append("{\"machineId\":").append(unit).append(",\"cycle\":").append(cycle).append(",\"settings\":[");
            for (int i = 0; i < settings.length; i++) {
                if (i > 0) {
                    sb.append(',');
                }
                sb.append(settings[i]);
            }
            sb.append("],\"sensors\":{");
            for (int i = 0; i < sensors.length; i++) {
                if (i > 0) {
                    sb.append(',');
                }
                sb.append("\"s").append(i + 1).append("\":").append(sensors[i]);
            }
            return sb.append("}}").toString();
        }
    }

    private CmapssReader() {}

    public static Map<Integer, List<Row>> read(Path file) throws IOException {
        try (BufferedReader in = Files.newBufferedReader(file)) {
            return read(in);
        }
    }

    public static Map<Integer, List<Row>> read(Reader reader) throws IOException {
        BufferedReader in = reader instanceof BufferedReader b ? b : new BufferedReader(reader);
        Map<Integer, List<Row>> byUnit = new LinkedHashMap<>();
        String line;
        int lineNo = 0;
        while ((line = in.readLine()) != null) {
            lineNo++;
            String trimmed = line.trim();
            if (trimmed.isEmpty()) {
                continue;
            }
            String[] parts = trimmed.split("\\s+");
            if (parts.length < 2 + SETTINGS + SENSORS) {
                throw new IOException("line " + lineNo + ": expected 26 columns, found " + parts.length);
            }
            int unit = Integer.parseInt(parts[0]);
            int cycle = Integer.parseInt(parts[1]);
            double[] settings = new double[SETTINGS];
            for (int i = 0; i < SETTINGS; i++) {
                settings[i] = Double.parseDouble(parts[2 + i]);
            }
            double[] sensors = new double[SENSORS];
            for (int i = 0; i < SENSORS; i++) {
                sensors[i] = Double.parseDouble(parts[2 + SETTINGS + i]);
            }
            byUnit.computeIfAbsent(unit, k -> new ArrayList<>()).add(new Row(unit, cycle, settings, sensors));
        }
        for (List<Row> rows : byUnit.values()) {
            rows.sort((a, b) -> Integer.compare(a.cycle(), b.cycle()));
        }
        return byUnit;
    }
}
