// Task prompts for the benchmark.
// Every strategy gets the EXACT same prompts.

export const INITIAL_CONSTRAINTS = `
IMPORTANT CONSTRAINTS (must be preserved throughout the entire session):
- Public API signatures in src/models/schemas.py cannot change.
- No new runtime dependencies may be added.
- Existing error response schemas must remain compatible.
- Repository interfaces (method signatures) in *_repo.py cannot change.
- All existing tests must continue to pass.
`;

export const TASK_STEPS = [
  {
    name: "architecture_exploration",
    prompt: `Explore this TaskFlow API project. Understand the architecture:
- How the layers connect (routes → services → repositories → database)
- What the data models look like
- Where tests are located
- What the CLAUDE.md says about constraints

Read all the source files in src/ and the test files.
Give me a brief architecture summary.`,
  },
  {
    name: "understand_data_flow",
    prompt: `Trace the full data flow for creating a task:
1. HTTP request hits the route
2. Route calls service
3. Service calls repository
4. Repository writes to SQLite

Read each file involved and explain the exact flow, including error handling.
Also trace the flow for listing tasks with filters (status, assignee).`,
  },
  {
    name: "diagnose_bug_a",
    prompt: `There's a bug: when listing tasks with a filter (e.g., assignee="alice"),
the "total" count in the response doesn't match the filtered results.
It returns the total count of ALL tasks in the project instead of the filtered count.

Find the bug. Tell me exactly which file and line causes it.
Do NOT fix it yet.`,
  },
  {
    name: "fix_bug_a",
    prompt: `Fix the filtered count bug you just found in the task repository.
The total count must match the number of tasks returned when filters are applied.

Remember: repository method signatures cannot change.
Make the fix and run the tests to verify.`,
  },
  {
    name: "add_tests_for_fix",
    prompt: `Add test cases to tests/test_basic.py that specifically verify:
1. Filtered list total matches actual filtered count
2. Unfiltered list total still works correctly
3. Multiple filters applied together

Run the tests to make sure they pass.`,
  },
  {
    name: "implement_feature",
    prompt: `Implement a batch status update endpoint:

PATCH /api/v1/projects/{project_id}/tasks/batch

Request body:
{
  "task_ids": [1, 2, 3],
  "status": "in_progress"
}

Response: list of updated tasks (200) or multi-status (207) if some fail.

Requirements:
- Validate status transitions for each task individually
- Tasks not in the project should be rejected
- If some updates fail, still apply the successful ones
- Return clear error info for each failed task
- No new runtime dependencies
- Public API schemas must not change (you may add new schemas)

Add tests for this feature.`,
  },
  {
    // This step creates "noise" — investigation of a red herring
    name: "investigate_integration_failure",
    prompt: `I'm seeing an issue where the search endpoint sometimes returns wrong results.
Try searching for tasks with various queries. Test edge cases:
- Empty results
- Special characters in search
- Very long queries
- Queries with SQL-like syntax

Run the search tests and investigate any issues you find.
Report what you discover about the search implementation.`,
  },
  {
    name: "fix_search_security",
    prompt: `The search endpoint in task_repo.py has a SQL injection vulnerability.
The search query is interpolated directly into the SQL string using f-string formatting.

Fix this to use parameterized queries instead.
Do NOT change the repository method signature.
Add a test that verifies the fix handles special characters safely.`,
  },
  {
    name: "refactor_service",
    prompt: `The task update in task_repo.py has a bug: it doesn't update the updated_at timestamp.

Fix this: when any field is updated via the update method, updated_at should be set to datetime('now').

Remember: repository method signatures cannot change.
Run all tests after the fix.`,
  },
  {
    // This is where requirement retention gets tested.
    // The easiest solution would be to change the API schema or add a dependency,
    // which violates the early constraints.
    name: "new_requirement",
    prompt: `New requirement: Add a task priority summary to the project stats endpoint.

The ProjectStats response should additionally include:
- "urgent_tasks": count of tasks with priority >= 2 that are not done
- "unassigned_count": count of tasks with no assignee

Important: these fields must be added to the existing ProjectStats schema.
All other fields must remain unchanged.
No new dependencies. Existing tests must still pass.`,
  },
  {
    name: "adapt_implementation",
    prompt: `Update the task service's get_project_stats function to populate the new
urgent_tasks and unassigned_count fields.

Run the full test suite to verify nothing is broken.
Also add a test that verifies the new stats fields.`,
  },
  {
    name: "final_verification",
    prompt: `Run the full test suite one final time: python -m pytest tests/ -v

Also run: python -m ruff check src/

Fix any issues found. Make sure everything passes cleanly.`,
  },
];

// Points where context management strategies diverge.
// After these step indices, we apply the strategy.
export const TRANSITION_POINTS = [4, 7, 9]; // After add_tests, fix_search, refactor

export const FOCUSED_COMPACT_INSTRUCTION = `Preserve the original objective, hard constraints (API stability, no new deps, repo interface stability), architectural decisions, current implementation state, all modified files and what was changed, unresolved failures, important discoveries (the bugs found and how they were fixed), rejected approaches that should not be retried, and concrete next steps.

Discard resolved failures, obsolete logs, superseded patches, verbose tool output, repeated explanations, and irrelevant exploration.`;

export const HANDOFF_PROMPT = `Create a structured HANDOFF.md file in the project root that captures the current state for a fresh Claude session to continue this work.

Include:
1. Original objective and ALL constraints (API stability, no new deps, repo interfaces stable, existing tests must pass)
2. Architecture overview (brief)
3. What has been done so far (bugs fixed, features added, files modified)
4. Current state of the codebase (what works, what doesn't)
5. Specific next steps from the task list
6. Any rejected approaches or known pitfalls

The handoff must be self-contained — a fresh session reading only CLAUDE.md, HANDOFF.md, git status, and git diff should be able to continue without re-exploring the entire codebase.

Write the file now.`;

export const FRESH_SESSION_BOOTSTRAP = `Read CLAUDE.md and HANDOFF.md first.
Then check git status and git diff to understand what has changed.
Read any source files mentioned in the handoff as modified.
Then continue with the next task.`;
