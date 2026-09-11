// Benchmark types

export type Strategy = "control" | "plain_compact" | "focused_compact" | "handoff_fresh";

export interface RunConfig {
  strategy: Strategy;
  runId: number;
  projectDir: string;
  model: string;
  effort: string;
  resultsDir: string;
}

export interface StepMetrics {
  step: number;
  stepName: string;
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheCreationTokens: number;
  costUsd: number;
  toolCalls: number;
  wallClockMs: number;
  turnCount: number;
}

export interface TransitionMetrics {
  type: "compact" | "focused_compact" | "handoff" | "none";
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheCreationTokens: number;
  costUsd: number;
  wallClockMs: number;
  preTransitionTokens: number;
  postTransitionTokens: number;
}

export interface RunResult {
  strategy: Strategy;
  runId: number;
  model: string;
  steps: StepMetrics[];
  transitions: TransitionMetrics[];
  totalInputTokens: number;
  totalOutputTokens: number;
  totalCacheReadTokens: number;
  totalCacheCreationTokens: number;
  totalCostUsd: number;
  totalWallClockMs: number;
  totalTurnCount: number;
  totalToolCalls: number;
  qualityScore: Record<string, number>;
  requirementRetention: Record<string, boolean>;
  completed: boolean;
  error?: string;
  // Fresh-session recovery metrics (handoff_fresh only)
  recoveryTokensBeforeFirstChange?: number;
  recoveryFilesReread?: number;
  recoveryToolCallsBeforeProductive?: number;
  recoveryWallClockMs?: number;
}

export interface BenchmarkResult {
  timestamp: string;
  claudeCodeVersion: string;
  model: string;
  effort: string;
  repetitions: number;
  strategies: Strategy[];
  runs: RunResult[];
  hypotheses: Record<string, string>;
}
