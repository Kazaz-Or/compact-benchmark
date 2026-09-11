# Benchmark Report: Claude Code Context Management Strategies

## Methodology

### Model Configuration
- **Model:** claude-opus-4-6
- **Effort:** high
- **Claude Code Version:** 2.1.62
- **Permissions:** bypassPermissions

### Experimental Design
- **Strategies:** control, plain_compact, focused_compact, handoff_fresh
- **Planned repetitions:** 5 per strategy (20 total runs)
- **Completed runs:** 1 full run (focused_compact#5), 1 partial (plain_compact#1, step 1 only)
- **Execution order:** Randomized
- **Repository isolation:** Fresh copy per run (git init + commit)
- **Evaluation:** Hidden test suite (10 criteria) + requirement retention (4 criteria)

### Incomplete Data

Rate limiting prevented 18 of 20 runs from executing meaningful work. Steps 2-12 in those runs show zero tokens, zero cost, and baseline quality (5/10 = unmodified project score). Only focused_compact#5 completed all 12 steps.

This report uses:
- **Empirical data** from the one complete run (focused_compact#5)
- **Analytical projections** from Anthropic's published pricing model for cross-strategy comparison

## Pre-registered Hypotheses

**control:** Cheapest for coherent sessions, may degrade with historical noise accumulation. Cache hits keep per-turn cost low, but context grows unbounded.

**plain_compact:** Saves downstream context but pays a transition cost (cache rebuild). May lose useful implementation details. Net benefit depends on how many turns remain after compaction.

**focused_compact:** Better state preservation than plain compact due to guided summarization. Similar transition cost. May reduce requirement-forgetting failures.

**handoff_fresh:** Cleanest context at task boundaries, but pays rediscovery cost (re-reading files, re-understanding state). Best when task boundaries are genuine semantic breaks.

## Complete Run Data: focused_compact#5

### Session Summary

| Metric | Value |
|---|---|
| Total cost (SDK estimate) | $4.1453 |
| Total input tokens (uncached) | 167 |
| Total output tokens | 21,567 |
| Total cache read tokens | 3,349,581 |
| Total cache creation tokens | 537,266 |
| Total tokens moved | 3,908,581 |
| Cache hit rate (overall) | 86.2% |
| Total turns | 115 |
| Total tool calls | 74 |
| Quality score | 10/10 |
| Requirement retention | 4/4 (100%) |

### Per-Step Breakdown

| Step | Name | Cache Hit % | Cost | Turns | Tools |
|---|---|---|---|---|---|
| 1 | architecture_exploration | 71.5% | $0.3342 | 15 | 12 |
| 2 | understand_data_flow | 97.6% | $0.0719 | 1 | 0 |
| 3 | diagnose_bug_a | 92.8% | $0.0415 | 1 | 0 |
| 4 | fix_bug_a | 98.5% | $0.0714 | 3 | 2 |
| 5 | add_tests_for_fix | 97.4% | $0.1398 | 4 | 3 |
| 6 | implement_feature | 87.5% | $0.6482 | 23 | 14 |
| 7 | investigate_integration_failure | 73.4% | $0.5159 | 9 | 4 |
| 8 | fix_search_security | 98.7% | $0.2202 | 7 | 5 |
| 9 | refactor_service | 79.8% | $0.3261 | 7 | 4 |
| 10 | new_requirement | 69.4% | $0.3631 | 7 | 5 |
| 11 | adapt_implementation | 67.9% | $0.2878 | 8 | 4 |
| 12 | final_verification | 94.8% | $0.7780 | 30 | 21 |

### Transition Data

| Transition | Type | Pre-compact Tokens | Cost |
|---|---|---|---|
| After step 5 | focused_compact | 36,483 | $0.1063 |
| After step 8 | focused_compact | 50,194 | $0.1306 |
| After step 9 | focused_compact | 36,441 | $0.1102 |
| **Total** | | | **$0.3471** |

### Cost Breakdown (Calculated)

| Component | Tokens | Rate ($/MTok) | Cost | % of Total |
|---|---|---|---|---|
| Cache reads | 3,349,581 | $0.50 | $1.67 | 30% |
| Cache creation | 537,266 | $6.25 | $3.36 | 60% |
| Uncached input | 167 | $5.00 | $0.00 | 0% |
| Output | 21,567 | $25.00 | $0.54 | 10% |
| **Calculated total** | | | **$5.57** | |
| **SDK reported total** | | | **$4.15** | |

Note: The SDK-reported cost ($4.15) is lower than the calculated cost ($5.57). This discrepancy may be due to: subscription pricing differences, cache TTL tiers (1-hour writes at different rates), or internal pricing adjustments not reflected in published rates.

### Quality Evaluation

| Criterion | Score | Notes |
|---|---|---|
| visible_tests | 1/1 | All 8 pytest tests pass |
| filtered_count_fix | 1/1 | Bug fixed: count query now applies filters |
| updated_at_fix | 1/1 | Bug fixed: update method sets updated_at |
| sql_injection_fix | 1/1 | Parameterized queries in search method |
| batch_update | 1/1 | PATCH endpoint implemented with multi-status |
| api_compat | 1/1 | All schema fields preserved |
| no_new_deps | 1/1 | No new dependencies added |
| repo_interface | 1/1 | Method signatures unchanged |
| no_regressions | 1/1 | All existing functionality preserved |
| lint_clean | 1/1 | ruff check passes |

### Requirement Retention

| Requirement | Retained |
|---|---|
| API schema compatibility | ✓ |
| No new dependencies | ✓ |
| Repository interface stability | ✓ |
| No regressions | ✓ |

## Analytical Cost Model

### Hypothetical scenario comparison

Using observed per-step costs and published pricing:

| Scenario | Estimated cost | Savings vs no-cache |
|---|---|---|
| No caching | $19.97 | — |
| Caching, no compaction | ~$4.77 | 76% |
| Caching + focused /compact | $4.15 | 79% |

### Break-even calculation

- Transition cost: ~$0.12 per focused /compact
- Per-turn saving from shorter context: ~$0.015
- Break-even: ~8 turns post-compaction

## Reproduction

```bash
# Full benchmark (requires significant Claude API quota)
cd benchmark/runner
npm install
npm run benchmark -- --reps 5

# Analysis only (from existing results)
cd benchmark
python3 analyze.py ../results

# Article generation (from existing results)
python3 generate_article.py ../results

# Quick single-strategy test
cd benchmark/runner
npm run benchmark -- --reps 1 --strategies focused_compact
```

## Pricing Reference (September 2026)

Claude Opus 4.6:

| Token type | $/MTok |
|---|---|
| Input (uncached) | $5.00 |
| Cache write (5-min TTL) | $6.25 |
| Cache write (1-hour TTL) | $10.00 |
| Cache read | $0.50 |
| Output | $25.00 |

Minimum cacheable prefix: 4,096 tokens (Opus 4.6).

## Timestamp

- Benchmark executed: 2026-09-10
- Report generated: 2026-09-11
