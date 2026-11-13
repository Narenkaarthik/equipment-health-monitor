package dev.eqmon.ingest;

import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.util.List;
import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/** Writes readings with one multi-row batch statement; duplicates (same machine and cycle) are ignored. */
@Repository
public class ReadingRepository {

    private static final String INSERT;

    static {
        StringBuilder cols = new StringBuilder("machine_id, cycle, recorded_at, setting_1, setting_2, setting_3");
        StringBuilder marks = new StringBuilder("?, ?, ?, ?, ?, ?");
        for (int s = 1; s <= ReadingRequest.SENSOR_COUNT; s++) {
            cols.append(", s").append(s);
            marks.append(", ?");
        }
        INSERT = "INSERT INTO readings (" + cols + ") VALUES (" + marks + ") ON CONFLICT (machine_id, cycle) DO NOTHING";
    }

    private final JdbcTemplate jdbc;

    public ReadingRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** @return number of rows actually inserted (duplicates are not counted) */
    public int insertAll(List<Reading> readings) {
        if (readings.isEmpty()) {
            return 0;
        }
        int[] counts = jdbc.batchUpdate(INSERT, new BatchPreparedStatementSetter() {
            @Override
            public void setValues(PreparedStatement ps, int i) throws SQLException {
                Reading r = readings.get(i);
                int p = 1;
                ps.setInt(p++, r.machineId());
                ps.setInt(p++, r.cycle());
                ps.setTimestamp(p++, Timestamp.from(r.recordedAt()));
                for (double v : r.settings()) {
                    ps.setDouble(p++, v);
                }
                for (double v : r.sensors()) {
                    ps.setDouble(p++, v);
                }
            }

            @Override
            public int getBatchSize() {
                return readings.size();
            }
        });
        int inserted = 0;
        for (int c : counts) {
            // Drivers may report SUCCESS_NO_INFO (-2) for batches; PostgreSQL reports real counts.
            inserted += Math.max(c, 0);
        }
        return inserted;
    }

    public long count() {
        Long n = jdbc.queryForObject("select count(*) from readings", Long.class);
        return n == null ? 0 : n;
    }

    public long countForMachine(int machineId) {
        Long n = jdbc.queryForObject("select count(*) from readings where machine_id = ?", Long.class, machineId);
        return n == null ? 0 : n;
    }
}
