# Task Generation Stage

The third stage of the pipeline. After the verifier (stage 1) and smoke loop (stage 2) are passing, point a coding agent at [`CLAUDE.md`](./CLAUDE.md) to generate finalized tasks under `task_generator/tasks/`.

There is no wrapper script — the agent drives all four stages (propose → evaluate → match to verifier → synthesize env) directly.

To extend coverage:
- [`TASK_EXTENSION.md`](./TASK_EXTENSION.md) — add tasks for uncovered workflows in an existing app.
- [`ENDPOINT_EXTENSION.md`](./ENDPOINT_EXTENSION.md) — add a new verifier endpoint when a task has no matching check.
