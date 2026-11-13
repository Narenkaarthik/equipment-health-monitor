package dev.eqmon.alerts;

import dev.eqmon.model.HealthScore;
import dev.eqmon.model.HealthScoreListener;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.BiConsumer;
import java.util.function.Consumer;

/**
 * Applies the alert rules to every health score.
 *
 * <p>Semantics (docs/architecture.md, "Alerts"):
 * <ul>
 *   <li>Two rule types. Threshold: predicted RUL below {@code criticalBelow} is CRITICAL, below
 *       {@code warningBelow} is WARNING. Trend: RUL fell by more than {@code trendDrop} over the last
 *       {@code trendWindow} scored readings (WARNING).</li>
 *   <li>A machine has at most one open alert per severity. The first rule that raises a severity opens
 *       it; while it is open, nothing re-fires for that severity, so an alert never repeats per reading.</li>
 *   <li>An open alert closes only after every condition of its severity has been clear for
 *       {@code closeAfter} consecutive readings. "Clear" for a threshold means RUL above the threshold
 *       plus {@code hysteresis}, so a noisy prediction hovering at the line does not flap.</li>
 *   <li>Machine status = most severe open alert, else HEALTHY; a change is persisted and published.</li>
 * </ul>
 * Per-machine state (recent RULs, clear counters, open alerts) is rebuilt from the repositories the
 * first time a machine is seen after a restart.
 */
public class AlertEngine implements HealthScoreListener {

    public static final String RULE_THRESHOLD = "rul_threshold";
    public static final String RULE_TREND = "rul_trend";

    private final AlertRules rules;
    private final AlertRepository alerts;
    private final BiConsumer<Integer, String> statusStore;
    private final Consumer<AlertEvent> events;
    private final RecentScores recentScores;
    private final Map<Integer, MachineAlertState> states = new ConcurrentHashMap<>();

    /** Supplies the last N predicted RULs of a machine (oldest first) when state is rebuilt after a restart. */
    @FunctionalInterface
    public interface RecentScores {
        List<Double> lastRuls(int machineId, int n);
    }

    public AlertEngine(AlertRules rules, AlertRepository alerts, BiConsumer<Integer, String> statusStore,
            Consumer<AlertEvent> events, RecentScores recentScores) {
        this.rules = rules;
        this.alerts = alerts;
        this.statusStore = statusStore;
        this.events = events;
        this.recentScores = recentScores;
    }

    @Override
    public void onScore(HealthScore score) {
        MachineAlertState st = states.computeIfAbsent(score.machineId(), this::rebuild);
        synchronized (st) {
            evaluate(st, score);
        }
    }

    private void evaluate(MachineAlertState st, HealthScore score) {
        double rul = score.predictedRul();
        st.recent.addLast(rul);
        while (st.recent.size() > rules.trendWindow() + 1) {
            st.recent.removeFirst();
        }

        // which conditions hold now, per severity
        Map<Severity, List<String>> firing = new EnumMap<>(Severity.class);
        Map<Severity, Boolean> clear = new EnumMap<>(Severity.class);
        for (Severity s : Severity.values()) {
            firing.put(s, new ArrayList<>());
            clear.put(s, true);
        }
        if (rul < rules.criticalBelow()) {
            firing.get(Severity.CRITICAL).add(String.format("%s: predicted RUL %.1f < %.0f", RULE_THRESHOLD, rul, rules.criticalBelow()));
        }
        if (rul < rules.criticalBelow() + rules.hysteresis()) {
            clear.put(Severity.CRITICAL, false);
        }
        if (rul < rules.warningBelow()) {
            firing.get(Severity.WARNING).add(String.format("%s: predicted RUL %.1f < %.0f", RULE_THRESHOLD, rul, rules.warningBelow()));
        }
        if (rul < rules.warningBelow() + rules.hysteresis()) {
            clear.put(Severity.WARNING, false);
        }
        if (st.recent.size() > rules.trendWindow()) {
            double drop = st.recent.peekFirst() - rul;
            if (drop > rules.trendDrop()) {
                firing.get(Severity.WARNING).add(String.format("%s: predicted RUL fell %.1f over %d readings", RULE_TREND, drop, rules.trendWindow()));
                clear.put(Severity.WARNING, false);
            }
        }

        for (Severity sev : Severity.values()) {
            Alert open = st.open.get(sev);
            List<String> reasons = firing.get(sev);
            if (open == null) {
                if (!reasons.isEmpty()) {
                    String rule = reasons.get(0).startsWith(RULE_TREND) ? RULE_TREND : RULE_THRESHOLD;
                    Alert created = alerts.open(new Alert(0, score.machineId(), rule, sev, String.join("; ", reasons),
                            score.cycle(), score.scoredAt(), null, null, null));
                    st.open.put(sev, created);
                    st.clearStreak.put(sev, 0);
                    events.accept(new AlertEvent(AlertEvent.Type.OPENED, score.machineId(), created, null));
                }
            } else {
                int streak = clear.get(sev) ? st.clearStreak.getOrDefault(sev, 0) + 1 : 0;
                st.clearStreak.put(sev, streak);
                if (streak >= rules.closeAfter()) {
                    alerts.close(open.id(), score.cycle(), score.scoredAt());
                    Alert closed = open.closed(score.cycle(), score.scoredAt());
                    st.open.remove(sev);
                    st.clearStreak.put(sev, 0);
                    events.accept(new AlertEvent(AlertEvent.Type.CLOSED, score.machineId(), closed, null));
                }
            }
        }
        updateStatus(st, score.machineId());
    }

    private void updateStatus(MachineAlertState st, int machineId) {
        String status = st.open.containsKey(Severity.CRITICAL) ? Severity.CRITICAL.name()
                : st.open.containsKey(Severity.WARNING) ? Severity.WARNING.name() : Severity.HEALTHY;
        if (!status.equals(st.status)) {
            st.status = status;
            statusStore.accept(machineId, status);
            events.accept(new AlertEvent(AlertEvent.Type.STATUS, machineId, null, status));
        }
    }

    public boolean acknowledge(long id, Instant at) {
        boolean ok = alerts.acknowledge(id, at);
        if (ok) {
            alerts.find(id).ifPresent(a -> {
                MachineAlertState st = states.get(a.machineId());
                if (st != null) {
                    synchronized (st) {
                        if (st.open.containsKey(a.severity()) && st.open.get(a.severity()).id() == id) {
                            st.open.put(a.severity(), a);
                        }
                    }
                }
                events.accept(new AlertEvent(AlertEvent.Type.ACKNOWLEDGED, a.machineId(), a, null));
            });
        }
        return ok;
    }

    public String status(int machineId) {
        MachineAlertState st = states.get(machineId);
        return st == null ? null : st.status;
    }

    /** Drops in-memory state (tests simulate a restart). */
    public void forgetInMemoryState() {
        states.clear();
    }

    private MachineAlertState rebuild(int machineId) {
        MachineAlertState st = new MachineAlertState();
        for (Alert a : alerts.openFor(machineId)) {
            st.open.put(a.severity(), a);
        }
        st.recent.addAll(recentScores.lastRuls(machineId, rules.trendWindow() + 1));
        st.status = st.open.containsKey(Severity.CRITICAL) ? Severity.CRITICAL.name()
                : st.open.containsKey(Severity.WARNING) ? Severity.WARNING.name() : Severity.HEALTHY;
        return st;
    }

    private static final class MachineAlertState {
        final ArrayDeque<Double> recent = new ArrayDeque<>();
        final Map<Severity, Alert> open = new EnumMap<>(Severity.class);
        final Map<Severity, Integer> clearStreak = new EnumMap<>(Severity.class);
        String status = Severity.HEALTHY;
    }
}
