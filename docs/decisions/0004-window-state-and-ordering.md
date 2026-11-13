# 0004: Where window state lives, what happens on restart, and the ordering rule

**Status:** accepted (stage 2)

## Window state

Each machine has a window of its last W = 30 readings plus running sums per sensor
(`RollingStats`). The features of a reading are the mean, standard deviation and slope of each
sensor over that window, so the window *is* the processor's state.

### Options

1. **In memory only.** Fastest; a restart forgets every window and the first 30 readings after a
   restart are scored on a short window.
2. **Redis, written after every applied reading.** One `SET window:{id}` of about 6 KB. A restart
   reloads a machine's window lazily when its next reading arrives.
3. **Rebuild from PostgreSQL on restart** (`SELECT ... ORDER BY cycle DESC LIMIT 30` per machine).
   No extra system, but one query per machine on first contact and the database becomes the hot
   path for state.

### Decision

Option 2, with option 3's query kept as the operator's fallback if Redis is lost (`readings` has
everything needed). Redis is already the natural home of "latest state per machine" for the
dashboard; the window snapshot rides along. Cost: one Redis write per reading (sub-millisecond,
pipelined by Lettuce). The `no-redis` configuration (`monitor.window.store=memory`) exists for
tests and single-process demos and accepts option 1's loss on restart.

### What a restart loses

Nothing that was applied: the window snapshot is written before the features are handed on, so
a crash after the write replays the same reading as LATE (idempotent). A crash between the
database insert and the snapshot write loses that one reading's effect on the window until the
next reading arrives; the reading itself is in PostgreSQL. Stage 5 closes this gap by making the
Kafka consumer re-deliver the message.

## Ordering rule

The cycle number is the machine's clock. For a machine whose last applied cycle is `last`:

| arriving cycle | outcome | window | features produced | counted as |
| --- | --- | --- | --- | --- |
| `last + 1` | APPLIED | append | yes | `monitor.readings.processed{outcome=applied}` |
| `> last + 1` | GAP | append; the gap is logged | yes | `outcome=gap` |
| `<= last` | LATE | unchanged | no | `outcome=late` |

Why: a reading that arrives after a later cycle was already scored cannot change a decision that
was already made, and silently inserting it into the middle of the window would make the same
cycle produce two different feature vectors depending on arrival order. A gap is tolerated
because the window is defined as "the last W observations", not "the last W cycles"; the gap
count is exposed so an operator can see a flaky sensor link. The replayer never produces either
case; the unit tests in `MachineWindowTest` do.
