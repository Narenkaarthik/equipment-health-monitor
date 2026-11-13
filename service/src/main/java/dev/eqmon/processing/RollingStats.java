package dev.eqmon.processing;

/**
 * Mean, population standard deviation and least-squares slope of the last W values of one sensor,
 * updated in O(1) per new value. This is the sliding-window pattern: keep running sums and
 * subtract what leaves the window instead of re-summing it.
 *
 * <p>Sums are kept relative to an offset (the first value seen) so values near 9000 do not lose the
 * variance to floating-point cancellation, and they are rebuilt from the buffer every
 * {@value #RESYNC_EVERY} updates so rounding drift cannot accumulate over a long stream.
 */
public final class RollingStats {

    static final int RESYNC_EVERY = 1024;

    private final int capacity;
    private final double[] ring;
    private int head; // index of the oldest value
    private int size;
    private double offset;
    private boolean hasOffset;
    private double sy;   // sum of (x - offset)
    private double syy;  // sum of (x - offset)^2
    private double sjy;  // sum of position * (x - offset), position 0..size-1 oldest..newest
    private long updates;

    public RollingStats(int capacity) {
        if (capacity < 1) {
            throw new IllegalArgumentException("window must hold at least one value");
        }
        this.capacity = capacity;
        this.ring = new double[capacity];
    }

    public int size() {
        return size;
    }

    public int capacity() {
        return capacity;
    }

    /** Pushes a value; the oldest value leaves when the window is full. */
    public void add(double x) {
        if (!hasOffset) {
            offset = x;
            hasOffset = true;
        }
        double y = x - offset;
        if (size == capacity) {
            double y0 = ring[head] - offset;
            // slide: every position drops by one, the oldest leaves, the new one lands at position n-1
            sjy = sjy - sy + y0 + (size - 1) * y;
            sy = sy - y0 + y;
            syy = syy - y0 * y0 + y * y;
            ring[head] = x;
            head = (head + 1) % capacity;
        } else {
            sjy += size * y;
            sy += y;
            syy += y * y;
            ring[(head + size) % capacity] = x;
            size++;
        }
        if (++updates % RESYNC_EVERY == 0) {
            resync();
        }
    }

    public double mean() {
        return size == 0 ? Double.NaN : sy / size + offset;
    }

    public double std() {
        if (size == 0) {
            return Double.NaN;
        }
        double m = sy / size;
        double var = syy / size - m * m;
        return Math.sqrt(Math.max(var, 0.0));
    }

    public double slope() {
        if (size < 2) {
            return 0.0;
        }
        double n = size;
        double sx = n * (n - 1) / 2.0;
        double sxx = (n - 1) * n * (2 * n - 1) / 6.0;
        return (n * sjy - sx * sy) / (n * sxx - sx * sx);
    }

    /** Rebuilds the sums from the buffer; makes the running sums exact again. */
    void resync() {
        sy = 0;
        syy = 0;
        sjy = 0;
        for (int i = 0; i < size; i++) {
            double y = ring[(head + i) % capacity] - offset;
            sy += y;
            syy += y * y;
            sjy += i * y;
        }
    }

    /** Oldest to newest. */
    public double[] values() {
        double[] out = new double[size];
        for (int i = 0; i < size; i++) {
            out[i] = ring[(head + i) % capacity];
        }
        return out;
    }
}
