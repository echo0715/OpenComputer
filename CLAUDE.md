# Root Pipeline Guide

This repository has a strict execution order for app work:

1. Generate or update the app verifier.
2. Run the verifier smoke tests to confirm endpoints work end-to-end.
3. Generate finalized tasks for the app.
4. (Optional) Run the repair loop on 3 tasks per app.

Do not skip ahead through stages 1–3. Verifier quality determines task quality, and task quality determines whether repair runs are meaningful. Stage 4 is optional and only runs when explicitly requested.

## Stage 1: Verifier Generation

Start by reading [verifiers/CLAUDE.md](/Users/Mike/Desktop/syn_env/verifiers/CLAUDE.md).

For each target app:

1. Read `verifiers/CLAUDE.md` completely.
2. Read the existing app docs in `verifiers/<app>/README.md` and the current verifier at `verifiers/<app>/<app>.py` if they already exist.
3. Build or extend the verifier module under `verifiers/<app>/`:
   - `<app>.py`
   - `README.md`
   - `Test.md`
   - `test_<app>.py`
4. Follow the verifier workflow in `verifiers/CLAUDE.md` exactly:
   - design comprehensive endpoints across all inspectable app surfaces
   - document every endpoint in the app README
   - write `Test.md` before test code
   - run `python verifiers/<app>/test_<app>.py`
   - debug and fix until tests pass before moving on

Rule: task generation must not begin for an app until its verifier is implemented and passing.

## Stage 2: Verifier Smoke Tests

After verifier unit tests pass (`python verifiers/<app>/test_<app>.py`), run the
smoke-test pipeline to confirm verifier endpoints work with real agent trajectories
in a live sandbox:

```bash
python smoke/smoke_loop.py --app <app>
```

This generates small, easy tasks (one per verifier endpoint group) and runs each in
a fresh sandbox. Read `smoke/README.md` for full documentation.

- `--generate-only`: inspect the generated tasks before running them
- `--run-only`: re-run existing tasks after editing the verifier
- `--max-tasks N`: cap the number of generated tasks

The run produces `smoke/runs/<app>_<ts>/REPORT.md`. Review it before
proceeding. If endpoints fail, fix the verifier and re-run `--run-only`.

Rule: real task generation should not begin until the smoke-test report shows all
endpoint groups passing (or the failures are understood and accepted).

## Stage 3: Task Generation

After the verifier is ready, read [task_generator/CLAUDE.md](/Users/Mike/Desktop/syn_env/task_generator/CLAUDE.md).

For each target app:

1. Read `task_generator/CLAUDE.md`.
2. Read `task_generator/LESSONS.md`.
3. Follow the full task pipeline:
   - Stage 1: generate proposals in `task_generator/tasks/proposals_<app>.json` (do NOT consult verifiers yet — focus on diversity and difficulty)
   - Stage 2: evaluate proposals on complexity + data generatability into `task_generator/tasks/evaluated_<app>.json`
   - Stage 3: match accepted tasks to verifiers (direct match → adapt task → extend verifier → discard), then produce final `task.json` files under `task_generator/tasks/<task_id>/task.json`
   - Stage 4: synthesize env files under `task_generator/tasks/<task_id>/env/` and write `env_manifest.json`
4. Also write the combined app file `task_generator/tasks/<app>_tasks.json`.

Task rules:

- Proposals are generated without verifier constraints. Verification matching happens in Stage 3 — tasks are adapted, verifiers extended, or tasks discarded there.
- If no endpoint exists but the outcome is inspectable, follow the [Endpoint Extension Workflow](task_generator/ENDPOINT_EXTENSION.md) to build, test, and add the endpoint. Log truly unverifiable tasks to `task_generator/tasks/unverifiable_<app>.md` for human review.
- Avoid duplicating existing tasks in `task_generator/tasks/`.
- Prefer meaningful, non-trivial tasks; default difficulty should stay in the `3-5` range from `task_generator/CLAUDE.md`.
- Verify every generated env artifact actually exists and parses/opens correctly before finalizing the task.

Default output target: unless the user specifies a different count, finalize at least 3 good tasks per app so the repair stage has work to run.

## Stage 4: Repair Loop (Optional)

This stage is **optional**. Only run it when the user explicitly asks for repair, or when you have an explicit reason to debug/repair finalized tasks. Stages 1–3 are sufficient to consider an app done by default.

When you do run it, follow the repair loop defined by [evaluation/repair/README.md](/Users/Mike/Desktop/syn_env/evaluation/repair/README.md) and [evaluation/repair/repair_loop.py](/Users/Mike/Desktop/syn_env/evaluation/repair/repair_loop.py).

Important constraint: `evaluation/repair/repair_loop.py` is single-task only. To repair 3 tasks for one app, run it 3 separate times, once per task.

For each app:

1. Choose exactly 3 finalized task IDs for that app, unless the user asks for a different count.
2. Run:

```bash
python evaluation/repair/repair_loop.py --app <app> --task <task_id> --max-rounds 3
```

3. Repeat for 3 task IDs for that app.
4. Inspect outputs under `evaluation/repair/runs/<task_id>_<timestamp>/`.
5. Read `SOLVED.md` for each run and use it as the repair summary.

Recommended optional flags:

```bash
python evaluation/repair/repair_loop.py \
  --app <app> \
  --task <task_id> \
  --max-rounds 3 \
  --max-iterations 60
```

If you need to run all 3 tasks in a shell loop, do it outside the Python script, for example:

```bash
for task in <task_1> <task_2> <task_3>; do
  python evaluation/repair/repair_loop.py --app <app> --task "$task" --max-rounds 3
done
```

## Required End-to-End Order

For every app, follow this exact order:

1. Read `verifiers/CLAUDE.md`.
2. Generate or update the verifier for the app.
3. Run verifier tests and fix them until they pass (`python verifiers/<app>/test_<app>.py`).
4. Run smoke tests: `python smoke/smoke_loop.py --app <app>`. Fix any endpoint failures, then re-run `--run-only` to confirm.
5. Read `task_generator/CLAUDE.md`.
6. Generate proposals (without consulting verifiers), evaluate them, match to verifiers (adapt/extend/discard), and synthesize env files.
7. Select 3 finalized tasks for the app.

Optional (only when explicitly requested):

8. Run `evaluation/repair/repair_loop.py` on each of those 3 tasks with `--max-rounds 3`.
9. Review each run's `SOLVED.md` and keep any verifier/task fixes produced by the repair loop.

## Practical Notes

- The verifier README is consulted in Stage 3 (verification matching), not during proposal generation. Extend the verifier when a viable verification channel exists but no endpoint covers it yet.
- Do not keep tasks whose criteria have no viable verification channel. Log them to `task_generator/tasks/unverifiable_<app>.md` instead of silently discarding them.
- Keep verifier fixes and task fixes scoped to the target app and task.
- The repair loop is optional and only invoked when explicitly requested. When it does run, it may edit both `task_generator/tasks/<task_id>/task.json` and `verifiers/<app>/`.
- `evaluation/repair/README.md` describes the repair stages; `repair_loop.py` is the executable source of truth for CLI behavior.
- The current repair script default is not the same as your requested workflow, so explicitly pass `--max-rounds 3` when following this root guide.
