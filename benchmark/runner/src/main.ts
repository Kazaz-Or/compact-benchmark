#!/usr/bin/env node
// Main benchmark orchestrator
// Usage: node --experimental-strip-types src/main.ts [--reps N] [--strategies a,b,c,d]

import { execSync } from "child_process";
import { existsSync, mkdirSync, writeFileSync, readFileSync, cpSync, rmSync } from "fs";
import { join, resolve } from "path";
import { runStep, runCompact, runHandoff } from "./session.ts";
import {
  TASK_STEPS,
  TRANSITION_POINTS,
  INITIAL_CONSTRAINTS,
  FOCUSED_COMPACT_INSTRUCTION,
  HANDOFF_PROMPT,
  FRESH_SESSION_BOOTSTRAP,
} from "./prompts.ts";
import type { Strategy, RunResult, BenchmarkResult, StepMetrics, TransitionMetrics } from "./types.ts";

// --- Config ---
const MODEL = "claude-opus-4-6";
const EFFORT = "high";
const ALL_STRATEGIES: Strategy[] = ["control", "plain_compact", "focused_compact", "handoff_fresh"];

function parseArgs() {
  const args = process.argv.slice(2);
  let reps = 5;
  let strategies = [...ALL_STRATEGIES];

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--reps" && args[i + 1]) {
      reps = parseInt(args[i + 1], 10);
      i++;
    }
    if (args[i] === "--strategies" && args[i + 1]) {
      strategies = args[i + 1].split(",") as Strategy[];
      i++;
    }
  }

  return { reps, strategies };
}

// import.meta.dirname = runner/src/ when running src/main.ts
const THIS_DIR = import.meta.dirname || resolve(".");
const RUNNER_DIR = resolve(join(THIS_DIR, ".."));     // runner/
const BENCHMARK_DIR = resolve(join(RUNNER_DIR, "..")); // benchmark/
const PROJECT_ROOT = resolve(join(BENCHMARK_DIR, "..")); // compact-test/
const SEED_PROJECT = join(BENCHMARK_DIR, "seed_project");
const RESULTS_DIR = join(PROJECT_ROOT, "results");
const RAW_DIR = join(RESULTS_DIR, "raw");

function ensureDirs() {
  mkdirSync(RAW_DIR, { recursive: true });
}

function createWorkCopy(strategy: Strategy, runId: number): string {
  const workDir = join(PROJECT_ROOT, "work", `${strategy}_run${runId}`);
  if (existsSync(workDir)) {
    rmSync(workDir, { recursive: true, force: true });
  }
  cpSync(SEED_PROJECT, workDir, { recursive: true });

  // Init git repo for diff tracking
  execSync("git init && git add -A && git commit -m 'initial'", {
    cwd: workDir,
    stdio: "pipe",
  });

  return workDir;
}

function shuffleArray<T>(arr: T[]): T[] {
  const shuffled = [...arr];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled;
}

async function runSingleBenchmark(strategy: Strategy, runId: number): Promise<RunResult> {
  console.log(`\n=== ${strategy} run ${runId} ===`);
  const projectDir = createWorkCopy(strategy, runId);
  const startTime = Date.now();

  const result: RunResult = {
    strategy,
    runId,
    model: MODEL,
    steps: [],
    transitions: [],
    totalInputTokens: 0,
    totalOutputTokens: 0,
    totalCacheReadTokens: 0,
    totalCacheCreationTokens: 0,
    totalCostUsd: 0,
    totalWallClockMs: 0,
    totalTurnCount: 0,
    totalToolCalls: 0,
    qualityScore: {},
    requirementRetention: {},
    completed: false,
  };

  let sessionId = "";
  let isFirstStepAfterHandoff = false;
  let handoffBootstrapTokens = 0;

  try {
    for (let i = 0; i < TASK_STEPS.length; i++) {
      const step = TASK_STEPS[i];
      console.log(`  Step ${i}: ${step.name}`);

      // Prepend constraints to first step
      const prompt = i === 0
        ? `${INITIAL_CONSTRAINTS}\n\n${step.prompt}`
        : step.prompt;

      // For handoff_fresh after transition: start fresh session
      const resumeId = (strategy === "handoff_fresh" && isFirstStepAfterHandoff)
        ? undefined  // Fresh session, no resume
        : sessionId || undefined;

      // Bootstrap prompt for fresh session
      const fullPrompt = (strategy === "handoff_fresh" && isFirstStepAfterHandoff)
        ? `${FRESH_SESSION_BOOTSTRAP}\n\n${prompt}`
        : prompt;

      const stepResult = await runStep(
        step.name,
        fullPrompt,
        { projectDir, model: MODEL, effort: EFFORT },
        resumeId,
      );

      result.steps.push(stepResult.metrics);
      sessionId = stepResult.sessionId;

      // Track recovery cost for fresh sessions
      if (isFirstStepAfterHandoff) {
        result.recoveryTokensBeforeFirstChange = stepResult.metrics.inputTokens + stepResult.metrics.outputTokens;
        result.recoveryToolCallsBeforeProductive = stepResult.metrics.toolCalls;
        result.recoveryWallClockMs = stepResult.metrics.wallClockMs;
        isFirstStepAfterHandoff = false;
      }

      // Apply context management at transition points
      if (TRANSITION_POINTS.includes(i)) {
        console.log(`  --- Transition point after step ${i} ---`);

        if (strategy === "plain_compact") {
          const compactResult = await runCompact(projectDir, MODEL, EFFORT, sessionId);
          result.transitions.push(compactResult.metrics);
          sessionId = compactResult.sessionId;
          console.log(`  Compacted. Cost: $${compactResult.metrics.costUsd.toFixed(4)}`);
        }

        if (strategy === "focused_compact") {
          const compactResult = await runCompact(
            projectDir, MODEL, EFFORT, sessionId, FOCUSED_COMPACT_INSTRUCTION,
          );
          result.transitions.push(compactResult.metrics);
          sessionId = compactResult.sessionId;
          console.log(`  Focused compact. Cost: $${compactResult.metrics.costUsd.toFixed(4)}`);
        }

        if (strategy === "handoff_fresh") {
          const handoffResult = await runHandoff(
            projectDir, MODEL, EFFORT, sessionId, HANDOFF_PROMPT,
          );
          result.transitions.push(handoffResult.handoffMetrics);
          sessionId = ""; // Will start fresh
          isFirstStepAfterHandoff = true;
          console.log(`  Handoff created. Cost: $${handoffResult.handoffMetrics.costUsd.toFixed(4)}`);
        }

        if (strategy === "control") {
          result.transitions.push({
            type: "none",
            inputTokens: 0,
            outputTokens: 0,
            cacheReadTokens: 0,
            cacheCreationTokens: 0,
            costUsd: 0,
            wallClockMs: 0,
            preTransitionTokens: 0,
            postTransitionTokens: 0,
          });
        }
      }
    }

    result.completed = true;
  } catch (err: any) {
    result.error = err.message;
    console.error(`  Run failed: ${err.message}`);
  }

  // Aggregate totals
  for (const step of result.steps) {
    result.totalInputTokens += step.inputTokens;
    result.totalOutputTokens += step.outputTokens;
    result.totalCacheReadTokens += step.cacheReadTokens;
    result.totalCacheCreationTokens += step.cacheCreationTokens;
    result.totalCostUsd += step.costUsd;
    result.totalWallClockMs += step.wallClockMs;
    result.totalTurnCount += step.turnCount;
    result.totalToolCalls += step.toolCalls;
  }
  for (const t of result.transitions) {
    result.totalInputTokens += t.inputTokens;
    result.totalOutputTokens += t.outputTokens;
    result.totalCacheReadTokens += t.cacheReadTokens;
    result.totalCacheCreationTokens += t.cacheCreationTokens;
    result.totalCostUsd += t.costUsd;
    result.totalWallClockMs += t.wallClockMs;
  }

  // Run hidden tests for quality evaluation
  try {
    console.log(`  Running hidden tests...`);
    const hiddenTestPath = join(BENCHMARK_DIR, "hidden_tests.py");
    const evalOutput = execSync(
      `python3 ${hiddenTestPath} ${projectDir}`,
      { timeout: 120000, encoding: "utf-8", cwd: projectDir },
    );
    const evalResult = JSON.parse(evalOutput);
    result.qualityScore = evalResult.scores || {};

    // Check requirement retention specifically
    result.requirementRetention = {
      api_compat: evalResult.scores?.api_compat === 1,
      no_new_deps: evalResult.scores?.no_new_deps === 1,
      repo_interface: evalResult.scores?.repo_interface === 1,
      no_regressions: evalResult.scores?.no_regressions === 1,
    };
  } catch (err: any) {
    console.error(`  Hidden test evaluation failed: ${err.message}`);
    result.qualityScore = {};
  }

  result.totalWallClockMs = Date.now() - startTime;

  // Save individual run result
  const runFile = join(RAW_DIR, `${strategy}_run${runId}.json`);
  writeFileSync(runFile, JSON.stringify(result, null, 2));
  console.log(`  Saved to ${runFile}`);
  console.log(`  Total cost: $${result.totalCostUsd.toFixed(4)}, quality: ${JSON.stringify(result.qualityScore)}`);

  return result;
}

async function main() {
  const { reps, strategies } = parseArgs();
  ensureDirs();

  console.log("=== Compact Benchmark ===");
  console.log(`Model: ${MODEL}`);
  console.log(`Effort: ${EFFORT}`);
  console.log(`Strategies: ${strategies.join(", ")}`);
  console.log(`Repetitions: ${reps}`);
  console.log(`Claude Code: ${execSync("claude --version", { encoding: "utf-8" }).trim()}`);

  // Pre-register hypotheses
  const hypotheses = {
    control: "Cheapest for coherent sessions, may degrade with historical noise accumulation. Cache hits keep per-turn cost low, but context grows unbounded.",
    plain_compact: "Saves downstream context but pays a transition cost (cache rebuild). May lose useful implementation details. Net benefit depends on how many turns remain after compaction.",
    focused_compact: "Better state preservation than plain compact due to guided summarization. Similar transition cost. May reduce requirement-forgetting failures.",
    handoff_fresh: "Cleanest context at task boundaries, but pays rediscovery cost (re-reading files, re-understanding state). Best when task boundaries are genuine semantic breaks.",
  };

  // Build run schedule (randomized)
  interface ScheduledRun { strategy: Strategy; runId: number }
  const schedule: ScheduledRun[] = [];
  for (const strategy of strategies) {
    for (let r = 1; r <= reps; r++) {
      schedule.push({ strategy, runId: r });
    }
  }
  const randomized = shuffleArray(schedule);

  console.log(`\nSchedule: ${randomized.length} total runs`);
  console.log(randomized.map(r => `${r.strategy}#${r.runId}`).join(", "));

  const allResults: RunResult[] = [];

  for (let i = 0; i < randomized.length; i++) {
    const { strategy, runId } = randomized[i];
    console.log(`\n[${i + 1}/${randomized.length}] ${strategy} run ${runId}`);
    const result = await runSingleBenchmark(strategy, runId);
    allResults.push(result);

    // Save intermediate full results
    const intermediate: BenchmarkResult = {
      timestamp: new Date().toISOString(),
      claudeCodeVersion: execSync("claude --version", { encoding: "utf-8" }).trim(),
      model: MODEL,
      effort: EFFORT,
      repetitions: reps,
      strategies,
      runs: allResults,
      hypotheses,
    };
    writeFileSync(
      join(RESULTS_DIR, "benchmark_results.json"),
      JSON.stringify(intermediate, null, 2),
    );
  }

  // Final results
  const finalResult: BenchmarkResult = {
    timestamp: new Date().toISOString(),
    claudeCodeVersion: execSync("claude --version", { encoding: "utf-8" }).trim(),
    model: MODEL,
    effort: EFFORT,
    repetitions: reps,
    strategies,
    runs: allResults,
    hypotheses,
  };

  writeFileSync(
    join(RESULTS_DIR, "benchmark_results.json"),
    JSON.stringify(finalResult, null, 2),
  );

  // Generate summary CSV
  const csvHeader = "strategy,run,completed,total_input,total_output,cache_read,cache_create,cost_usd,wall_clock_ms,turns,tool_calls,quality_total,quality_max";
  const csvRows = allResults.map(r => {
    const qTotal = Object.values(r.qualityScore).reduce((a, b) => a + b, 0);
    const qMax = Object.keys(r.qualityScore).length;
    return `${r.strategy},${r.runId},${r.completed},${r.totalInputTokens},${r.totalOutputTokens},${r.totalCacheReadTokens},${r.totalCacheCreationTokens},${r.totalCostUsd.toFixed(4)},${r.totalWallClockMs},${r.totalTurnCount},${r.totalToolCalls},${qTotal},${qMax}`;
  });
  writeFileSync(join(RESULTS_DIR, "summary.csv"), [csvHeader, ...csvRows].join("\n"));

  console.log("\n=== Benchmark Complete ===");
  console.log(`Results saved to ${RESULTS_DIR}/`);
  console.log(`Runs completed: ${allResults.filter(r => r.completed).length}/${allResults.length}`);
}

main().catch(err => {
  console.error("Fatal:", err);
  process.exit(1);
});
