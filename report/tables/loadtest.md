| Run    | Pipeline   |   Users |   Batch |   Readings/s |   p50 ms |   p95 ms |   p99 ms |   Pool waits | Change             |
|:-------|:-----------|--------:|--------:|-------------:|---------:|---------:|---------:|-------------:|:-------------------|
| before | direct     |      50 |       1 |         4235 |     9.51 |    21.8  |    36.11 |        32.85 |                    |
| after  | direct     |      50 |       1 |         4984 |     7    |    19.4  |    33.7  |         1.39 | MONITOR_DB_POOL=40 |
| kafka  | kafka      |      50 |       1 |         4606 |     7.8  |    20.43 |    34.12 |         3.52 | MONITOR_DB_POOL=40 |