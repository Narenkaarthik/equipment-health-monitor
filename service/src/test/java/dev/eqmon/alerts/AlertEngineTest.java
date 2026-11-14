package dev.eqmon.alerts;

import static org.assertj.core.api.Assertions.assertThat;

import dev.eqmon.model.HealthScore;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/** Stage 4 transitions: open once, stay open, close only after K clear readings, status follows severity. */
class AlertEngineTest {

    // warning < 60, critical < 30, trend slope < -2 over 30 (clear above -1.5, full window), close after 5 clear, hysteresis 10
    final AlertRules rules = AlertRules.defaults();
    InMemoryAlertRepository repo;
    Map<Integer, String> status;
    List<AlertEvent> events;
    AlertEngine engine;
    int cycle;

    @BeforeEach
    void setUp() {
        repo = new InMemoryAlertRepository();
        status = new HashMap<>();
        events = new ArrayList<>();
        engine = new AlertEngine(rules, repo, status::put, events::add, (m, before, n) -> List.of());
        cycle = 0;
    }

    void score(double rul) {
        engine.onScore(new HealthScore(1, ++cycle, rul, "test", 30, Instant.ofEpochSecond(cycle)));
    }

    void scores(double rul, int times) {
        for (int i = 0; i < times; i++) {
            score(rul);
        }
    }

    long opened() {
        return events.stream().filter(e -> e.type() == AlertEvent.Type.OPENED).count();
    }

    @Test
    void thresholdOpensOnceAndDoesNotRepeatPerReading() {
        scores(100, 3);
        assertThat(repo.all).isEmpty();
        scores(55, 20);
        assertThat(repo.all).hasSize(1);
        assertThat(repo.all.get(0).severity()).isEqualTo(Severity.WARNING);
        assertThat(repo.all.get(0).rule()).isEqualTo(AlertEngine.RULE_THRESHOLD);
        assertThat(repo.all.get(0).openedCycle()).isEqualTo(4);
        assertThat(opened()).isEqualTo(1);
        assertThat(status.get(1)).isEqualTo("WARNING");
    }

    @Test
    void closesOnlyAfterKConsecutiveClearReadingsWithHysteresis() {
        scores(55, 2); // WARNING open
        scores(65, 4); // above 60 but inside hysteresis (needs > 70): not clear
        assertThat(repo.all.get(0).open()).isTrue();
        scores(75, 4); // clear, but only 4 in a row
        assertThat(repo.all.get(0).open()).isTrue();
        score(55);     // condition back: streak resets
        scores(75, 4);
        assertThat(repo.all.get(0).open()).isTrue();
        score(75);     // fifth consecutive clear reading
        assertThat(repo.all.get(0).open()).isFalse();
        assertThat(repo.all.get(0).closedCycle()).isEqualTo(cycle);
        assertThat(status.get(1)).isEqualTo("HEALTHY");
        assertThat(events.stream().filter(e -> e.type() == AlertEvent.Type.CLOSED).count()).isEqualTo(1);
    }

    @Test
    void engineRunToFailureGivesOneWarningThenOneCritical() {
        // a smooth decline from 120 to 0 over 120 readings
        for (int rul = 120; rul >= 0; rul--) {
            score(rul);
        }
        assertThat(repo.all).hasSize(2);
        assertThat(repo.all.get(0).severity()).isEqualTo(Severity.WARNING);
        assertThat(repo.all.get(1).severity()).isEqualTo(Severity.CRITICAL);
        assertThat(repo.all.get(0).openedCycle()).isLessThan(repo.all.get(1).openedCycle());
        assertThat(repo.all).allMatch(Alert::open);
        assertThat(status.get(1)).isEqualTo("CRITICAL");
        List<String> statuses = events.stream().filter(e -> e.type() == AlertEvent.Type.STATUS).map(AlertEvent::status).toList();
        assertThat(statuses).containsExactly("WARNING", "CRITICAL");
    }

    @Test
    void criticalDoesNotOpenASecondWarning() {
        scores(25, 3); // both conditions at once
        assertThat(repo.all).hasSize(2);
        assertThat(repo.all).extracting(Alert::severity).containsExactlyInAnyOrder(Severity.WARNING, Severity.CRITICAL);
        scores(25, 10);
        assertThat(repo.all).hasSize(2);
    }

    @Test
    void trendRuleOpensAWarningOnASharpFallWhileStillAboveThreshold() {
        scores(124, 30);
        int fallFrom = cycle;
        for (int i = 1; i <= 15; i++) {
            score(124 - 4 * i); // falling 4 cycles per reading: 120 .. 64, never below the WARNING threshold
        }
        assertThat(repo.all).hasSize(1);
        Alert a = repo.all.get(0);
        assertThat(a.rule()).isEqualTo(AlertEngine.RULE_TREND);
        assertThat(a.severity()).isEqualTo(Severity.WARNING);
        assertThat(a.openedCycle()).isGreaterThan(fallFrom);
        assertThat(a.detail()).contains("cycles per reading");
        // flat again at 80 (above 60 + hysteresis): the fitted slope recovers, then K = 5 clear readings close it
        scores(80, 5);
        assertThat(repo.all.get(0).open()).isTrue();
        scores(80, 40);
        assertThat(repo.all.get(0).open()).isFalse();
        assertThat(repo.all).hasSize(1);
    }

    @Test
    void trendRuleIgnoresJitterAroundAFlatLevel() {
        // +-15 cycles of alternating jitter: an endpoint difference over 10 readings would fire; a 30-reading fit does not
        for (int i = 0; i < 200; i++) {
            score(i % 2 == 0 ? 105 : 90);
        }
        assertThat(repo.all).isEmpty();
    }

    @Test
    void noAlertOpensDuringWarmUp() {
        // a falling, then critically low RUL, but the feature window never fills: nothing may open
        for (int i = 0; i < 40; i++) {
            engine.onScore(new HealthScore(1, ++cycle, Math.max(0, 124 - 4 * i), "test", 10, Instant.ofEpochSecond(cycle)));
        }
        assertThat(repo.all).isEmpty();
        // the first reading with a full window opens both, threshold first
        engine.onScore(new HealthScore(1, ++cycle, 5, "test", 30, Instant.ofEpochSecond(cycle)));
        assertThat(repo.all).extracting(Alert::severity).containsExactly(Severity.WARNING, Severity.CRITICAL);
    }

    @Test
    void slopeIsTheLeastSquaresSlope() {
        assertThat(AlertEngine.slope(List.of(1.0, 2.0, 4.0))).isEqualTo(1.5);
        assertThat(AlertEngine.slope(List.of(5.0, 5.0, 5.0))).isEqualTo(0.0);
        assertThat(AlertEngine.slope(List.of(7.0))).isEqualTo(0.0);
    }

    @Test
    void rebuildAsksOnlyForScoresBeforeTheCurrentCycle() {
        List<Integer> asked = new ArrayList<>();
        AlertEngine fresh = new AlertEngine(rules, repo, status::put, events::add, (m, before, n) -> {
            asked.add(before);
            return List.of();
        });
        fresh.onScore(new HealthScore(1, 77, 100, "test", 30, Instant.ofEpochSecond(77)));
        assertThat(asked).containsExactly(77);
    }

    @Test
    void statusFollowsTheMostSevereOpenAlert() {
        scores(25, 1);
        assertThat(status.get(1)).isEqualTo("CRITICAL");
        scores(50, 5); // critical clears (50 > 30 + 10) for 5 readings, warning stays
        assertThat(status.get(1)).isEqualTo("WARNING");
        assertThat(repo.openFor(1)).hasSize(1);
        scores(80, 5);
        assertThat(status.get(1)).isEqualTo("HEALTHY");
    }

    @Test
    void acknowledgeIsIdempotentAndUnknownIdIsFalse() {
        scores(55, 1);
        assertThat(engine.acknowledge(1, Instant.ofEpochSecond(100))).isTrue();
        assertThat(engine.acknowledge(1, Instant.ofEpochSecond(200))).isTrue();
        assertThat(repo.find(1).orElseThrow().acknowledgedAt()).isEqualTo(Instant.ofEpochSecond(100));
        assertThat(engine.acknowledge(99, Instant.ofEpochSecond(100))).isFalse();
    }

    @Test
    void stateIsRebuiltFromRepositoriesAfterARestart() {
        scores(55, 3);
        AlertEngine restarted = new AlertEngine(rules, repo, status::put, events::add, (m, before, n) -> List.of(55.0, 55.0, 55.0));
        // same machine keeps its open WARNING: no second alert is opened
        restarted.onScore(new HealthScore(1, 4, 55, "test", 30, Instant.ofEpochSecond(4)));
        assertThat(repo.all).hasSize(1);
        assertThat(restarted.status(1)).isEqualTo("WARNING");
    }
}
