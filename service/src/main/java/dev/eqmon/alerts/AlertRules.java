package dev.eqmon.alerts;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Alert rule parameters ({@code monitor.alerts.*}).
 *
 * @param warningBelow       threshold rule: predicted RUL below this is WARNING (plan: 60)
 * @param criticalBelow      threshold rule: predicted RUL below this is CRITICAL (plan: 30)
 * @param trendWindow        trend rule: least-squares fit over the last this-many scored readings
 * @param trendSlope         trend rule fires (WARNING) when the fitted slope is below this, in cycles of RUL
 *                           per reading; -2 means "falling twice as fast as time passes"
 * @param trendClearSlope    the trend condition counts as clear only when the slope is above this
 * @param minWindowRows      warm-up: no alert opens, and the trend rule is not evaluated, before the feature window holds this many rows
 * @param closeAfter         an alert closes after its conditions have been clear for this many consecutive readings (K)
 * @param hysteresis         a threshold condition counts as clear only when RUL is above threshold + hysteresis
 */
@ConfigurationProperties(prefix = "monitor.alerts")
public record AlertRules(double warningBelow, double criticalBelow, int trendWindow, double trendSlope,
        double trendClearSlope, int minWindowRows, int closeAfter, double hysteresis) {

    /** Values designed on the validation engines (results/alert_rule_design_val.json). */
    public static AlertRules defaults() {
        return new AlertRules(60, 30, 30, -2.0, -1.5, 30, 5, 10);
    }
}
