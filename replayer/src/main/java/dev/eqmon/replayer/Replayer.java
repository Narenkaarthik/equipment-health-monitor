package dev.eqmon.replayer;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicLong;
import picocli.CommandLine;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;

/**
 * Replays a C-MAPSS file as a live stream: each engine becomes a machine, each row a reading posted
 * in cycle order. N machines stream concurrently (one virtual thread each) at a fleet-wide rate of R
 * readings per second, so the service sees interleaved traffic the way a real fleet would produce it.
 */
@Command(name = "replayer", mixinStandardHelpOptions = true, description = "Replay C-MAPSS readings to the ingest API.")
public final class Replayer implements Callable<Integer> {

    @Option(names = {"-f", "--file"}, required = true, description = "C-MAPSS text file, e.g. data/raw/train_FD001.txt")
    Path file;

    @Option(names = {"-u", "--url"}, defaultValue = "http://localhost:8080", description = "Service base URL (default: ${DEFAULT-VALUE})")
    String url;

    @Option(names = {"-n", "--machines"}, defaultValue = "100", description = "Number of engines to replay (default: ${DEFAULT-VALUE})")
    int machines;

    @Option(names = {"-r", "--rate"}, defaultValue = "200", description = "Fleet-wide readings per second (default: ${DEFAULT-VALUE})")
    double rate;

    @Option(names = {"-b", "--batch"}, defaultValue = "1", description = "Readings per POST, per machine (default: ${DEFAULT-VALUE})")
    int batch;

    @Option(names = {"--register"}, defaultValue = "true", negatable = true, description = "PUT /api/machines/{id} before streaming (default: ${DEFAULT-VALUE})")
    boolean register;

    @Option(names = {"--max-cycles"}, defaultValue = "0", description = "Stop each engine after this many cycles (0 = full life)")
    int maxCycles;

    @Option(names = {"--units"}, split = ",", description = "Explicit engine ids to replay (overrides --machines)")
    List<Integer> units;

    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    private final AtomicLong sent = new AtomicLong();
    private final AtomicLong failed = new AtomicLong();

    public static void main(String[] args) {
        System.exit(new CommandLine(new Replayer()).execute(args));
    }

    @Override
    public Integer call() throws Exception {
        Map<Integer, List<CmapssReader.Row>> byUnit = CmapssReader.read(file);
        List<Integer> ids = units != null && !units.isEmpty() ? units : byUnit.keySet().stream().limit(machines).toList();
        long totalRows = ids.stream().mapToLong(id -> rowsFor(byUnit, id).size()).sum();
        System.out.printf("replaying %d engines, %d readings, at %.0f readings/s, batch %d -> %s%n",
                ids.size(), totalRows, rate, batch, url);

        if (register) {
            for (int id : ids) {
                post("PUT", "/api/machines/" + id, "{\"name\":\"engine-" + String.format("%03d", id) + "\"}");
            }
        }

        RateLimiter limiter = new RateLimiter(rate);
        long start = System.nanoTime();
        try (ExecutorService pool = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<?>> futures = new ArrayList<>();
            for (int id : ids) {
                List<CmapssReader.Row> rows = rowsFor(byUnit, id);
                futures.add(pool.submit(() -> stream(rows, limiter)));
            }
            for (Future<?> f : futures) {
                f.get();
            }
        }
        double seconds = (System.nanoTime() - start) / 1e9;
        System.out.printf("done: sent %d readings (%d failed) in %.1f s = %.0f readings/s%n",
                sent.get(), failed.get(), seconds, sent.get() / Math.max(seconds, 1e-9));
        return failed.get() == 0 ? 0 : 1;
    }

    private List<CmapssReader.Row> rowsFor(Map<Integer, List<CmapssReader.Row>> byUnit, int id) {
        List<CmapssReader.Row> rows = byUnit.getOrDefault(id, List.of());
        return maxCycles > 0 && rows.size() > maxCycles ? rows.subList(0, maxCycles) : rows;
    }

    private void stream(List<CmapssReader.Row> rows, RateLimiter limiter) {
        for (int i = 0; i < rows.size(); i += batch) {
            List<CmapssReader.Row> chunk = rows.subList(i, Math.min(rows.size(), i + batch));
            limiter.acquire(chunk.size());
            StringBuilder body = new StringBuilder("[");
            for (int j = 0; j < chunk.size(); j++) {
                if (j > 0) {
                    body.append(',');
                }
                body.append(chunk.get(j).toJson());
            }
            body.append(']');
            int status = post("POST", "/api/readings", body.toString());
            if (status >= 200 && status < 300) {
                sent.addAndGet(chunk.size());
            } else {
                failed.addAndGet(chunk.size());
            }
        }
    }

    private int post(String method, String path, String json) {
        HttpRequest req = HttpRequest.newBuilder(URI.create(url + path))
                .timeout(Duration.ofSeconds(30))
                .header("Content-Type", "application/json")
                .method(method, HttpRequest.BodyPublishers.ofString(json))
                .build();
        for (int attempt = 1; attempt <= 3; attempt++) {
            try {
                HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
                if (resp.statusCode() < 500) {
                    if (resp.statusCode() >= 400) {
                        System.err.println(method + " " + path + " -> " + resp.statusCode() + " " + resp.body());
                    }
                    return resp.statusCode();
                }
                System.err.println(method + " " + path + " -> " + resp.statusCode() + " (attempt " + attempt + ")");
            } catch (Exception e) {
                System.err.println(method + " " + path + " failed: " + e.getMessage() + " (attempt " + attempt + ")");
            }
            try {
                Thread.sleep(200L * attempt);
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
                return -1;
            }
        }
        return -1;
    }
}
