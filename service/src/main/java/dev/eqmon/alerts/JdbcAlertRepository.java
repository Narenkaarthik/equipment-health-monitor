package dev.eqmon.alerts;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcAlertRepository implements AlertRepository {

    private static final String COLUMNS =
            "id, machine_id, rule, severity, detail, opened_cycle, opened_at, closed_cycle, closed_at, acknowledged_at";

    private final JdbcClient jdbc;

    public JdbcAlertRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Alert open(Alert a) {
        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.sql("""
                insert into alerts (machine_id, rule, severity, detail, opened_cycle, opened_at)
                values (:m, :rule, :sev, :detail, :cycle, :at)
                """)
                .param("m", a.machineId()).param("rule", a.rule()).param("sev", a.severity().name())
                .param("detail", a.detail()).param("cycle", a.openedCycle()).param("at", Timestamp.from(a.openedAt()))
                .update(keys, "id");
        long id = ((Number) keys.getKeys().get("id")).longValue();
        return new Alert(id, a.machineId(), a.rule(), a.severity(), a.detail(), a.openedCycle(), a.openedAt(), null, null, null);
    }

    @Override
    public void close(long id, int cycle, Instant at) {
        jdbc.sql("update alerts set closed_cycle = :c, closed_at = :at where id = :id and closed_at is null")
                .param("c", cycle).param("at", Timestamp.from(at)).param("id", id).update();
    }

    @Override
    public boolean acknowledge(long id, Instant at) {
        return jdbc.sql("update alerts set acknowledged_at = coalesce(acknowledged_at, :at) where id = :id")
                .param("at", Timestamp.from(at)).param("id", id).update() == 1;
    }

    @Override
    public Optional<Alert> find(long id) {
        return jdbc.sql("select " + COLUMNS + " from alerts where id = :id").param("id", id)
                .query(JdbcAlertRepository::map).optional();
    }

    @Override
    public List<Alert> openFor(int machineId) {
        return jdbc.sql("select " + COLUMNS + " from alerts where machine_id = :m and closed_at is null order by id")
                .param("m", machineId).query(JdbcAlertRepository::map).list();
    }

    @Override
    public List<Alert> list(String status, int limit) {
        String where = switch (status) {
            case "open" -> "where closed_at is null";
            case "closed" -> "where closed_at is not null";
            default -> "";
        };
        return jdbc.sql("select " + COLUMNS + " from alerts " + where + " order by opened_at desc, id desc limit :limit")
                .param("limit", limit).query(JdbcAlertRepository::map).list();
    }

    static Alert map(ResultSet rs, int i) throws SQLException {
        Timestamp closedAt = rs.getTimestamp("closed_at");
        Timestamp ack = rs.getTimestamp("acknowledged_at");
        int closedCycle = rs.getInt("closed_cycle");
        return new Alert(rs.getLong("id"), rs.getInt("machine_id"), rs.getString("rule"),
                Severity.valueOf(rs.getString("severity")), rs.getString("detail"), rs.getInt("opened_cycle"),
                rs.getTimestamp("opened_at").toInstant(), rs.wasNull() ? null : closedCycle,
                closedAt == null ? null : closedAt.toInstant(), ack == null ? null : ack.toInstant());
    }
}
