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

    // warning < 60, critical < 30, trend drop > 20 over 10, close after 5 clear, hysteresis 10
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
        engine = new AlertEngine(rules, repo, status::put, events::add, (m, n) -> List.of());
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
    void trendRuleOpensAWarningOnASharpDropWhileStillAboveThreshold() {
        scores(120, 11);
        for (int i = 1; i <= 10; i++) {
            score(120 - 3 * i); // 117 .. 90: drop of 30 over 10 readings
        }
        assertThat(repo.all).hasSize(1);
        assertThat(repo.all.get(0).rule()).isEqualTo(AlertEngine.RULE_TREND);
        assertThat(repo.all.get(0).severity()).isEqualTo(Severity.WARNING);
        // flat again: the drop leaves the window one reading at a time (clear from the 4th flat reading),
        // then K = 5 clear readings close it: closed on the 8th flat reading, not before
        scores(90, 7);
        assertThat(repo.all.get(0).open()).isTrue();
        score(90);
        assertThat(repo.all.get(0).open()).isFalse();
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
        AlertEngine restarted = new AlertEngine(rules, repo, status::put, events::add, (m, n) -> List.of(55.0, 55.0, 55.0));
        // same machine keeps its open WARNING: no second alert is opened
        restarted.onScore(new HealthScore(1, 4, 55, "test", 30, Instant.ofEpochSecond(4)));
        assertThat(repo.all).hasSize(1);
        assertThat(restarted.status(1)).isEqualTo("WARNING");
    }
}
