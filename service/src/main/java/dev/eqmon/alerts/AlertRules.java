package dev.eqmon.alerts;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Alert rule parameters ({@code monitor.alerts.*}).
 *
 * @param warningBelow  threshold rule: predicted RUL below this is WARNING (plan: 60)
 * @param criticalBelow threshold rule: predicted RUL below this is CRITICAL (plan: 30)
 * @param trendDrop     trend rule: RUL fell by more than this ...
 * @param trendWindow   ... over the last this-many scored readings
 * @param closeAfter    an alert closes after its conditions have been clear for this many consecutive readings (K)
 * @param hysteresis    a threshold condition counts as clear only when RUL is above threshold + hysteresis
 */
@ConfigurationProperties(prefix = "monitor.alerts")
public record AlertRules(double warningBelow, double criticalBelow, double trendDrop, int trendWindow, int closeAfter,
        double hysteresis) {

    public static AlertRules defaults() {
        return new AlertRules(60, 30, 20, 10, 5, 10);
    }
}
