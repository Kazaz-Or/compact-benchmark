# Benchmark Results

## Data completeness

Of 20 planned runs (4 strategies × 5 repetitions), only **1 run completed fully**:

- `focused_compact_run5.json` — **complete**, 10/10 quality, $4.15
- `plain_compact_run1.json` — **partial** (step 1 only), $0.24

The remaining 18 runs were rate-limited: they report `completed: true` but have zero tokens and baseline quality (5/10 = unmodified project). This happened because the benchmark exhausted the Claude subscription quota after the first ~2 runs.

## How to read the data

Each `raw/*.json` file contains:
- `steps[]` — per-step token counts, cost, tool calls, wall clock time
- `transitions[]` — compaction/handoff costs and pre/post token counts
- `qualityScore` — hidden test results (10 criteria)
- `requirementRetention` — which early constraints survived
- `total*` — aggregate metrics

The `benchmark_results.json` file contains all runs plus metadata (model, version, hypotheses).

## Regenerating graphs

```bash
python3 ../generate_final.py
```
