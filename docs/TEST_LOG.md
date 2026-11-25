# Test Log — Beat-Draw Showdown

Write down every test and every config change. This is your "technical difficulty" evidence for the report.
`pc/scores.csv` (Level 1 rounds), `pc/matches.csv` (full matches) and `pc/disconnects.csv` (every drop-out,
reconnect and self-restart) are saved automatically — attach them too.

## 0. Measurements with `pc/bench.py` (v5) — one wand at a time, arena closed
Each run prints a ready-made row for this table and saves a CSV in `pc/bench_results/`.

| Date | Wand | Test | Size | Result | Notes |
|---|---|---|---|---|---|
| | BDS-1 | latency (`python bench.py latency BDS-1`) | 200 pings | | |
| | BDS-1 | gestures (`python bench.py gestures BDS-1 --who <name>`) | 30 casts | | |
| | BDS-1 | battery (`python bench.py battery BDS-1`, full → empty) | | | |


Targets: one-way delay < 30 ms, 0–2 % lost; gestures ≥ 80 % for 3 different people; battery ≥ 1.5 h.

## 1. Spell recognition (spell practice mode, Serial Monitor open)
Each person does each spell 10 times. Write how many were recognised correctly.

| Date | Tester | Wand | Lightning /10 | Water /10 | Fire /10 | Wrong spell seen | Notes |
|---|---|---|---|---|---|---|---|
| | | BDS-1 | | | | | |


## 2. Config changes

| Date | File | Setting | Old → New | Why (what went wrong) | Better after? |
|---|---|---|---|---|---|
| | config.h | | | | |


## 3. Full matches with real players

| Date | Players | L1 score | L2 HP end | L3 winner | Match time | Bugs / feelings |
|---|---|---|---|---|---|---|
| | | | | | | |


## 4. Drop-outs (from `pc/disconnects.csv`)

| Date | Wand | Event (disconnect / restart WATCHDOG / BROWN-OUT) | Battery % | Level | What we changed |
|---|---|---|---|---|---|
| | | | | | |


## 5. Bugs

| Date | What happened | How to repeat | Fixed? (commit / change) |
|---|---|---|---|
| | | | |

