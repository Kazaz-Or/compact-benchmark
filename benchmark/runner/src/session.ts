// Session management — wraps Claude Agent SDK for benchmark usage

import { query } from "@anthropic-ai/claude-agent-sdk";
import type { StepMetrics, TransitionMetrics } from "./types.ts";

interface SessionOptions {
  projectDir: string;
  model: string;
  effort: string;
  sessionId?: string;
  appendSystemPrompt?: string;
}

interface QueryResult {
  metrics: StepMetrics;
  sessionId: string;
  output: string;
  messages: any[];
}

let stepCounter = 0;

export async function runStep(
  stepName: string,
  prompt: string,
  opts: SessionOptions,
  resumeSessionId?: string,
): Promise<QueryResult> {
  stepCounter++;
  const startTime = Date.now();
  let totalInput = 0;
  let totalOutput = 0;
  let totalCacheRead = 0;
  let totalCacheCreate = 0;
  let totalCost = 0;
  let toolCalls = 0;
  let turnCount = 0;
  let sessionId = resumeSessionId || "";
  let lastOutput = "";
  const allMessages: any[] = [];

  const queryOpts: Record<string, any> = {
    model: opts.model,
    effort: opts.effort,
    permissionMode: "bypassPermissions" as const,
    cwd: opts.projectDir,
  };

  if (resumeSessionId) {
    queryOpts.resume = resumeSessionId;
  }

  if (opts.appendSystemPrompt) {
    queryOpts.appendSystemPrompt = opts.appendSystemPrompt;
  }

  try {
    for await (const message of query({ prompt, options: queryOpts })) {
      allMessages.push(message);

      if (message.type === "assistant") {
        turnCount++;
        if (message.message?.usage) {
          const u = message.message.usage;
          // Don't double-count: per-step input is deduplicated via message ID
          totalInput += u.input_tokens || 0;
          totalCacheRead += u.cache_read_input_tokens || 0;
          totalCacheCreate += u.cache_creation_input_tokens || 0;
        }
        // Count tool uses
        if (message.message?.content) {
          for (const block of message.message.content) {
            if (block.type === "tool_use") toolCalls++;
            if (block.type === "text") lastOutput = block.text;
          }
        }
      }

      if (message.type === "result") {
        sessionId = message.session_id || sessionId;
        totalCost = message.total_cost_usd || 0;
        if (message.usage) {
          totalOutput = message.usage.output_tokens || 0;
        }
        if (message.subtype === "error_max_turns" || message.subtype === "error_during_execution") {
          console.warn(`  Step "${stepName}" ended with: ${message.subtype}`);
        }
      }
    }
  } catch (err: any) {
    console.error(`  Step "${stepName}" error: ${err.message}`);
  }

  const wallClockMs = Date.now() - startTime;

  return {
    metrics: {
      step: stepCounter,
      stepName,
      inputTokens: totalInput,
      outputTokens: totalOutput,
      cacheReadTokens: totalCacheRead,
      cacheCreationTokens: totalCacheCreate,
      costUsd: totalCost,
      toolCalls,
      wallClockMs,
      turnCount,
    },
    sessionId,
    output: lastOutput,
    messages: allMessages,
  };
}

export async function runCompact(
  projectDir: string,
  model: string,
  effort: string,
  sessionId: string,
  instruction?: string,
): Promise<{ metrics: TransitionMetrics; sessionId: string }> {
  const startTime = Date.now();
  let totalInput = 0;
  let totalOutput = 0;
  let totalCacheRead = 0;
  let totalCacheCreate = 0;
  let totalCost = 0;

  const compactPrompt = instruction
    ? `/compact ${instruction}`
    : "/compact";

  let preTokens = 0;
  let postTokens = 0;

  try {
    for await (const message of query({
      prompt: compactPrompt,
      options: {
        model,
        effort,
        permissionMode: "bypassPermissions" as const,
        cwd: projectDir,
        resume: sessionId,
      },
    })) {
      if (message.type === "assistant" && message.message?.usage) {
        const u = message.message.usage;
        totalInput += u.input_tokens || 0;
        totalCacheRead += u.cache_read_input_tokens || 0;
        totalCacheCreate += u.cache_creation_input_tokens || 0;
      }
      // Capture compact boundary metadata if available
      if ((message as any).type === "system" && (message as any).subtype === "compact_boundary") {
        const meta = (message as any).compact_metadata || (message as any).data?.compact_metadata;
        if (meta) {
          preTokens = meta.pre_tokens || 0;
        }
      }
      if (message.type === "result") {
        sessionId = message.session_id || sessionId;
        totalCost = message.total_cost_usd || 0;
        if (message.usage) {
          totalOutput = message.usage.output_tokens || 0;
        }
      }
    }
  } catch (err: any) {
    console.error(`  Compact error: ${err.message}`);
  }

  return {
    metrics: {
      type: instruction ? "focused_compact" : "compact",
      inputTokens: totalInput,
      outputTokens: totalOutput,
      cacheReadTokens: totalCacheRead,
      cacheCreationTokens: totalCacheCreate,
      costUsd: totalCost,
      wallClockMs: Date.now() - startTime,
      preTransitionTokens: preTokens,
      postTransitionTokens: postTokens,
    },
    sessionId,
  };
}

export async function runHandoff(
  projectDir: string,
  model: string,
  effort: string,
  sessionId: string,
  handoffPrompt: string,
): Promise<{
  handoffMetrics: TransitionMetrics;
  oldSessionId: string;
}> {
  const startTime = Date.now();
  let totalInput = 0;
  let totalOutput = 0;
  let totalCacheRead = 0;
  let totalCacheCreate = 0;
  let totalCost = 0;

  try {
    for await (const message of query({
      prompt: handoffPrompt,
      options: {
        model,
        effort,
        permissionMode: "bypassPermissions" as const,
        cwd: projectDir,
        resume: sessionId,
      },
    })) {
      if (message.type === "assistant" && message.message?.usage) {
        const u = message.message.usage;
        totalInput += u.input_tokens || 0;
        totalCacheRead += u.cache_read_input_tokens || 0;
        totalCacheCreate += u.cache_creation_input_tokens || 0;
      }
      if (message.type === "result") {
        totalCost = message.total_cost_usd || 0;
        if (message.usage) {
          totalOutput = message.usage.output_tokens || 0;
        }
      }
    }
  } catch (err: any) {
    console.error(`  Handoff creation error: ${err.message}`);
  }

  return {
    handoffMetrics: {
      type: "handoff",
      inputTokens: totalInput,
      outputTokens: totalOutput,
      cacheReadTokens: totalCacheRead,
      cacheCreationTokens: totalCacheCreate,
      costUsd: totalCost,
      wallClockMs: Date.now() - startTime,
      preTransitionTokens: 0,
      postTransitionTokens: 0,
    },
    oldSessionId: sessionId,
  };
}
