package dev.eqmon.machines;

import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/** The fleet table. */
@Repository
public class MachineRepository {

    public record Machine(int id, String name, String status) {}

    private final JdbcClient jdbc;

    public MachineRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    /** Idempotent create: a second call with the same id only updates the name. */
    public void upsert(int id, String name) {
        jdbc.sql("""
                insert into machines (id, name) values (:id, :name)
                on conflict (id) do update set name = excluded.name, updated_at = now()
                """)
                .param("id", id).param("name", name).update();
    }

    public Set<Integer> ids() {
        return new HashSet<>(jdbc.sql("select id from machines").query(Integer.class).list());
    }

    public Optional<Machine> find(int id) {
        return jdbc.sql("select id, name, status from machines where id = :id")
                .param("id", id).query(Machine.class).optional();
    }

    public List<Machine> all() {
        return jdbc.sql("select id, name, status from machines order by id").query(Machine.class).list();
    }

    public void updateStatus(int id, String status) {
        jdbc.sql("update machines set status = :status, updated_at = now() where id = :id")
                .param("status", status).param("id", id).update();
    }
}
