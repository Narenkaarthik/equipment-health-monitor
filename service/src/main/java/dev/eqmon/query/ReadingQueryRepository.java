package dev.eqmon.query;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/** Read side of the readings table for the charts. */
@Repository
public class ReadingQueryRepository {

    private static final Set<String> SENSORS = IntStream.rangeClosed(1, 21).mapToObj(i -> "s" + i).collect(Collectors.toSet());

    public record Point(int cycle, double value) {}

    public record FleetRow(int id, String name, String status, Integer lastCycle, Double predictedRul, String modelVersion) {}

    private final JdbcClient jdbc;

    public ReadingQueryRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public static boolean validSensor(String sensor) {
        return SENSORS.contains(sensor);
    }

    /** One sensor's values of one machine between two cycles, in cycle order, at most {@code limit} rows. */
    public List<Point> sensorHistory(int machineId, String sensor, int from, int to, int limit) {
        if (!validSensor(sensor)) {
            throw new IllegalArgumentException("unknown sensor " + sensor);
        }
        // the column name is whitelisted above; cycles and limit are bound parameters
        return jdbc.sql("select cycle, " + sensor + " as value from readings where machine_id = :m and cycle between :from and :to "
                + "order by cycle limit :limit")
                .param("m", machineId).param("from", from).param("to", to).param("limit", limit)
                .query((rs, i) -> new Point(rs.getInt("cycle"), rs.getDouble("value"))).list();
    }

    public Map<String, Object> cycleRange(int machineId) {
        return jdbc.sql("select coalesce(min(cycle), 0) as min_cycle, coalesce(max(cycle), 0) as max_cycle, count(*) as rows_ from readings where machine_id = :m")
                .param("m", machineId).query().singleRow();
    }

    /** Fleet list with the latest health score per machine (DISTINCT ON walks the (machine_id, cycle) index backwards). */
    public List<FleetRow> fleet() {
        return jdbc.sql("""
                select m.id, m.name, m.status, h.cycle as last_cycle, h.predicted_rul, h.model_version
                from machines m
                left join (
                    select distinct on (machine_id) machine_id, cycle, predicted_rul, model_version
                    from health_scores order by machine_id, cycle desc
                ) h on h.machine_id = m.id
                order by m.id
                """)
                .query((rs, i) -> {
                    int lastCycle = rs.getInt("last_cycle");
                    boolean noScore = rs.wasNull();
                    double rul = rs.getDouble("predicted_rul");
                    return new FleetRow(rs.getInt("id"), rs.getString("name"), rs.getString("status"),
                            noScore ? null : lastCycle, noScore ? null : rul, rs.getString("model_version"));
                }).list();
    }
}
