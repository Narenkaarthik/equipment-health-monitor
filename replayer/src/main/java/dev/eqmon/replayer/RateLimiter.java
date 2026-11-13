package dev.eqmon.replayer;

import java.util.concurrent.locks.LockSupport;

/**
 * A fleet-wide token bucket shared by every machine thread. {@code acquire(n)} blocks until n
 * readings may be sent so that, over any second, at most {@code perSecond} readings leave.
 */
public final class RateLimiter {

    private final double nanosPerPermit;
    private long nextFreeAt = System.nanoTime();

    public RateLimiter(double perSecond) {
        if (perSecond <= 0) {
            throw new IllegalArgumentException("rate must be positive");
        }
        this.nanosPerPermit = 1e9 / perSecond;
    }

    public void acquire(int permits) {
        long wakeAt;
        synchronized (this) {
            long now = System.nanoTime();
            long start = Math.max(now, nextFreeAt);
            nextFreeAt = start + (long) (permits * nanosPerPermit);
            wakeAt = start;
        }
        long wait;
        while ((wait = wakeAt - System.nanoTime()) > 0) {
            LockSupport.parkNanos(wait);
        }
    }
}
