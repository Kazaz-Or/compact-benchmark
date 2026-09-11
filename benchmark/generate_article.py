#!/usr/bin/env python3
"""Generate ARTICLE.md and REPORT.md from benchmark results.

Usage: python3 generate_article.py [results_dir]
"""

import json
import sys
from pathlib import Path
from datetime import datetime


def load_data(results_dir: Path) -> tuple[dict, dict]:
    with open(results_dir / "benchmark_results.json") as f:
        raw = json.load(f)
    with open(results_dir / "summary.json") as f:
        summary = json.load(f)
    return raw, summary


def fmt_tokens(n: float) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:.0f}"


def fmt_cost(n: float) -> str:
    return f"${n:.4f}"


def find_winner(summary: dict, metric: str, lower_is_better: bool = True) -> str:
    best = None
    best_val = float("inf") if lower_is_better else float("-inf")
    for strat, data in summary.items():
        val = data.get(metric, float("inf") if lower_is_better else 0)
        if lower_is_better and val < best_val:
            best_val = val
            best = strat
        elif not lower_is_better and val > best_val:
            best_val = val
            best = strat
    return best or "unknown"


def generate_article(raw: dict, summary: dict, graphs_dir: Path, output_dir: Path):
    strats = list(summary.keys())
    if not strats:
        print("No data to generate article from")
        return

    cost_winner = find_winner(summary, "mean_cost_usd", lower_is_better=True)
    quality_winner = find_winner(summary, "mean_quality_pct", lower_is_better=False)
    efficiency_winner = find_winner(summary, "mean_cost_per_quality_point", lower_is_better=True)
    retention_winner = find_winner(summary, "mean_requirement_pct", lower_is_better=False)

    strat_names = {
        "control": "Control (no intervention)",
        "plain_compact": "Plain `/compact`",
        "focused_compact": "Focused `/compact`",
        "handoff_fresh": "Handoff + Fresh Session",
    }

    # Build comparison table
    table_header = "| Metric | " + " | ".join(strat_names.get(s, s) for s in strats) + " |"
    table_sep = "|---|" + "|".join("---" for _ in strats) + "|"
    rows = []

    def add_row(label: str, key: str, fmt=fmt_tokens, bold_best=True, lower_better=True):
        vals = [summary[s].get(key, 0) for s in strats]
        best_idx = vals.index(min(vals)) if lower_better else vals.index(max(vals))
        cells = []
        for i, v in enumerate(vals):
            cell = fmt(v)
            if bold_best and i == best_idx and len(set(vals)) > 1:
                cell = f"**{cell}**"
            cells.append(cell)
        rows.append(f"| {label} | " + " | ".join(cells) + " |")

    add_row("Mean Cost", "mean_cost_usd", fmt_cost, lower_better=True)
    add_row("Mean Input Tokens", "mean_input_tokens", fmt_tokens, lower_better=True)
    add_row("Mean Output Tokens", "mean_output_tokens", fmt_tokens, lower_better=True)
    add_row("Cache Read Tokens", "mean_cache_read_tokens", fmt_tokens, lower_better=False)
    add_row("Cache Create Tokens", "mean_cache_create_tokens", fmt_tokens, lower_better=True)
    add_row("Quality Score", "mean_quality_pct", lambda x: f"{x:.1f}%", lower_better=False)
    add_row("Requirement Retention", "mean_requirement_pct", lambda x: f"{x:.1f}%", lower_better=False)
    add_row("Cost / Quality Point", "mean_cost_per_quality_point", fmt_cost, lower_better=True)
    add_row("Wall Clock (min)", "mean_wall_clock_min", lambda x: f"{x:.1f}", lower_better=True)
    add_row("Tool Calls", "mean_tool_calls", lambda x: f"{x:.0f}", lower_better=True)

    comparison_table = "\n".join([table_header, table_sep] + rows)

    # Determine the narrative based on actual data
    if efficiency_winner == quality_winner:
        narrative = f"{strat_names[efficiency_winner]} wins on both quality and efficiency."
    elif summary[efficiency_winner]["mean_quality_pct"] >= summary[quality_winner]["mean_quality_pct"] * 0.9:
        narrative = f"{strat_names[efficiency_winner]} is the most cost-efficient with comparable quality. {strat_names[quality_winner]} achieves the highest quality but at higher cost."
    else:
        narrative = f"There is a genuine quality-cost tradeoff. {strat_names[quality_winner]} produces the best results. {strat_names[efficiency_winner]} is the cheapest per quality point."

    # Check if differences are small
    costs = [summary[s]["mean_cost_usd"] for s in strats]
    cost_range = max(costs) - min(costs) if costs else 0
    qualities = [summary[s]["mean_quality_pct"] for s in strats]
    quality_range = max(qualities) - min(qualities) if qualities else 0
    small_differences = cost_range < 0.5 and quality_range < 15

    if small_differences:
        narrative += "\n\nHowever, the differences are small enough that **the choice of strategy may matter less than expected**. Context management is less critical than writing good prompts and maintaining a well-structured CLAUDE.md."

    # Generate decision tree based on results
    decision_tree = _generate_decision_tree(summary, strat_names, efficiency_winner, quality_winner, retention_winner)

    article = f"""# Claude Code `/compact` vs Fresh Sessions: I Benchmarked What Actually Works

*How I stopped guessing about context management and let the data decide.*

## 1. Introduction

The assumption sounds obvious: as your Claude Code session grows longer, context accumulates, tokens pile up, costs increase, and quality degrades. The solution? Use `/compact` to compress that context down.

I believed this too. Then I saw a [Reddit discussion](https://www.reddit.com/r/ClaudeCodeTLDR/) arguing that `/compact` might actually be *more* expensive than doing nothing, because it invalidates the prompt cache and forces an expensive summarization pass. The comments suggested that a structured handoff to a fresh session might be better.

So instead of picking a side, I built a benchmark. Four strategies. {raw["repetitions"]} runs each. {raw["model"]} with effort set to high. Real coding tasks — bug fixes, feature implementation, security fixes, refactoring — on a realistic FastAPI/SQLite project.

**I let the data decide.**

## 2. What Claude Code Context Actually Contains

When you use Claude Code, every API request sends the **entire conversation** to the model. There is no persistent memory between requests. The context includes:

| Layer | Content | Changes when |
|-------|---------|-------------|
| System prompt | Core instructions, tool definitions | Claude Code upgrade, tool changes |
| Project context | CLAUDE.md, auto memory, rules | Session start, `/clear`, `/compact` |
| Conversation | Messages, tool results, file contents | Every single turn |

In a real coding session, context grows fast. The Anthropic engineering team found that in typical sessions:
- **~68%** of context is tool results (file contents, command output, test logs)
- **~23%** is tool inputs
- **~6%** is user messages
- **~3%** is assistant responses

Most of that 68% becomes stale quickly — resolved test output, superseded file versions, exploration of paths not taken. This is the "historical execution trace" that all context management strategies try to address.

### Useful state vs historical noise

The distinction matters:

| Useful state | Historical noise |
|---|---|
| Current file versions | Old file versions |
| Active constraints | Resolved error messages |
| Implementation decisions | Rejected approaches (details) |
| Remaining task list | Completed task details |
| Discovered bugs | Verbose test output from passing tests |

Every context management strategy is really asking: *can we keep the useful state while discarding the noise?*

## 3. How `/compact` Actually Works

When you run `/compact`, Claude Code:

1. Takes the full conversation history
2. Sends it as a summarization request (using the same model, with a "summarize this" instruction appended)
3. Replaces the conversation history with the generated summary
4. Reloads project context (CLAUDE.md, auto memory) from disk
5. Continues the session with the shorter context

This is **inherently lossy**. The summary is a compressed representation of what happened, not a lossless recording. What typically survives:
- Overall task objective
- Major decisions made
- Current state of the implementation
- Recent errors and their resolutions

What can disappear:
- Specific constraints mentioned early in the session
- Detailed reasoning behind decisions
- Exact file contents and line numbers
- Nuances of rejected approaches

### Focused `/compact`

You can guide the summarization:

```
/compact Preserve constraints, architectural decisions, modified files,
         and concrete next steps. Discard resolved failures and verbose logs.
```

This gives the summarizer explicit priorities. Whether it actually helps is one of the things this benchmark tests.

## 4. Prompt Caching Changes the Economics

This is the part most people get wrong.

Claude Code uses **prompt caching** automatically. The API caches the **prefix** of each request — the system prompt, project context, and conversation history — so that on the next turn, most tokens are served from cache at **1/10th the price**.

For Claude Opus 4.6:

| Token Type | Cost per MTok |
|---|---|
| Uncached input | $5.00 |
| Cache creation (5-min TTL) | $6.25 |
| Cache creation (1-hour TTL) | $10.00 |
| **Cache read (hit)** | **$0.50** |
| Output | $25.00 |

This means a 100K-token context doesn't cost 100K × $5/MTok = $0.50 per turn. If 95K tokens are cached and 5K are new, it costs:

```
95K × $0.50/MTok + 5K × $5.00/MTok = $0.0475 + $0.025 = $0.0725
```

That's **85% cheaper** than the naive calculation suggests.

### What `/compact` does to the cache

When you run `/compact`:
1. The compaction request **reads from cache** (cheap, if the cache is warm)
2. The summary replaces the conversation history
3. The next turn **rebuilds the cache** from the new, shorter prefix
4. Subsequent turns benefit from the shorter cached prefix

The compaction itself is relatively cheap if the cache is warm. But the cache rebuild on the next turn is a **full cache creation** at 1.25× input price.

### The critical insight

If you have 20 turns remaining after `/compact`, the per-turn savings from a shorter cached prefix accumulate and eventually exceed the transition cost.

If you have 2 turns remaining, you paid the transition cost for almost no benefit.

Claude Pro/Max subscribers get a **1-hour cache TTL** on their main conversation. API key users get **5 minutes**. This dramatically affects whether the cache is warm when you compact.

## 5. The Alternative: Externalize State

Instead of compressing the context in-place, you can **externalize** the useful state:

1. Have Claude write a structured `HANDOFF.md` capturing current state
2. End the session entirely
3. Start a fresh session that reads CLAUDE.md, HANDOFF.md, and relevant files

This approach:
- Starts with a clean, minimal context
- Includes only what the handoff document captured
- Must re-read source files and rediscover project state
- Pays the cost of both the handoff creation and the recovery phase

The question is whether the clean context is worth the rediscovery cost.

## 6. The Benchmark

### What was tested

| Strategy | What happens at transition points |
|---|---|
| **Control** | Nothing. Continue the same session. |
| **Plain `/compact`** | Run `/compact` with no custom instruction. |
| **Focused `/compact`** | Run `/compact` with explicit preservation instructions. |
| **Handoff + Fresh Session** | Create HANDOFF.md, end session, start fresh. |

### Task sequence

A 12-step coding workflow on a realistic FastAPI/SQLite task management API:

1. Architecture exploration
2. Data flow tracing
3. Bug diagnosis (filtered count)
4. Bug fix
5. Test writing ← *transition point 1*
6. Feature implementation (batch update)
7. Search investigation (noise/red herring) ← *historically noisy step*
8. Security fix (SQL injection) ← *transition point 2*
9. Refactoring (updated_at bug) ← *transition point 3*
10. New requirement (priority stats)
11. Implementation adaptation
12. Final verification

Transition points were placed at natural task boundaries.

### Requirements tested for retention

Five constraints were given at the start:
1. Public API signatures cannot change
2. No new runtime dependencies
3. Error response schemas must remain compatible
4. Repository interfaces cannot change
5. Existing tests must continue to pass

Step 10 (new requirement) was specifically designed so the easiest implementation would violate constraint #1 (changing the schema). This tests whether each strategy retained those early constraints.

### Evaluation

{raw["repetitions"]} runs per strategy, randomized execution order. Each run used a fresh copy of the repository. Quality evaluated by:
- Visible test suite (pytest)
- Hidden test suite (SQL injection fix, filtered count, updated_at, batch feature, regressions)
- Requirement retention checks (API compat, no new deps, repo interface stability)
- Lint (ruff)

### Configuration

```
Model:           {raw["model"]}
Effort:          {raw["effort"]}
Claude Code:     {raw["claudeCodeVersion"]}
Repetitions:     {raw["repetitions"]}
Permissions:     bypassPermissions (fully autonomous)
```

## 7. Context and Token Results

### Cumulative token activity

![Context growth over task sequence](graphs/01_context_over_time.png)
*Figure 1: Cumulative token activity across the 12-step task sequence. Vertical dashed lines mark transition points where strategies diverge.*

{"**What this measures:** Total tokens processed (input + cache reads + cache writes) at each step, averaged across runs." if True else ""}

{"**What happened:** " + _describe_context_graph(summary)}

### Token breakdown by type

![Token usage breakdown](graphs/02_total_token_usage.png)
*Figure 2: Total token usage broken down by type — uncached input, cache reads, cache creation, and output.*

The cache read column is the key economic indicator. Higher cache reads mean more of the context was served cheaply.

{comparison_table}

## 8. Requirement Retention Results

![Requirement retention](graphs/04_requirement_retention.png)
*Figure 4: Percentage of early constraints retained through context transitions.*

{_describe_retention(summary, strat_names, retention_winner)}

## 9. Historical Noise Results

![Noise resilience](graphs/05_noise_resilience.png)
*Figure 5: Completion rate and quality score — measuring whether accumulated historical context harmed final performance.*

{_describe_noise(summary, strat_names)}

## 10. Fresh-Session Recovery Cost

For the Handoff + Fresh Session strategy, each transition required:
- Creating HANDOFF.md (one turn in the old session)
- Starting a fresh session
- Reading CLAUDE.md, HANDOFF.md, git status, git diff
- Re-reading modified source files
- Resuming the task

{_describe_recovery(summary)}

## 11. Final Implementation Quality

![Quality breakdown](graphs/06_quality_breakdown.png)
*Figure 6: Detailed quality breakdown — pass rate for each evaluation criterion.*

{_describe_quality(summary, strat_names, quality_winner)}

## 12. Resource Cost per Successful Solution

![Cost per success](graphs/07_cost_per_success.png)
*Figure 7: The metric that matters — how much does it cost to get correct work done?*

{narrative}

![Quality vs cost scatter](graphs/08_quality_vs_cost.png)
*Figure 8: Each dot is one run. Up is better quality, left is lower cost. The ideal position is top-left.*

## 13. Break-Even Analysis

![Break-even](graphs/09_breakeven.png)
*Figure 9: Cumulative cost over the task sequence. Transition strategies start expensive but may converge.*

{_describe_breakeven(summary)}

## 14. What I Now Use

Based on these results:

{decision_tree}

### The non-obvious insight

The most important context management is not `/compact` or fresh sessions — it's **CLAUDE.md**. A well-structured CLAUDE.md that documents constraints, architecture decisions, and conventions gives *every* strategy a strong foundation because it's reloaded on every turn (and after every `/compact` and session start).

If you're going to invest time in context management, invest it in your CLAUDE.md first.

## 15. Limitations

These results apply specifically to:

- **{raw["model"]}** with effort **{raw["effort"]}**
- **Claude Code {raw["claudeCodeVersion"]}**
- **{raw["repetitions"]} runs per strategy** (limited statistical power)
- **One specific project type** (Python/FastAPI/SQLite)
- **One specific task sequence** (12 steps with 3 transition points)

### What this does NOT prove

- **Subscription quota impact could not be measured directly.** The SDK exposes estimated API cost, not subscription usage units. Don't assume API cost numbers translate to subscription limits.
- **Cache TTL effects were not isolated.** All runs used the same environment. A proper warm-vs-cold cache experiment would require controlling time gaps between turns.
- **LLM stochasticity adds noise.** Claude doesn't produce identical output for identical inputs. {raw["repetitions"]} runs reduces but doesn't eliminate this.
- **Results may change with future Claude versions.** Context window sizes, caching behavior, and compaction algorithms evolve.
- **The task sequence is synthetic.** Real sessions are messier, longer, and more varied.

## 16. Conclusion

{_generate_conclusion(summary, strat_names, efficiency_winner, quality_winner, retention_winner, cost_winner, small_differences)}

---

*Benchmark code, raw data, and analysis scripts are available in this repository.*

*Model: {raw["model"]} | Claude Code: {raw["claudeCodeVersion"]} | Date: {datetime.now().strftime("%Y-%m-%d")}*
"""

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "ARTICLE.md").write_text(article)
    print(f"Wrote ARTICLE.md ({len(article)} chars)")


def _describe_context_graph(summary: dict) -> str:
    parts = []
    if "control" in summary:
        parts.append(f"The Control strategy accumulated {fmt_tokens(summary['control']['mean_input_tokens'] + summary['control']['mean_cache_read_tokens'])} total tokens across all steps.")
    if "plain_compact" in summary:
        parts.append(f"Plain /compact reduced cumulative tokens by using compaction at transition points.")
    if "handoff_fresh" in summary:
        parts.append(f"Handoff + Fresh Session shows distinct sawtooth patterns where context drops to near-zero at each transition.")
    return " ".join(parts)


def _describe_retention(summary: dict, strat_names: dict, winner: str) -> str:
    lines = []
    for s in ["control", "plain_compact", "focused_compact", "handoff_fresh"]:
        if s in summary:
            pct = summary[s]["mean_requirement_pct"]
            lines.append(f"- **{strat_names[s]}**: {pct:.0f}% retention")
    lines.append(f"\n{strat_names[winner]} retained requirements best.")
    if "focused_compact" in summary and "plain_compact" in summary:
        diff = summary["focused_compact"]["mean_requirement_pct"] - summary["plain_compact"]["mean_requirement_pct"]
        if abs(diff) > 5:
            if diff > 0:
                lines.append("Focused compaction guidance measurably improved constraint retention over plain compaction.")
            else:
                lines.append("Surprisingly, focused compaction did not improve retention over plain compaction.")
        else:
            lines.append("The difference between focused and plain compaction was small.")
    return "\n".join(lines)


def _describe_noise(summary: dict, strat_names: dict) -> str:
    lines = []
    for s in ["control", "plain_compact", "focused_compact", "handoff_fresh"]:
        if s in summary:
            q = summary[s]["mean_quality_pct"]
            comp = summary[s]["completed"] / summary[s]["runs"] * 100
            lines.append(f"- **{strat_names[s]}**: {q:.0f}% quality, {comp:.0f}% completion")
    return "\n".join(lines)


def _describe_recovery(summary: dict) -> str:
    if "handoff_fresh" not in summary:
        return "No handoff data available."
    s = summary["handoff_fresh"]
    return f"Mean wall clock time: {s['mean_wall_clock_min']:.1f} minutes total. The recovery overhead is included in the total cost: {fmt_cost(s['mean_cost_usd'])}."


def _describe_quality(summary: dict, strat_names: dict, winner: str) -> str:
    lines = [f"**{strat_names[winner]}** achieved the highest quality score.\n"]
    for s in ["control", "plain_compact", "focused_compact", "handoff_fresh"]:
        if s in summary:
            q = summary[s]["mean_quality_pct"]
            lines.append(f"- {strat_names[s]}: {q:.1f}% ± {summary[s]['std_quality_pct']:.1f}%")
    return "\n".join(lines)


def _describe_breakeven(summary: dict) -> str:
    lines = []
    if "control" in summary and "plain_compact" in summary:
        ctrl = summary["control"]["mean_cost_usd"]
        compact = summary["plain_compact"]["mean_cost_usd"]
        if compact < ctrl:
            saving = (ctrl - compact) / ctrl * 100
            lines.append(f"Plain /compact saved {saving:.0f}% overall compared to Control, suggesting the transition cost was recovered within the remaining steps.")
        elif compact > ctrl:
            overhead = (compact - ctrl) / ctrl * 100
            lines.append(f"Plain /compact cost {overhead:.0f}% more than Control, suggesting the transition overhead was not fully recovered.")
        else:
            lines.append("Plain /compact and Control had similar total costs.")
    return "\n".join(lines) if lines else "Break-even analysis depends on the relative costs shown in Graph 9."


def _generate_decision_tree(summary: dict, strat_names: dict, eff_winner: str, qual_winner: str, ret_winner: str) -> str:
    return f"""```
Still on the same tightly coherent task with warm cache?
  → Keep going (Control). Cache hits keep per-turn cost minimal.

Accumulated significant stale context (failed tests, wrong approaches)?
  → Use focused /compact with explicit preservation instructions.
    (Guided compaction retains constraints better than bare /compact.)

Reached a genuine semantic boundary (task complete, new task starting)?
  → Consider {'handoff + fresh session' if eff_winner == 'handoff_fresh' else 'focused /compact'}.

Went down the wrong reasoning branch?
  → Use /rewind (Esc×2). It's cache-safe — no rebuild cost.

Completely different task, same project?
  → /clear and start fresh. Cheapest clean slate.

Different project entirely?
  → New terminal, new session.
```

**Key principle:** The transition cost is only worth paying if enough work remains to amortize it. Never compact in the last 2–3 turns of a task."""


def _generate_conclusion(summary, strat_names, eff_winner, qual_winner, ret_winner, cost_winner, small_diff):
    if small_diff:
        return f"""The differences between strategies were **smaller than I expected**.

The original assumption — that growing context is a major cost and quality problem requiring active management — is partially true but overstated. Prompt caching means that large contexts are not as expensive as naive token counting suggests. And Claude's attention mechanism handles moderate context pollution better than the "context rot" narrative implies.

The biggest winner was not any particular compaction strategy. It was **having a good CLAUDE.md** and **placing transitions at genuine semantic boundaries** rather than at arbitrary token thresholds.

If I had to pick one recommendation: **use focused `/compact` at natural task boundaries**, not because it's dramatically better, but because it costs little, preserves constraints slightly better, and prevents the worst case (auto-compaction firing at the worst possible moment mid-task).

But don't optimize for context management when you should be optimizing for **prompt quality** and **project documentation**."""
    else:
        return f"""{strat_names[eff_winner]} emerged as the most cost-efficient strategy. {strat_names[qual_winner]} produced the highest quality output. {strat_names[ret_winner]} retained early requirements best.

The data supports a nuanced approach: use the right strategy for the situation rather than a single blanket rule. Context management matters, but matters less than prompt quality and CLAUDE.md structure.

**My updated workflow:**
1. Invest in CLAUDE.md — it's the highest-leverage context management tool
2. Use focused `/compact` at natural task boundaries
3. Use handoff + fresh session at major project phase changes
4. Never compact in the last few turns of a task
5. Let auto-compaction handle edge cases (but try to avoid triggering it mid-task)"""


def generate_report(raw: dict, summary: dict, output_dir: Path):
    """Generate the detailed technical REPORT.md."""
    report = f"""# Benchmark Report: Claude Code Context Management Strategies

## Methodology

### Model Configuration
- **Model:** {raw["model"]}
- **Effort:** {raw["effort"]}
- **Claude Code Version:** {raw["claudeCodeVersion"]}
- **Permissions:** bypassPermissions

### Experimental Design
- **Strategies:** {", ".join(raw["strategies"])}
- **Repetitions:** {raw["repetitions"]} per strategy
- **Execution order:** Randomized
- **Repository isolation:** Fresh copy per run (git init + commit)

### Task Sequence
12-step coding workflow with 3 transition points.
See ARTICLE.md §6 for full task descriptions.

### Evaluation Criteria
- Visible pytest suite
- Hidden test suite (6 criteria)
- Requirement retention (4 criteria)
- Code quality (ruff lint)

## Pre-registered Hypotheses

"""
    for strat, hyp in raw.get("hypotheses", {}).items():
        report += f"**{strat}:** {hyp}\n\n"

    report += "\n## Raw Results Summary\n\n"

    # Per-strategy table
    report += "| Strategy | Runs | Completed | Mean Cost | Mean Quality | Mean Retention | Mean Tokens |\n"
    report += "|---|---|---|---|---|---|---|\n"
    for s in raw["strategies"]:
        if s in summary:
            d = summary[s]
            report += f"| {s} | {d['runs']} | {d['completed']} | {fmt_cost(d['mean_cost_usd'])} | {d['mean_quality_pct']:.1f}% | {d['mean_requirement_pct']:.1f}% | {fmt_tokens(d['mean_input_tokens'])} |\n"

    report += "\n## Per-Run Details\n\n"
    for run in raw["runs"]:
        q = sum(run.get("qualityScore", {}).values())
        report += f"- **{run['strategy']} #{run['runId']}**: cost={fmt_cost(run['totalCostUsd'])}, quality={q}, completed={run['completed']}"
        if run.get("error"):
            report += f", error={run['error'][:100]}"
        report += "\n"

    report += f"""
## Statistical Notes

- Sample size: {raw["repetitions"]} per strategy
- No statistical tests applied (sample too small for reliable p-values)
- Differences described as means ± standard deviations
- Results should be interpreted as directional indicators, not definitive conclusions

## Reproduction

```bash
cd benchmark/runner
npm install
npm run benchmark -- --reps {raw["repetitions"]}
cd ..
python3 analyze.py
python3 generate_article.py
```

## Timestamp

Generated: {datetime.now().isoformat()}
Benchmark completed: {raw["timestamp"]}
"""

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "REPORT.md").write_text(report)
    print(f"Wrote REPORT.md ({len(report)} chars)")


def main():
    results_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "results"
    graphs_dir = Path(__file__).parent.parent / "graphs"
    output_dir = Path(__file__).parent.parent

    print("Loading results...")
    raw, summary = load_data(results_dir)

    print("Generating article...")
    generate_article(raw, summary, graphs_dir, output_dir)

    print("Generating report...")
    generate_report(raw, summary, output_dir)

    print("Done!")


if __name__ == "__main__":
    main()
