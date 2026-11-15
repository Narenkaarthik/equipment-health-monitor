| Run         | Pipeline   |   Repeats | Readings/s   |   p50 ms | p95 ms     | p99 ms     |   Pool waits | Change                                                 |
|:------------|:-----------|----------:|:-------------|---------:|:-----------|:-----------|-------------:|:-------------------------------------------------------|
| before      | direct     |         3 | 4138 ± 133   |     9.79 | 22.8 ± 0.4 | 37.5 ± 1.7 |        30.4  | MONITOR_DB_POOL=10 monitor.ingest.cache-machines=false |
| after       | direct     |         3 | 4318 ± 382   |     7.9  | 22.7 ± 1.9 | 38.6 ± 4.6 |         1.35 | MONITOR_DB_POOL=40 monitor.ingest.cache-machines=false |
| after-cache | direct     |         3 | 4550 ± 516   |     7.48 | 21.9 ± 2.5 | 38.1 ± 6.3 |         1.26 | MONITOR_DB_POOL=40 monitor.ingest.cache-machines=true  |
| kafka       | kafka      |         3 | 4036 ± 456   |     8.47 | 24.3 ± 2.1 | 41.4 ± 5.9 |         3.63 | MONITOR_DB_POOL=40 monitor.ingest.cache-machines=true  |