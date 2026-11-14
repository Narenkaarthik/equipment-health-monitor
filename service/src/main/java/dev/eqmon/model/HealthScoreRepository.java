package dev.eqmon.model;

import java.sql.Timestamp;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class HealthScoreRepository {

    private final JdbcClient jdbc;

    public HealthScoreRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    /** Idempotent: scoring the same (machine, cycle) twice keeps the first row. */
    public boolean insert(HealthScore s) {
        int n = jdbc.sql("""
                insert into health_scores (machine_id, cycle, predicted_rul, model_version, window_rows, scored_at)
                values (:m, :c, :rul, :v, :w, :t) on conflict (machine_id, cycle) do nothing
                """)
                .param("m", s.machineId()).param("c", s.cycle()).param("rul", s.predictedRul())
                .param("v", s.modelVersion()).param("w", s.windowRows()).param("t", Timestamp.from(s.scoredAt()))
                .update();
        return n == 1;
    }

    public Optional<HealthScore> latest(int machineId) {
        return jdbc.sql("""
                select machine_id, cycle, predicted_rul, model_version, window_rows, scored_at
                from health_scores where machine_id = :m order by cycle desc limit 1
                """)
                .param("m", machineId).query(HealthScoreRepository::map).optional();
    }

    public List<HealthScore> history(int machineId, int fromCycle, int toCycle, int limit) {
        return jdbc.sql("""
                select machine_id, cycle, predicted_rul, model_version, window_rows, scored_at
                from health_scores where machine_id = :m and cycle between :from and :to order by cycle limit :limit
                """)
                .param("m", machineId).param("from", fromCycle).param("to", toCycle).param("limit", limit)
                .query(HealthScoreRepository::map).list();
    }

    /** The last n predicted RULs of a machine strictly before a cycle, oldest first (rebuilds the alert engine's trend window). */
    public List<Double> lastRuls(int machineId, int beforeCycle, int n) {
        List<Double> newestFirst = jdbc.sql("select predicted_rul from health_scores where machine_id = :m and cycle < :before "
                + "order by cycle desc limit :n")
                .param("m", machineId).param("before", beforeCycle).param("n", n).query(Double.class).list();
        List<Double> out = new java.util.ArrayList<>(newestFirst);
        java.util.Collections.reverse(out);
        return out;
    }

    public long count() {
        Long n = jdbc.sql("select count(*) from health_scores").query(Long.class).single();
        return n == null ? 0 : n;
    }

    private static HealthScore map(java.sql.ResultSet rs, int i) throws java.sql.SQLException {
        return new HealthScore(rs.getInt("machine_id"), rs.getInt("cycle"), rs.getDouble("predicted_rul"),
                rs.getString("model_version"), rs.getInt("window_rows"), rs.getTimestamp("scored_at").toInstant());
    }
}
