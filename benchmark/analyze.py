#!/usr/bin/env python3
"""Analyze benchmark results and generate graphs + reports.

Usage: python3 analyze.py [results_dir]
Default results_dir: ../results
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import pandas as pd
import numpy as np

# --- Config ---
STRATEGY_LABELS = {
    "control": "Control\n(no intervention)",
    "plain_compact": "Plain\n/compact",
    "focused_compact": "Focused\n/compact",
    "handoff_fresh": "Handoff +\nFresh Session",
}
STRATEGY_COLORS = {
    "control": "#4C72B0",
    "plain_compact": "#DD8452",
    "focused_compact": "#55A868",
    "handoff_fresh": "#C44E52",
}
STRATEGY_ORDER = ["control", "plain_compact", "focused_compact", "handoff_fresh"]


def load_results(results_dir: Path) -> dict:
    path = results_dir / "benchmark_results.json"
    if not path.exists():
        print(f"Error: {path} not found")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def make_df(data: dict) -> pd.DataFrame:
    rows = []
    for run in data["runs"]:
        q_total = sum(run.get("qualityScore", {}).values())
        q_max = len(run.get("qualityScore", {})) or 1
        req_retained = sum(1 for v in run.get("requirementRetention", {}).values() if v)
        req_total = len(run.get("requirementRetention", {})) or 1

        # Calculate token activity (total tokens moved, weighted by cost)
        # cache_read at 0.1x, cache_create at 1.25x, input at 1x, output at 5x (relative to input)
        token_activity = (
            run["totalInputTokens"]
            + run["totalCacheReadTokens"] * 0.1
            + run["totalCacheCreationTokens"] * 1.25
            + run["totalOutputTokens"] * 5.0  # output is 5x input price for Opus
        )

        rows.append({
            "strategy": run["strategy"],
            "run_id": run["runId"],
            "completed": run["completed"],
            "input_tokens": run["totalInputTokens"],
            "output_tokens": run["totalOutputTokens"],
            "cache_read_tokens": run["totalCacheReadTokens"],
            "cache_create_tokens": run["totalCacheCreationTokens"],
            "cost_usd": run["totalCostUsd"],
            "wall_clock_ms": run["totalWallClockMs"],
            "wall_clock_min": run["totalWallClockMs"] / 60000,
            "turns": run["totalTurnCount"],
            "tool_calls": run["totalToolCalls"],
            "quality_score": q_total,
            "quality_max": q_max,
            "quality_pct": q_total / q_max * 100 if q_max > 0 else 0,
            "requirements_retained": req_retained,
            "requirements_total": req_total,
            "requirement_pct": req_retained / req_total * 100 if req_total > 0 else 0,
            "token_activity": token_activity,
            "cost_per_quality_point": run["totalCostUsd"] / q_total if q_total > 0 else float("inf"),
            # Recovery metrics
            "recovery_tokens": run.get("recoveryTokensBeforeFirstChange", 0),
            "recovery_tool_calls": run.get("recoveryToolCallsBeforeProductive", 0),
            "recovery_wall_ms": run.get("recoveryWallClockMs", 0),
        })
    return pd.DataFrame(rows)


def make_step_df(data: dict) -> pd.DataFrame:
    """Per-step metrics for context growth visualization."""
    rows = []
    for run in data["runs"]:
        cumulative_input = 0
        cumulative_cost = 0
        for step in run.get("steps", []):
            cumulative_input += step["inputTokens"] + step["cacheReadTokens"] + step["cacheCreationTokens"]
            cumulative_cost += step["costUsd"]
            rows.append({
                "strategy": run["strategy"],
                "run_id": run["runId"],
                "step": step["step"],
                "step_name": step["stepName"],
                "input_tokens": step["inputTokens"],
                "output_tokens": step["outputTokens"],
                "cache_read": step["cacheReadTokens"],
                "cache_create": step["cacheCreationTokens"],
                "step_cost": step["costUsd"],
                "cumulative_tokens": cumulative_input,
                "cumulative_cost": cumulative_cost,
                "tool_calls": step["toolCalls"],
                "wall_clock_ms": step["wallClockMs"],
            })
    return pd.DataFrame(rows)


def make_transition_df(data: dict) -> pd.DataFrame:
    rows = []
    for run in data["runs"]:
        for t in run.get("transitions", []):
            if t["type"] == "none":
                continue
            rows.append({
                "strategy": run["strategy"],
                "run_id": run["runId"],
                "type": t["type"],
                "input_tokens": t["inputTokens"],
                "output_tokens": t["outputTokens"],
                "cache_read": t["cacheReadTokens"],
                "cache_create": t["cacheCreationTokens"],
                "cost_usd": t["costUsd"],
                "wall_clock_ms": t["wallClockMs"],
            })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def setup_style():
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update({
        "figure.figsize": (12, 7),
        "figure.dpi": 150,
        "font.size": 11,
        "axes.titlesize": 14,
        "axes.labelsize": 12,
        "legend.fontsize": 10,
        "figure.facecolor": "white",
    })


def save_fig(fig: plt.Figure, graphs_dir: Path, name: str):
    fig.savefig(graphs_dir / f"{name}.png", bbox_inches="tight", dpi=150)
    fig.savefig(graphs_dir / f"{name}.svg", bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {name}.png + .svg")


def graph1_context_over_time(step_df: pd.DataFrame, graphs_dir: Path):
    """Graph 1: Context/token activity over the task sequence."""
    if step_df.empty:
        return
    fig, ax = plt.subplots(figsize=(14, 7))

    for strategy in STRATEGY_ORDER:
        sdf = step_df[step_df["strategy"] == strategy]
        if sdf.empty:
            continue
        # Average across runs
        avg = sdf.groupby("step")["cumulative_tokens"].mean()
        std = sdf.groupby("step")["cumulative_tokens"].std().fillna(0)
        ax.plot(avg.index, avg.values / 1000, label=STRATEGY_LABELS[strategy].replace("\n", " "),
                color=STRATEGY_COLORS[strategy], linewidth=2)
        ax.fill_between(avg.index, (avg - std).values / 1000, (avg + std).values / 1000,
                        alpha=0.15, color=STRATEGY_COLORS[strategy])

    # Mark transition points
    from prompts import TRANSITION_POINTS  # noqa
    # Can't import TS, use hardcoded: [4, 7, 9]
    for tp in [4, 7, 9]:
        ax.axvline(x=tp + 0.5, color="gray", linestyle="--", alpha=0.5, linewidth=1)
        ax.text(tp + 0.5, ax.get_ylim()[1] * 0.95, "transition", rotation=90,
                va="top", ha="right", fontsize=8, color="gray")

    ax.set_xlabel("Task Step")
    ax.set_ylabel("Cumulative Tokens (thousands)")
    ax.set_title("Graph 1: Context / Token Activity Over Task Sequence")
    ax.legend(loc="upper left")
    ax.set_xlim(left=1)
    save_fig(fig, graphs_dir, "01_context_over_time")


def graph2_total_token_usage(df: pd.DataFrame, graphs_dir: Path):
    """Graph 2: Total token/cache usage breakdown by strategy."""
    fig, ax = plt.subplots(figsize=(12, 7))

    strategies = [s for s in STRATEGY_ORDER if s in df["strategy"].unique()]
    x = np.arange(len(strategies))
    width = 0.2

    components = [
        ("input_tokens", "Uncached Input", "#4C72B0"),
        ("cache_read_tokens", "Cache Reads", "#55A868"),
        ("cache_create_tokens", "Cache Creation", "#DD8452"),
        ("output_tokens", "Output", "#C44E52"),
    ]

    for i, (col, label, color) in enumerate(components):
        means = [df[df["strategy"] == s][col].mean() / 1000 for s in strategies]
        stds = [df[df["strategy"] == s][col].std() / 1000 for s in strategies]
        ax.bar(x + i * width, means, width, yerr=stds, label=label, color=color, alpha=0.85)

    ax.set_xlabel("Strategy")
    ax.set_ylabel("Tokens (thousands)")
    ax.set_title("Graph 2: Total Token / Cache Usage by Strategy")
    ax.set_xticks(x + width * 1.5)
    ax.set_xticklabels([STRATEGY_LABELS[s] for s in strategies], fontsize=9)
    ax.legend()
    save_fig(fig, graphs_dir, "02_total_token_usage")


def graph3_transition_overhead(trans_df: pd.DataFrame, graphs_dir: Path):
    """Graph 3: Immediate cost of each transition type."""
    if trans_df.empty:
        print("  Skipping graph 3: no transition data")
        return
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    for ax, metric, ylabel, title_suffix in [
        (ax1, "cost_usd", "Cost (USD)", "Cost"),
        (ax2, "wall_clock_ms", "Time (seconds)", "Wall Clock Time"),
    ]:
        types = trans_df["type"].unique()
        data_by_type = {}
        for t in types:
            vals = trans_df[trans_df["type"] == t][metric]
            if metric == "wall_clock_ms":
                vals = vals / 1000  # to seconds
            data_by_type[t] = vals

        positions = range(len(types))
        bp = ax.boxplot(
            [data_by_type[t] for t in types],
            positions=list(positions),
            widths=0.5,
            patch_artist=True,
        )

        colors = {"compact": "#DD8452", "focused_compact": "#55A868", "handoff": "#C44E52"}
        for patch, t in zip(bp["boxes"], types):
            patch.set_facecolor(colors.get(t, "#999999"))
            patch.set_alpha(0.7)

        ax.set_xticks(list(positions))
        ax.set_xticklabels([t.replace("_", "\n") for t in types])
        ax.set_ylabel(ylabel)
        ax.set_title(f"Transition Overhead: {title_suffix}")

    fig.suptitle("Graph 3: Transition Overhead", fontsize=14)
    fig.tight_layout()
    save_fig(fig, graphs_dir, "03_transition_overhead")


def graph4_requirement_retention(df: pd.DataFrame, graphs_dir: Path):
    """Graph 4: Requirement retention by strategy."""
    fig, ax = plt.subplots(figsize=(10, 6))

    strategies = [s for s in STRATEGY_ORDER if s in df["strategy"].unique()]
    x = np.arange(len(strategies))

    means = [df[df["strategy"] == s]["requirement_pct"].mean() for s in strategies]
    stds = [df[df["strategy"] == s]["requirement_pct"].std() for s in strategies]
    colors = [STRATEGY_COLORS[s] for s in strategies]

    bars = ax.bar(x, means, yerr=stds, color=colors, alpha=0.85, capsize=5)

    ax.set_ylim(0, 110)
    ax.set_ylabel("Requirements Retained (%)")
    ax.set_title("Graph 4: Requirement Retention Across Context Transitions")
    ax.set_xticks(x)
    ax.set_xticklabels([STRATEGY_LABELS[s] for s in strategies], fontsize=9)

    for bar, mean in zip(bars, means):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                f"{mean:.0f}%", ha="center", fontsize=10)

    save_fig(fig, graphs_dir, "04_requirement_retention")


def graph5_noise_resilience(df: pd.DataFrame, graphs_dir: Path):
    """Graph 5: Success rate and quality under historical noise."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    strategies = [s for s in STRATEGY_ORDER if s in df["strategy"].unique()]
    x = np.arange(len(strategies))
    colors = [STRATEGY_COLORS[s] for s in strategies]

    # Completion rate
    completion = [df[df["strategy"] == s]["completed"].mean() * 100 for s in strategies]
    ax1.bar(x, completion, color=colors, alpha=0.85)
    ax1.set_ylim(0, 110)
    ax1.set_ylabel("Completion Rate (%)")
    ax1.set_title("Task Completion Rate")
    ax1.set_xticks(x)
    ax1.set_xticklabels([STRATEGY_LABELS[s] for s in strategies], fontsize=9)

    # Quality score
    quality = [df[df["strategy"] == s]["quality_pct"].mean() for s in strategies]
    quality_std = [df[df["strategy"] == s]["quality_pct"].std() for s in strategies]
    ax2.bar(x, quality, yerr=quality_std, color=colors, alpha=0.85, capsize=5)
    ax2.set_ylim(0, 110)
    ax2.set_ylabel("Quality Score (%)")
    ax2.set_title("Final Implementation Quality")
    ax2.set_xticks(x)
    ax2.set_xticklabels([STRATEGY_LABELS[s] for s in strategies], fontsize=9)

    fig.suptitle("Graph 5: Success Under Historical Context Noise", fontsize=14)
    fig.tight_layout()
    save_fig(fig, graphs_dir, "05_noise_resilience")


def graph6_quality_breakdown(df: pd.DataFrame, data: dict, graphs_dir: Path):
    """Graph 6: Detailed quality score breakdown."""
    # Collect all quality dimensions
    quality_dims = set()
    for run in data["runs"]:
        quality_dims.update(run.get("qualityScore", {}).keys())
    quality_dims = sorted(quality_dims)

    if not quality_dims:
        print("  Skipping graph 6: no quality data")
        return

    fig, ax = plt.subplots(figsize=(14, 7))

    strategies = [s for s in STRATEGY_ORDER if s in df["strategy"].unique()]
    x = np.arange(len(quality_dims))
    width = 0.8 / len(strategies)

    for i, strategy in enumerate(strategies):
        runs = [r for r in data["runs"] if r["strategy"] == strategy]
        means = []
        for dim in quality_dims:
            scores = [r["qualityScore"].get(dim, 0) for r in runs]
            means.append(np.mean(scores) * 100)
        ax.bar(x + i * width, means, width, label=STRATEGY_LABELS[strategy].replace("\n", " "),
               color=STRATEGY_COLORS[strategy], alpha=0.85)

    ax.set_ylim(0, 110)
    ax.set_ylabel("Pass Rate (%)")
    ax.set_title("Graph 6: Final Implementation Quality — Detailed Breakdown")
    ax.set_xticks(x + width * (len(strategies) - 1) / 2)
    ax.set_xticklabels([d.replace("_", "\n") for d in quality_dims], fontsize=9)
    ax.legend(loc="upper right")
    save_fig(fig, graphs_dir, "06_quality_breakdown")


def graph7_cost_per_success(df: pd.DataFrame, graphs_dir: Path):
    """Graph 7: Resource usage per successful solution."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    strategies = [s for s in STRATEGY_ORDER if s in df["strategy"].unique()]
    x = np.arange(len(strategies))
    colors = [STRATEGY_COLORS[s] for s in strategies]

    # Cost per quality point
    cost_per_q = []
    for s in strategies:
        sdf = df[(df["strategy"] == s) & (df["completed"])]
        if sdf.empty or sdf["quality_score"].sum() == 0:
            cost_per_q.append(0)
        else:
            cost_per_q.append(sdf["cost_usd"].sum() / sdf["quality_score"].sum())

    ax1.bar(x, cost_per_q, color=colors, alpha=0.85)
    ax1.set_ylabel("Cost per Quality Point (USD)")
    ax1.set_title("Cost Efficiency")
    ax1.set_xticks(x)
    ax1.set_xticklabels([STRATEGY_LABELS[s] for s in strategies], fontsize=9)

    # Token activity per quality point
    token_per_q = []
    for s in strategies:
        sdf = df[(df["strategy"] == s) & (df["completed"])]
        if sdf.empty or sdf["quality_score"].sum() == 0:
            token_per_q.append(0)
        else:
            token_per_q.append(sdf["token_activity"].sum() / sdf["quality_score"].sum() / 1000)

    ax2.bar(x, token_per_q, color=colors, alpha=0.85)
    ax2.set_ylabel("Token Activity per Quality Point (K)")
    ax2.set_title("Token Efficiency")
    ax2.set_xticks(x)
    ax2.set_xticklabels([STRATEGY_LABELS[s] for s in strategies], fontsize=9)

    fig.suptitle("Graph 7: Resource Usage per Successful Solution", fontsize=14)
    fig.tight_layout()
    save_fig(fig, graphs_dir, "07_cost_per_success")


def graph8_quality_vs_cost(df: pd.DataFrame, graphs_dir: Path):
    """Graph 8: Quality vs resource consumption scatter."""
    fig, ax = plt.subplots(figsize=(10, 8))

    for strategy in STRATEGY_ORDER:
        sdf = df[df["strategy"] == strategy]
        if sdf.empty:
            continue
        ax.scatter(
            sdf["cost_usd"], sdf["quality_pct"],
            label=STRATEGY_LABELS[strategy].replace("\n", " "),
            color=STRATEGY_COLORS[strategy],
            s=100, alpha=0.7, edgecolors="black", linewidth=0.5,
        )

    ax.set_xlabel("Total Cost (USD)")
    ax.set_ylabel("Quality Score (%)")
    ax.set_title("Graph 8: Quality vs Resource Consumption")
    ax.legend(loc="lower right")

    # Add "ideal direction" arrow
    ax.annotate("", xy=(ax.get_xlim()[0] + 0.1, 100), xytext=(ax.get_xlim()[1] - 0.1, 0),
                arrowprops=dict(arrowstyle="->", color="green", lw=2, alpha=0.3))
    ax.text(0.05, 0.95, "← Better", transform=ax.transAxes, fontsize=10, color="green", alpha=0.5)

    save_fig(fig, graphs_dir, "08_quality_vs_cost")


def graph9_breakeven(step_df: pd.DataFrame, df: pd.DataFrame, graphs_dir: Path):
    """Graph 9: Cumulative cost comparison — break-even analysis."""
    if step_df.empty:
        print("  Skipping graph 9: no step data")
        return

    fig, ax = plt.subplots(figsize=(14, 7))

    for strategy in STRATEGY_ORDER:
        sdf = step_df[step_df["strategy"] == strategy]
        if sdf.empty:
            continue
        avg_cost = sdf.groupby("step")["cumulative_cost"].mean()
        ax.plot(avg_cost.index, avg_cost.values, label=STRATEGY_LABELS[strategy].replace("\n", " "),
                color=STRATEGY_COLORS[strategy], linewidth=2, marker="o", markersize=4)

    # Mark transition points
    for tp in [4, 7, 9]:
        ax.axvline(x=tp + 0.5, color="gray", linestyle="--", alpha=0.4, linewidth=1)

    ax.set_xlabel("Task Step")
    ax.set_ylabel("Cumulative Cost (USD)")
    ax.set_title("Graph 9: Break-Even — Cumulative Cost Over Task Sequence")
    ax.legend(loc="upper left")
    save_fig(fig, graphs_dir, "09_breakeven")


def generate_summary_json(df: pd.DataFrame, data: dict, results_dir: Path):
    """Generate summary.json with aggregate stats."""
    summary = {}
    for strategy in STRATEGY_ORDER:
        sdf = df[df["strategy"] == strategy]
        if sdf.empty:
            continue
        summary[strategy] = {
            "runs": len(sdf),
            "completed": int(sdf["completed"].sum()),
            "mean_cost_usd": float(sdf["cost_usd"].mean()),
            "std_cost_usd": float(sdf["cost_usd"].std()),
            "mean_input_tokens": float(sdf["input_tokens"].mean()),
            "mean_output_tokens": float(sdf["output_tokens"].mean()),
            "mean_cache_read_tokens": float(sdf["cache_read_tokens"].mean()),
            "mean_cache_create_tokens": float(sdf["cache_create_tokens"].mean()),
            "mean_quality_pct": float(sdf["quality_pct"].mean()),
            "std_quality_pct": float(sdf["quality_pct"].std()),
            "mean_requirement_pct": float(sdf["requirement_pct"].mean()),
            "mean_wall_clock_min": float(sdf["wall_clock_min"].mean()),
            "mean_turns": float(sdf["turns"].mean()),
            "mean_tool_calls": float(sdf["tool_calls"].mean()),
            "mean_cost_per_quality_point": float(sdf["cost_per_quality_point"].mean()),
            "mean_token_activity": float(sdf["token_activity"].mean()),
        }

    with open(results_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Saved summary.json")


def main():
    results_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "results"
    graphs_dir = Path(__file__).parent.parent / "graphs"
    graphs_dir.mkdir(parents=True, exist_ok=True)

    print("Loading results...")
    data = load_results(results_dir)
    df = make_df(data)
    step_df = make_step_df(data)
    trans_df = make_transition_df(data)

    print(f"Loaded {len(df)} runs across {df['strategy'].nunique()} strategies")
    print(f"Strategies: {', '.join(df['strategy'].unique())}")

    setup_style()

    print("\nGenerating graphs...")
    graph1_context_over_time(step_df, graphs_dir)
    graph2_total_token_usage(df, graphs_dir)
    graph3_transition_overhead(trans_df, graphs_dir)
    graph4_requirement_retention(df, graphs_dir)
    graph5_noise_resilience(df, graphs_dir)
    graph6_quality_breakdown(df, data, graphs_dir)
    graph7_cost_per_success(df, graphs_dir)
    graph8_quality_vs_cost(df, graphs_dir)
    graph9_breakeven(step_df, df, graphs_dir)

    print("\nGenerating summary...")
    generate_summary_json(df, data, results_dir)

    print("\nDone! Graphs saved to", graphs_dir)
    return df, data


if __name__ == "__main__":
    main()
